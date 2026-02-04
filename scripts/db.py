"""
USDC Treasury - SQLite Database Layer
Replaces JSON file storage with proper SQLite database.
Handles schema creation, migration from JSON, and all CRUD operations.
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import contextmanager

# ============================================================
# Database Path
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "treasury.db")

# Legacy JSON paths (for migration)
_LEGACY_INVOICES = os.path.join(DATA_DIR, "invoices.json")
_LEGACY_TRANSACTIONS = os.path.join(DATA_DIR, "transactions.json")
_LEGACY_BUDGETS = os.path.join(DATA_DIR, "budgets.json")


# ============================================================
# Schema
# ============================================================

SCHEMA_SQL = """
-- Transactions ledger
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT NOT NULL,
    chain TEXT NOT NULL,
    chain_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'outgoing',
    from_address TEXT NOT NULL DEFAULT '',
    to_address TEXT NOT NULL DEFAULT '',
    amount_usdc TEXT NOT NULL DEFAULT '0',
    amount_raw INTEGER NOT NULL DEFAULT 0,
    type TEXT NOT NULL DEFAULT 'transfer',
    category TEXT NOT NULL DEFAULT 'uncategorized',
    memo TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'confirmed',
    block_number INTEGER,
    gas_used INTEGER,
    timestamp TEXT NOT NULL,
    explorer_url TEXT NOT NULL DEFAULT '',
    invoice_number TEXT,
    cctp_message_hash TEXT,
    cctp_burn_tx TEXT,
    wallet TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_tx_chain ON transactions(chain);
CREATE INDEX IF NOT EXISTS idx_tx_counterparty_from ON transactions(from_address);
CREATE INDEX IF NOT EXISTS idx_tx_counterparty_to ON transactions(to_address);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_invoice ON transactions(invoice_number);
CREATE INDEX IF NOT EXISTS idx_tx_wallet ON transactions(wallet);

-- Invoices
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    invoice_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    counterparty_name TEXT NOT NULL,
    counterparty_address TEXT NOT NULL,
    from_wallet TEXT NOT NULL,
    chain TEXT NOT NULL,
    chain_name TEXT NOT NULL DEFAULT '',
    line_items_json TEXT NOT NULL DEFAULT '[]',
    total_usdc TEXT NOT NULL DEFAULT '0',
    paid_usdc TEXT NOT NULL DEFAULT '0',
    remaining_usdc TEXT NOT NULL DEFAULT '0',
    payments_json TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL DEFAULT 'uncategorized',
    memo TEXT NOT NULL DEFAULT '',
    invoice_type TEXT NOT NULL DEFAULT 'payable',
    created_at TEXT NOT NULL,
    due_date TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inv_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_inv_chain ON invoices(chain);
CREATE INDEX IF NOT EXISTS idx_inv_counterparty ON invoices(counterparty_address);
CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status);

-- Budgets
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    category TEXT NOT NULL,
    limit_usdc TEXT NOT NULL,
    period TEXT NOT NULL DEFAULT 'monthly',
    created TEXT NOT NULL,
    updated TEXT,
    UNIQUE(chain, category)
);

-- Monotonic counters (for invoice numbering, etc.)
CREATE TABLE IF NOT EXISTS counters (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

-- High-water marks for reconciliation (last scanned block per chain per wallet)
CREATE TABLE IF NOT EXISTS high_water_marks (
    chain TEXT NOT NULL,
    wallet TEXT NOT NULL,
    block_number INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chain, wallet)
);

-- CCTP pending bridges
CREATE TABLE IF NOT EXISTS cctp_bridges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    burn_tx_hash TEXT NOT NULL UNIQUE,
    source_chain TEXT NOT NULL,
    dest_chain TEXT NOT NULL,
    amount_usdc TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_hash TEXT,
    message_bytes TEXT,
    attestation TEXT,
    mint_tx_hash TEXT,
    status TEXT NOT NULL DEFAULT 'burn_confirmed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cctp_burn ON cctp_bridges(burn_tx_hash);
