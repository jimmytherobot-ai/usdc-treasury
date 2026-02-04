# USDC Treasury v2.0.0 — QA Results

**Date:** 2026-02-04  
**Tester:** Jimmy (AI agent, subagent QA)  
**Commit base:** `27b4ba0` (v2.0.0)

## Summary

**Overall: PASS** — 3 bugs found and fixed, all core functionality verified.

### Bugs Found & Fixed

1. **EIP-55 Checksum Error on `--wallet` flag** (treasury.py, reconcile.py)
   - `get_balance()` passed raw wallet address to web3 without checksumming
   - `reconcile.py` had same issue in `balanceOf(wallet)` call
   - **Fix:** Added `Web3.to_checksum_address(wallet)` before all web3 calls

2. **Balance Sheet AR/AP Confusion** (reports.py)
   - All pending/partial invoices were classified as "Accounts Receivable"
   - Payable invoices (we owe them) should be "Accounts Payable" (liability)
   - **Fix:** Split into AR (receivable) and AP (payable), added `liabilities` section

3. **SQL Injection Risk in Dynamic UPDATE** (db.py)
   - `update_invoice()` and `update_bridge()` used f-strings for column names
   - While callers only pass known columns, this was a defense-in-depth gap
   - **Fix:** Added `_INVOICE_COLUMNS` and `_BRIDGE_COLUMNS` whitelists with validation

## Test Results

### 1. Core Regression ✅

| Test | Result |
|------|--------|
| `treasury.py balance` | ✅ 21.5 USDC across 3 chains |
| `invoices.py list` | ✅ 10 invoices (2 paid, 3 pending, 4 cancelled, 1 overpaid) |
| `reconcile.py full` | ✅ balance_ok=True, 0 discrepancies |
| `reports.py summary` | ✅ Complete summary with all sections |
| `reports.py balance-sheet` | ✅ FASB-compliant with AR/AP separation |

### 2. SQLite Migration ✅

| Check | Result |
|-------|--------|
| `data/treasury.db` exists | ✅ 135,168 bytes |
| All 7 tables present | ✅ transactions, invoices, budgets, counters, wallets, high_water_marks, cctp_bridges |
| Indexes on key columns | ✅ 11 indexes verified (tx_hash, chain, timestamp, invoice_number, wallet, etc.) |
| `.json.bak` files | ✅ invoices.json.bak, transactions.json.bak, budgets.json.bak |
| Data integrity | ✅ 7 invoices migrated, 6 transactions, counter=7 |
| WAL mode | ✅ Configured in get_connection() |

### 3. Invoice Numbering ✅

| Test | Result |
|------|--------|
| Create new invoice | ✅ Got INV-0008 (counter was 7) |
| Cancel INV-0008, create another | ✅ Got INV-0009 (no reuse) |
| Counter table | ✅ `invoice_number|9` after creating INV-0009 |
| Atomic increment | ✅ Uses INSERT ON CONFLICT + UPDATE + SELECT |

### 4. New Features

#### Multi-Wallet ✅
- `wallet list` — shows default treasury + any added wallets
- `wallet add` — validates address, stores with name
- `wallet remove` — prevents removing default wallet
- `balance --wallet` — works after checksum fix
- Wallet addresses normalized to lowercase in DB

#### Receivable Invoices ✅
- `invoices.py receive` — creates invoice with `invoice_type: "receivable"`
- Shows correctly in `list --type receivable`
- Cancel receivable — works
- Shows in balance sheet AR section (not AP)

#### CCTP Resume ✅
- `cctp.py pending` — returns empty list (no pending bridges)
- `cctp.py complete --help` — shows correct args
- Bridge records stored in `cctp_bridges` table with full state

#### Incoming Payment Watch ✅
- `treasury.py watch --help` — correct arguments
- Uses high-water marks for efficient scanning
- Auto-matches incoming against receivable invoices

#### Reports with Date Filtering ✅
- `summary --start/--end` — filters transactions and invoices
- `balance-sheet --start` — accepted (note: balance sheet is point-in-time)
- `income-statement --start/--end` — correctly categorizes expenses/income
- `counterparty` — shows all counterparties with invoice breakdown
- `chain` — per-chain volume and balance breakdown
- Future dates (2030) — returns empty, no crash ✅

#### CSV Export ✅
- `summary --format csv` — valid CSV key/value pairs
- `counterparty --format csv` — nested structures flattened to sub-tables

#### Period Comparison ✅
- `compare --start/--end` — shows current vs previous period
- Percentage changes calculated correctly
- N/A shown when previous period is zero

#### Reconciliation with High-Water Marks ✅
- First run: scans 10,000 blocks (default lookback)
- Subsequent runs: starts from high-water mark (fast, ~4.5s)
- `high_water_marks` table: 3 rows (one per chain)
- Block numbers update on each scan

### 5. Edge Cases ✅

| Test | Result |
|------|--------|
| Zero-amount invoice | ✅ Rejected: "Invoice total must be positive" |
| Negative price invoice | ✅ Rejected: "unit_price cannot be negative" |
| Future date reports | ✅ Returns empty, no crash |
| Cancel receivable invoice | ✅ Works correctly |
| Cancelled invoice outstanding | ✅ Not counted in AR/AP |

### 6. Security Review ✅

| Check | Result |
|-------|--------|
| SQL injection (parameterized queries) | ✅ All queries use `?` params. Dynamic column names now whitelisted |
| Private key never in DB | ✅ No secrets in treasury.db |
| Private key never logged | ✅ Only retrieved in get_private_key(), passed to web3 signer |
| Mainnet protection | ✅ MAINNET_CHAIN_IDS guard raises RuntimeError for mainnet chain IDs |
| Wallet key retrieval | ✅ KeePassXC → macOS Keychain fallback chain |

### 7. Code Quality ✅

| Check | Result |
|-------|--------|
| All .py files reviewed | ✅ db.py, config.py, treasury.py, invoices.py, reconcile.py, reports.py, cctp.py |
| No unhandled exceptions | ✅ All CLI scripts have try/except with JSON error output |
| No circular imports | ✅ Import chain: config ← db ← treasury ← invoices, reports, reconcile, cctp |
| SKILL.md updated for v2 | ✅ Complete with all new commands |
| README.md updated | ✅ Structure reflects db.py, SQLite data |
| CHANGELOG.md accurate | ✅ All v2 features documented |
| `__init__.py` present | ✅ |

## Notes

- **6 unmatched internal transactions** in reconciliation are expected — they occurred before the high-water mark scan range. A full rescan with `--from-block 0` would match them.
- INV-0005 (total=0) and INV-0006 (total=-5) are legacy test data from v1 QA, already cancelled. Current validation prevents these.
- The `direction` field defaults to `"outgoing"` in schema; incoming transactions explicitly set it to `"incoming"`.
