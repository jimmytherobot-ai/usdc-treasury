# USDC Treasury — QA Test Results

**Date:** 2026-02-04  
**Tester:** Jimmy (AI Agent)  
**Wallet:** `0x8fcc48751905c01cB7ddCC7A0c3d491389805ba8`  
**Network:** Base Sepolia (on-chain tests), all testnet chains  

---

## Summary

| Category | Tests | Pass | Fail | Fixed |
|----------|-------|------|------|-------|
| Edge Cases | 7 | 5 | 2 | ✅ 2 |
| Error Handling | 3 | 3 | 0 | — |
| Reports | 5 | 5 | 0 | — |
| Security | 4 | 3 | 1 | ✅ 1 |
| Code Quality | 5 | 2 | 3 | ✅ 3 |
| **Total** | **24** | **18** | **6** | **✅ 6** |

All 6 bugs were fixed in this QA pass.

---

## 1. Edge Cases

### ✅ PASS — Partial Payment
- **Test:** Created INV-0004 (5 USDC, Base Sepolia), paid 2.5 USDC
- **Command:** `invoices.py pay INV-0004 --amount 2.5`
- **Result:** Status correctly set to "partial", remaining_usdc = "2.5"
- **Tx:** [`0xa9d85c...`](https://base-sepolia.blockscout.com/tx/0xa9d85c89705689db1ccb6c6a498da8a82d51fc6995ca361ecd3fc21eb84aa924)

### ✅ PASS — Overpayment Detection
- **Test:** Paid 3 USDC on INV-0004 (only 2.5 remaining)
- **Command:** `invoices.py pay INV-0004 --amount 3.0`
- **Result:** Status correctly set to "overpaid", remaining_usdc = "-0.5", paid_usdc = "5.5"
- **Tx:** [`0xff2de2...`](https://base-sepolia.blockscout.com/tx/0xff2de2cd9954f7020707e7b6fd66047e8c5743a26745edae31a3ad1df1643542)

### ✅ PASS — Duplicate Payment Rejected
- **Test:** Tried to pay INV-0003 (already paid)
- **Command:** `invoices.py pay INV-0003`
- **Result:** `ValueError: Invoice INV-0003 is already fully paid`

### ✅ PASS — Cancel Invoice
- **Test:** Cancelled INV-0002 (pending, no payments)
- **Command:** `invoices.py cancel INV-0002`
- **Result:** Status changed to "cancelled". Also verified: can't cancel paid (INV-0001) or overpaid (INV-0004) invoices.

### ❌→✅ FIXED — Zero Amount Invoice Accepted
- **Test:** Created invoice with unit_price=0
- **Bug:** Invoice created with total_usdc = "0" — should reject
- **Fix:** Added validation in `create_invoice()`: rejects if total ≤ 0
- **Verified:** Now raises `ValueError: Invoice total must be positive, got 0`

### ❌→✅ FIXED — Negative Amount Invoice Accepted
- **Test:** Created invoice with unit_price=-5.0
- **Bug:** Invoice created with total_usdc = "-5.0" — should reject
- **Fix:** Added validation: rejects negative unit_price and non-positive quantity
- **Verified:** Now raises `ValueError: Line item unit_price cannot be negative: Refund`

### ✅ PASS — Can't Cancel Overpaid/Paid Invoices
- **Test:** Tried cancelling INV-0001 (paid) and INV-0004 (overpaid)
- **Result:** Both correctly rejected with appropriate error messages

---

## 2. Error Handling

### ✅ PASS — Insufficient USDC
- **Command:** `treasury.py transfer base_sepolia 0x...dEaD 1000`
- **Result:** `ValueError: Insufficient USDC balance on Base Sepolia: have 1.5, need 1000`

### ✅ PASS — Invalid Address (improved)
- **Command:** `treasury.py transfer base_sepolia INVALID_ADDRESS 1.0`
- **Original:** Raw web3 traceback (`ValueError: when sending a str, it must be a hex string`)
- **Fix:** Added `Web3.is_address()` validation — now raises `ValueError: Invalid Ethereum address: INVALID_ADDRESS`
- **Also added:** Address validation in `create_invoice()` for counterparty address

### ✅ PASS — Malformed JSON
- **Command:** `invoices.py create --items '{broken json'`
- **Result:** `json.decoder.JSONDecodeError` with clear position info

---

## 3. Reports

### ✅ PASS — Balance Sheet
- **Command:** `reports.py balance-sheet`
- **Result:** Valid JSON with FASB ASU 2023-08 categorization, digital assets, AR aging

### ✅ PASS — Income Statement
- **Command:** `reports.py income-statement`
- **Result:** Correct expense categorization (18.50 USDC in services)

### ✅ PASS — Counterparty Report (bug fixed)
- **Command:** `reports.py counterparty`
- **Bug found:** Cancelled invoices were counted in `total_outstanding_usdc`
- **Fix:** Exclude cancelled invoices from outstanding totals
- **Result:** Now correctly shows 0 outstanding for cancelled invoices

### ✅ PASS — Chain Report
- **Command:** `reports.py chain`
- **Result:** Per-chain breakdown with volume, tx counts, categories

### ✅ PASS — Treasury Summary
- **Command:** `reports.py summary`
- **Result:** Correct aggregate data (21.5 total USDC, 6 invoices, 6 transactions)

---

## 4. Security Review

### ✅ PASS — No Private Key Leakage
- **Check:** Searched all .py files for print/log of private keys
- **Result:** Private keys are never printed, logged, or stored in data files
- **Note:** `get_private_key()` retrieves from KeePassXC/Keychain at runtime only

### ✅ PASS — Clean Data Files
- **Check:** Searched `data/invoices.json` and `data/transactions.json` for secrets
- **Result:** Only public data (tx hashes, wallet addresses, amounts) — no secrets

### ❌→✅ FIXED — No Mainnet Guard
- **Bug:** No protection against adding mainnet chain IDs to CHAINS config
- **Fix:** Added startup validation that rejects mainnet chain IDs (1, 8453, 42161, 10, 137, 43114, 56)
- **Error:** `RuntimeError: SAFETY: Mainnet chain ID detected... This tool is testnet-only.`

### ✅ PASS — No Hardcoded Secrets
- **Check:** Searched for hardcoded keys, passwords, mnemonics
- **Result:** All secrets retrieved via `get_private_key()` from KeePassXC/Keychain

---

## 5. Code Quality

### ❌→✅ FIXED — No File Locking (Concurrent Access Safety)
- **Bug:** `load_json()` and `save_json()` had no file locking — concurrent writes could corrupt JSON
- **Fix:** Added `fcntl.flock()` — shared lock for reads, exclusive lock for writes
- **Verified:** Read/write operations work correctly with locking

### ❌→✅ FIXED — save_json Failed on New Files
- **Bug:** After adding file locking, `save_json` used `r+` mode which fails if file doesn't exist
- **Fix:** Changed to `a+` mode with seek/truncate pattern
- **Verified:** Works for both new and existing files

### ❌→✅ FIXED — Raw Tracebacks in CLI
- **Bug:** CLI entrypoints showed raw Python tracebacks on errors
- **Fix:** Added try/except wrappers to all 5 CLI scripts — errors now output clean JSON to stderr
- **Example:** `{"error": "Invalid Ethereum address: INVALID"}`

### ✅ PASS — Explorer URLs
- **Check:** Verified `.hex()` returns without "0x" prefix, code adds "0x"
- **Result:** All explorer URLs correctly formatted (blockscout for Base, etherscan for Eth/Arb)

### ✅ PASS — Decimal Precision
- **Check:** All amounts use Python `Decimal` — no floating-point arithmetic
- **Result:** USDC 6-decimal precision maintained throughout
- **Note:** Sub-unit amounts (<0.000001) silently truncate to 0 via `int()` — not a practical concern

---

## Bugs Fixed (6 total)

1. **Zero/negative invoice amounts** — Added input validation for line items and totals
2. **Counterparty report counting cancelled invoices** — Excluded from outstanding totals
3. **No mainnet safety guard** — Added chain ID blocklist check at import time
4. **No file locking** — Added `fcntl.flock()` for concurrent access safety
5. **save_json fails on new files** — Changed file mode from `r+` to `a+`
6. **Raw tracebacks in CLI** — Added JSON error output wrappers to all scripts
7. *(Improvement)* **Friendly address validation** — Added `Web3.is_address()` checks in treasury.py and invoices.py

---

## On-Chain Test Transactions

| Tx | Type | Amount | Chain | Block |
|----|------|--------|-------|-------|
| `0xa9d85c...` | Partial payment (INV-0004) | 2.5 USDC | Base Sepolia | 37217713 |
| `0xff2de2...` | Overpayment (INV-0004) | 3.0 USDC | Base Sepolia | 37217719 |

---

## Final State

- **INV-0001:** paid (9 USDC, Base Sepolia)
- **INV-0002:** cancelled (was 7.5 USDC, Ethereum Sepolia)
- **INV-0003:** paid (3 USDC, Base Sepolia)
- **INV-0004:** overpaid (5.5/5.0 USDC, Base Sepolia) — QA test invoice
- **INV-0005:** cancelled (0 USDC zero-amount test)
- **INV-0006:** cancelled (-5 USDC negative-amount test)
- **Balances:** 20 USDC (Eth Sepolia), 1.5 USDC (Base Sepolia), 0 (Arb Sepolia)