CREATE INDEX IF NOT EXISTS idx_cctp_status ON cctp_bridges(status);

-- Wallets
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
"""


# ============================================================
# Connection Management
# ============================================================

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_connection():
    """Get a SQLite connection with WAL mode and foreign keys."""
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections with auto-commit."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema and run migration if needed."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
    _migrate_from_json()


# ============================================================
# JSON Migration
# ============================================================

def _migrate_from_json():
    """If legacy JSON files exist, import into SQLite and rename to .bak"""
    migrated = False

    # Migrate transactions
    if os.path.exists(_LEGACY_TRANSACTIONS) and not _LEGACY_TRANSACTIONS.endswith('.bak'):
        try:
            with open(_LEGACY_TRANSACTIONS) as f:
                txs = json.load(f)
            if isinstance(txs, list) and len(txs) > 0:
                with get_db() as conn:
                    # Check if we already have data
                    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                    if count == 0:
                        for tx in txs:
                            _insert_transaction_from_dict(conn, tx)
                        print(f"Migrated {len(txs)} transactions from JSON to SQLite")
                os.rename(_LEGACY_TRANSACTIONS, _LEGACY_TRANSACTIONS + ".bak")
                migrated = True
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not migrate transactions.json: {e}")

    # Migrate invoices
    if os.path.exists(_LEGACY_INVOICES) and not _LEGACY_INVOICES.endswith('.bak'):
        try:
            with open(_LEGACY_INVOICES) as f:
                invoices = json.load(f)
            if isinstance(invoices, list) and len(invoices) > 0:
                with get_db() as conn:
                    count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
                    if count == 0:
                        max_num = 0
                        for inv in invoices:
                            _insert_invoice_from_dict(conn, inv)
                            # Track highest invoice number for counter
                            num_str = inv.get("invoice_number", "INV-0000")
                            try:
                                num = int(num_str.split("-")[1])
                                max_num = max(max_num, num)
                            except (IndexError, ValueError):
                                pass
                        # Set the counter to the highest invoice number
                        conn.execute(
                            "INSERT OR REPLACE INTO counters (key, value) VALUES (?, ?)",
                            ("invoice_number", max_num)
                        )
                        print(f"Migrated {len(invoices)} invoices from JSON to SQLite")
                os.rename(_LEGACY_INVOICES, _LEGACY_INVOICES + ".bak")
                migrated = True
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not migrate invoices.json: {e}")

    # Migrate budgets
    if os.path.exists(_LEGACY_BUDGETS) and not _LEGACY_BUDGETS.endswith('.bak'):
        try:
            with open(_LEGACY_BUDGETS) as f:
                budgets = json.load(f)
            if isinstance(budgets, list) and len(budgets) > 0:
                with get_db() as conn:
                    count = conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
                    if count == 0:
                        for b in budgets:
                            conn.execute(
                                "INSERT INTO budgets (chain, category, limit_usdc, period, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                                (b["chain"], b["category"], b["limit_usdc"], b.get("period", "monthly"),
                                 b.get("created", datetime.now(timezone.utc).isoformat()),
                                 b.get("updated"))
                            )
                        print(f"Migrated {len(budgets)} budgets from JSON to SQLite")
                os.rename(_LEGACY_BUDGETS, _LEGACY_BUDGETS + ".bak")
                migrated = True
            else:
                # Empty budgets file, just rename it
                os.rename(_LEGACY_BUDGETS, _LEGACY_BUDGETS + ".bak")
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not migrate budgets.json: {e}")

    if migrated:
        print("JSON → SQLite migration complete. Original files renamed to .json.bak")


def _insert_transaction_from_dict(conn, tx):
    """Insert a transaction dict (from legacy JSON) into SQLite."""
    conn.execute("""
        INSERT OR IGNORE INTO transactions
        (tx_hash, chain, chain_name, direction, from_address, to_address,
         amount_usdc, amount_raw, type, category, memo, status,
         block_number, gas_used, timestamp, explorer_url,
         invoice_number, cctp_message_hash, cctp_burn_tx, wallet, extra_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tx.get("tx_hash", ""),
        tx.get("chain", ""),
        tx.get("chain_name", ""),
        tx.get("direction", "outgoing"),
        tx.get("from", tx.get("from_address", "")),
        tx.get("to", tx.get("to_address", "")),
        tx.get("amount_usdc", "0"),
        tx.get("amount_raw", 0),
        tx.get("type", "transfer"),
        tx.get("category", "uncategorized"),
        tx.get("memo", ""),
        tx.get("status", "confirmed"),
        tx.get("block_number"),
        tx.get("gas_used"),
        tx.get("timestamp", datetime.now(timezone.utc).isoformat()),
        tx.get("explorer_url", ""),
        tx.get("invoice_number"),
        tx.get("cctp_message_hash"),
        tx.get("cctp_burn_tx"),
        tx.get("wallet", tx.get("from", tx.get("from_address", ""))),
        json.dumps({k: v for k, v in tx.items() if k not in {
            "tx_hash", "chain", "chain_name", "direction", "from", "from_address",
            "to", "to_address", "amount_usdc", "amount_raw", "type", "category",
            "memo", "status", "block_number", "gas_used", "timestamp", "explorer_url",
            "invoice_number", "cctp_message_hash", "cctp_burn_tx", "wallet"
        }})
    ))


