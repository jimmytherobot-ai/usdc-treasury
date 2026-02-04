# Changelog

## v2.1.0 — 2026-02-04

### 🌍 Fully Portable (Zero macOS Dependencies)
- **No hardcoded paths** — all references to `~/clawd/`, `jimmy`, specific wallet addresses removed
- **Env-var-first configuration** — `TREASURY_PRIVATE_KEY` is the primary key method
- **Auto `.env` loading** — drops `scripts/.env` at skill root, loaded automatically (no python-dotenv needed)
- **`TREASURY_WALLET`** — env var or auto-derived from private key
- **`TREASURY_DATA_DIR`** — override data directory location
- **`TREASURY_RPC_*`** — per-chain RPC URL overrides
- **`TREASURY_SECRET_CMD`** — plug in any secret manager (1Password, Vault, AWS SM, custom scripts)
- **macOS Keychain** — only activated when `TREASURY_KEYCHAIN_*` vars are explicitly set
- **Private key resolution:** env var → `TREASURY_SECRET_CMD` → macOS Keychain (explicit opt-in only)

### 📋 First-Run Experience
- **`scripts/setup.py`** — validates Python, dependencies, RPC connectivity, wallet config
- Shows clear ❌/✅ diagnostics with actionable fix instructions
- Derives wallet address from key, checks balances, suggests faucet links
- **`requirements.txt`** — `pip install -r requirements.txt` is all you need

### 🌐 Inter-Agent REST API
- **`scripts/server.py`** — lightweight HTTP server for agent-to-agent treasury operations
  - `GET /health` — health check
  - `GET /balance` — treasury balances across all chains
  - `GET /invoices` — list invoices with filters (status, type, counterparty)
  - `GET /invoices/<num>` — get invoice details
  - `GET /invoices/<num>/audit` — full audit trail
  - `POST /invoices` — receive an invoice from another agent
  - `POST /invoices/<num>/pay` — trigger on-chain payment
- Bearer token authentication via `TREASURY_API_KEY` env var
- CORS support for cross-origin requests

### 📦 Python Package Imports
- Proper `__init__.py` with all public API exports
- Importable as `from skills.usdc_treasury.scripts import get_balances, create_invoice, ...`
- Symlink `usdc_treasury` → `usdc-treasury` for Python-friendly imports

## v2.0.0 — 2026-02-04

### 🗄️ SQLite Migration (Breaking: data format change)
- **Replaced JSON files with SQLite database** (`data/treasury.db`)
  - `data/invoices.json` → `invoices` table
  - `data/transactions.json` → `transactions` table
  - `data/budgets.json` → `budgets` table
- **Automatic migration**: On first run, existing JSON files are imported into SQLite then renamed to `.json.bak`
- **Proper indexes** on `tx_hash`, `invoice_number`, `chain`, `counterparty`, `timestamp`, `wallet`
- New `db.py` module — centralized database layer with context-managed connections and WAL mode
- All scripts updated to use SQLite instead of JSON read/write

### 🔢 Invoice Numbering Fix
- **Monotonic counter** stored in SQLite `counters` table
- Invoice numbers (`INV-XXXX`) are **never reused**, even if invoices are deleted
- Counter is seeded from highest existing invoice number during migration

### 🔍 Reconciliation Improvements
- **High-water marks** — stores last scanned block per chain per wallet in SQLite
- Subsequent reconciliation runs only scan from the high-water mark forward (incremental)
- `--from-block` override on `reconcile.py full` and `reconcile.py fetch` commands
- Default first-run lookback increased to **10,000 blocks** (was 1,000)

### 🌉 CCTP Bridge Resume
- **`cctp.py complete <burn_tx_hash>`** — resume a pending bridge that timed out
  - Looks up stored `message_hash`, polls for attestation, calls `receiveMessage`
- **`cctp.py pending`** — list all incomplete bridges
- Pending bridges stored in SQLite `cctp_bridges` table (survives restarts)
- Bridge records include `message_bytes`, `attestation`, and status tracking

### 💰 Incoming Payment Detection
- **`treasury.py watch`** — scan for incoming USDC transfers to our wallet
  - Auto-matches incoming transfers to open receivable invoices (by sender address + amount)
  - Records matched payments and updates invoice status
  - Unmatched incoming transfers recorded as `incoming` transactions
- **`invoices.py receive`** — create receivable invoices (someone owes US money)
  - Sets `invoice_type: "receivable"` vs `"payable"` for outgoing invoices
  - `invoices.py list --type receivable` to filter

### 👛 Multi-Wallet Support
- **`treasury.py wallet add <address> --name "label"`** — register additional wallets
- **`treasury.py wallet list`** — list all tracked wallets
- **`treasury.py wallet remove <address>`** — unregister a wallet
- **`--wallet <address>`** accepted on all commands: `balance`, `transfer`, `history`, `watch`, `reconcile`, reports
- Default treasury wallet always available, cannot be removed
- Balance checks and reconciliation work across any registered wallet

### 📊 Report Improvements
- **Date filtering**: `--start` and `--end` on ALL report commands
  - `reports.py summary --start 2026-02-01 --end 2026-02-28`
  - Works on: `summary`, `balance-sheet`, `income-statement`, `counterparty`, `chain`, `compare`
- **CSV output**: `--format csv` on all report commands
  - Nested structures are flattened; lists of dicts become sub-tables
- **Period comparison**: `reports.py compare [--start X --end Y]`
  - Shows current period vs previous period (same duration)
  - Includes absolute change and percentage change for income/expenses/net
- `reports.py income-statement --compare-period` also works

### 📡 Event Monitor
- **`treasury.py monitor`** — continuous polling for incoming USDC transfers
  - Polls every 30s (configurable with `--interval`)
  - Prints alerts when new transfers detected
  - Auto-matches against open receivable invoices
  - Auto-records all incoming transactions
  - Foreground process, Ctrl-C to stop
  - Supports `--chain` and `--wallet` filters

### 🔧 Technical Changes
- New `scripts/db.py` — SQLite database module with schema, migration, CRUD helpers
- `config.py` simplified — removed `load_json`/`save_json` helpers
- All scripts import `db` module instead of using config JSON helpers
- `INSERT OR IGNORE` prevents duplicate transaction records
- Wallet addresses normalized for consistent lookups
- `signal.SIGINT` handler for graceful monitor shutdown

### 📦 Backward Compatibility
- All existing CLI interfaces preserved (same commands, same arguments)
- New features are additive — existing workflows unchanged
- Legacy JSON files renamed to `.json.bak` (recoverable)
- Output format unchanged for JSON mode

## v1.0.0 — 2026-02-04

Initial release:
- Multi-chain USDC balance tracking (Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia)
- Invoice creation, payment, and audit trail with on-chain USDC settlement
- CCTP v2 cross-chain bridging
- Reconciliation engine matching on-chain vs internal records
- FASB ASU 2023-08 compliant reporting (balance sheet, income statement)
- Budget management with spending alerts