def _insert_invoice_from_dict(conn, inv):
    """Insert an invoice dict (from legacy JSON) into SQLite."""
    cp = inv.get("counterparty", {})
    conn.execute("""
        INSERT OR IGNORE INTO invoices
        (id, invoice_number, status, counterparty_name, counterparty_address,
         from_wallet, chain, chain_name, line_items_json, total_usdc,
         paid_usdc, remaining_usdc, payments_json, category, memo,
         invoice_type, created_at, due_date, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        inv.get("id", str(uuid.uuid4())),
        inv.get("invoice_number", ""),
        inv.get("status", "pending"),
        cp.get("name", ""),
        cp.get("address", ""),
        inv.get("from_wallet", ""),
        inv.get("chain", ""),
        inv.get("chain_name", ""),
        json.dumps(inv.get("line_items", [])),
        inv.get("total_usdc", "0"),
        inv.get("paid_usdc", "0"),
        inv.get("remaining_usdc", "0"),
        json.dumps(inv.get("payments", [])),
        inv.get("category", "uncategorized"),
        inv.get("memo", ""),
        inv.get("invoice_type", "payable"),
        inv.get("created_at", datetime.now(timezone.utc).isoformat()),
        inv.get("due_date", ""),
        inv.get("updated_at", datetime.now(timezone.utc).isoformat()),
    ))


# ============================================================
# Counter Helpers
# ============================================================

def next_counter(key):
    """Atomically increment and return the next counter value. Never reuses numbers."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO counters (key, value) VALUES (?, 0) ON CONFLICT(key) DO NOTHING",
            (key,)
        )
        conn.execute(
            "UPDATE counters SET value = value + 1 WHERE key = ?",
            (key,)
        )
        row = conn.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
        return row[0]


def get_counter(key):
    """Get current counter value without incrementing."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM counters WHERE key = ?", (key,)).fetchone()
        return row[0] if row else 0


# ============================================================
# Transaction CRUD
# ============================================================

def insert_transaction(tx):
    """Insert a transaction record."""
    with get_db() as conn:
        _insert_transaction_from_dict(conn, tx)


def get_transactions(chain=None, category=None, counterparty=None, wallet=None, limit=50,
                     start=None, end=None, tx_type=None):
    """Query transactions with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []

        if chain:
            query += " AND chain = ?"
            params.append(chain)
        if category:
            query += " AND category = ?"
            params.append(category)
        if counterparty:
            cp = counterparty.lower()
            query += " AND (LOWER(from_address) = ? OR LOWER(to_address) = ?)"
            params.extend([cp, cp])
        if wallet:
            query += " AND (LOWER(from_address) = LOWER(?) OR LOWER(to_address) = LOWER(?) OR LOWER(wallet) = LOWER(?))"
            params.extend([wallet, wallet, wallet])
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        if tx_type:
            query += " AND type = ?"
            params.append(tx_type)

        query += " ORDER BY timestamp DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [_tx_row_to_dict(r) for r in rows]


def get_all_transactions():
    """Get all transactions (no limit)."""
    return get_transactions(limit=None)


def _tx_row_to_dict(row):
    """Convert a transaction row to dict format matching legacy JSON."""
    d = dict(row)
    # Map column names to legacy format
    d["from"] = d.pop("from_address", "")
    d["to"] = d.pop("to_address", "")
    # Remove internal id
    d.pop("id", None)
    # Parse extra_json
    extra = d.pop("extra_json", "{}")
    try:
        extra_data = json.loads(extra)
        d.update(extra_data)
    except (json.JSONDecodeError, TypeError):
        pass
    return d


# ============================================================
# Invoice CRUD
# ============================================================

def insert_invoice(inv):
    """Insert an invoice record. inv is a dict."""
    with get_db() as conn:
        _insert_invoice_from_dict(conn, inv)


def get_invoice(invoice_number=None, invoice_id=None):
    """Get a single invoice by number or UUID."""
    with get_db() as conn:
        if invoice_number:
            row = conn.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
        elif invoice_id:
            row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        else:
            return None
        return _invoice_row_to_dict(row) if row else None


def list_invoices(status=None, counterparty=None, chain=None, invoice_type=None,
                  start=None, end=None, wallet=None):
    """List invoices with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM invoices WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if counterparty:
            cp = counterparty.lower()
            query += " AND LOWER(counterparty_name) LIKE ?"
            params.append(f"%{cp}%")
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        if invoice_type:
            query += " AND invoice_type = ?"
            params.append(invoice_type)
        if start:
            query += " AND created_at >= ?"
            params.append(start)
        if end:
            query += " AND created_at <= ?"
            params.append(end)
        if wallet:
            query += " AND LOWER(from_wallet) = LOWER(?)"
            params.append(wallet)

        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [_invoice_row_to_dict(r) for r in rows]


_INVOICE_COLUMNS = {
    "status", "counterparty_name", "counterparty_address", "from_wallet",
    "chain", "chain_name", "line_items_json", "total_usdc", "paid_usdc",
    "remaining_usdc", "payments_json", "category", "memo", "invoice_type",
    "created_at", "due_date", "updated_at",
}


def update_invoice(invoice_number, updates):
    """Update invoice fields by invoice_number. updates is a dict of column: value."""
    with get_db() as conn:
        set_clauses = []
        params = []
        for col, val in updates.items():
            if col not in _INVOICE_COLUMNS:
                raise ValueError(f"Invalid invoice column: {col}")
            set_clauses.append(f"{col} = ?")
            params.append(val)
        params.append(invoice_number)
        conn.execute(
            f"UPDATE invoices SET {', '.join(set_clauses)} WHERE invoice_number = ?",
            params
        )


def _invoice_row_to_dict(row):
    """Convert an invoice row to dict format matching legacy JSON."""
    if row is None:
        return None
    d = dict(row)
    # Restructure counterparty
    d["counterparty"] = {
        "name": d.pop("counterparty_name", ""),
        "address": d.pop("counterparty_address", ""),
    }
    # Parse JSON fields
    try:
        d["line_items"] = json.loads(d.pop("line_items_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["line_items"] = []
    try:
        d["payments"] = json.loads(d.pop("payments_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["payments"] = []
    return d


# ============================================================
# Budget CRUD
# ============================================================

def set_budget(chain, category, limit_usdc, period="monthly"):
    """Create or update a budget."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO budgets (chain, category, limit_usdc, period, created, updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chain, category) DO UPDATE SET
                limit_usdc = excluded.limit_usdc,
                period = excluded.period,
                updated = excluded.updated
        """, (chain, category, str(limit_usdc), period, now, now))
    return {"status": "ok", "chain": chain, "category": category, "limit": str(limit_usdc)}


def get_budgets(chain=None, category=None):
    """Get budgets with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM budgets WHERE 1=1"
        params = []
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        if category:
            query += " AND category = ?"
            params.append(category)
        return [dict(r) for r in conn.execute(query, params).fetchall()]


# ============================================================
# High-Water Mark
# ============================================================

def get_high_water_mark(chain, wallet):
    """Get the last scanned block number for a chain+wallet."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT block_number FROM high_water_marks WHERE chain = ? AND wallet = ?",
            (chain, wallet)
        ).fetchone()
        return row[0] if row else None


def set_high_water_mark(chain, wallet, block_number):
    """Set the last scanned block number."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO high_water_marks (chain, wallet, block_number, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chain, wallet) DO UPDATE SET
                block_number = excluded.block_number,
                updated_at = excluded.updated_at
        """, (chain, wallet, block_number, datetime.now(timezone.utc).isoformat()))


# ============================================================
# CCTP Bridges
# ============================================================

def insert_bridge(bridge):
    """Insert a CCTP bridge record."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO cctp_bridges
            (burn_tx_hash, source_chain, dest_chain, amount_usdc, recipient,
             message_hash, message_bytes, attestation, mint_tx_hash, status,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bridge["burn_tx_hash"],
            bridge["source_chain"],
            bridge["dest_chain"],
            bridge["amount_usdc"],
            bridge["recipient"],
            bridge.get("message_hash"),
            bridge.get("message_bytes"),
            bridge.get("attestation"),
            bridge.get("mint_tx_hash"),
            bridge.get("status", "burn_confirmed"),
            bridge.get("created_at", now),
            now,
        ))


def get_bridge(burn_tx_hash):
    """Get a CCTP bridge by burn tx hash."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cctp_bridges WHERE burn_tx_hash = ?",
            (burn_tx_hash,)
        ).fetchone()
        return dict(row) if row else None


_BRIDGE_COLUMNS = {
    "source_chain", "dest_chain", "amount_usdc", "recipient",
    "message_hash", "message_bytes", "attestation", "mint_tx_hash", "status",
}


def update_bridge(burn_tx_hash, updates):
    """Update bridge fields."""
    with get_db() as conn:
        set_clauses = []
        params = []
        for col, val in updates.items():
            if col not in _BRIDGE_COLUMNS:
                raise ValueError(f"Invalid bridge column: {col}")
            set_clauses.append(f"{col} = ?")
            params.append(val)
        updates_str = ", ".join(set_clauses)
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(burn_tx_hash)
        conn.execute(
            f"UPDATE cctp_bridges SET {updates_str}, updated_at = ? WHERE burn_tx_hash = ?",
            params
        )


def list_pending_bridges():
    """List all bridges not yet completed."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cctp_bridges WHERE status != 'completed' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# Wallet Management
# ============================================================

def add_wallet(address, name="", is_default=False):
    """Add a wallet to tracking."""
    with get_db() as conn:
        if is_default:
            conn.execute("UPDATE wallets SET is_default = 0")
        conn.execute("""
            INSERT OR REPLACE INTO wallets (address, name, is_default, added_at)
            VALUES (?, ?, ?, ?)
        """, (address.lower(), name, 1 if is_default else 0,
              datetime.now(timezone.utc).isoformat()))


def list_wallets():
    """List all tracked wallets."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM wallets ORDER BY is_default DESC, added_at ASC").fetchall()
        return [dict(r) for r in rows]


def remove_wallet(address):
    """Remove a wallet from tracking."""
    with get_db() as conn:
        conn.execute("DELETE FROM wallets WHERE LOWER(address) = LOWER(?)", (address,))


def get_default_wallet():
    """Get the default wallet address, or None."""
    with get_db() as conn:
        row = conn.execute("SELECT address FROM wallets WHERE is_default = 1").fetchone()
        return row[0] if row else None


def get_all_wallet_addresses():
    """Get list of all wallet addresses (for multi-wallet operations)."""
    wallets = list_wallets()
    return [w["address"] for w in wallets]


# ============================================================
# Init on import
# ============================================================

init_db()
