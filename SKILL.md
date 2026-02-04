---
name: usdc-treasury
version: 2.0.0
description: "USDC Treasury & Invoice Management — QuickBooks for AI agents, settled in USDC on-chain. Multi-chain testnet treasury tracking, invoicing with on-chain payment settlement, CCTP bridging, reconciliation, and FASB ASU 2023-08 compliant reporting."
author: jimmytherobot-ai
homepage: https://github.com/jimmytherobot-ai/usdc-treasury
tags: [usdc, treasury, invoicing, accounting, cctp, stablecoin, defi]
chains: [ethereum-sepolia, base-sepolia, arbitrum-sepolia]
---

# USDC Treasury & Invoice Management

**QuickBooks for AI agents, settled in USDC.**

A complete treasury management and invoicing system built on USDC testnet. Track balances across chains, create and pay invoices with on-chain settlement, bridge USDC via CCTP, and generate FASB-compliant reports.

## Wallet

- **Address:** `0x8fcc48751905c01cB7ddCC7A0c3d491389805ba8`
- **Private key:** KeePassXC (`~/clawd/scripts/get-secret.sh jimmy-wallet-eth`)
- **Networks:** Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia

## Quick Reference

```bash
cd ~/clawd && source .venv/bin/activate
SCRIPTS=skills/usdc-treasury/scripts
```

### Treasury

```bash
# Check all balances
python $SCRIPTS/treasury.py balance

# Check specific chain
python $SCRIPTS/treasury.py balance --chain ethereum_sepolia

# Transfer USDC
python $SCRIPTS/treasury.py transfer ethereum_sepolia 0xRECIPIENT 10.00 --memo "Payment" --category services

# Transaction history
python $SCRIPTS/treasury.py history --chain ethereum_sepolia --category services

# Set budget
python $SCRIPTS/treasury.py budget set --chain ethereum_sepolia --category services --limit 1000 --period monthly

# Check budget status
python $SCRIPTS/treasury.py budget status
```

### Invoices

```bash
# Create invoice
python $SCRIPTS/invoices.py create \
  --counterparty-name "Acme Corp" \
  --counterparty-address 0xRECIPIENT \
  --items '[{"description": "Consulting", "quantity": 10, "unit_price": 50}]' \
  --chain ethereum_sepolia \
  --due-days 30 \
  --category services

# List invoices
python $SCRIPTS/invoices.py list --status pending

# Pay invoice (full)
python $SCRIPTS/invoices.py pay INV-0001

# Pay invoice (partial)
python $SCRIPTS/invoices.py pay INV-0001 --amount 100

# Audit trail
python $SCRIPTS/invoices.py audit INV-0001

# Cancel invoice
python $SCRIPTS/invoices.py cancel INV-0001
```

### Cross-Chain Bridge (CCTP v2)

```bash
# Bridge USDC between chains
python $SCRIPTS/cctp.py bridge ethereum_sepolia base_sepolia 10.00

# Check bridge status
python $SCRIPTS/cctp.py status BURN_TX_HASH

# Resume a pending bridge (if attestation timed out)
python $SCRIPTS/cctp.py complete BURN_TX_HASH

# List pending bridges
python $SCRIPTS/cctp.py pending
```

### Receivable Invoices

```bash
# Create invoice where someone owes US money
python $SCRIPTS/invoices.py receive \
  --counterparty-name "Client Corp" \
  --counterparty-address 0xCLIENT \
  --items '[{"description": "Consulting", "quantity": 5, "unit_price": 100}]' \
  --chain base_sepolia

# List receivable invoices
python $SCRIPTS/invoices.py list --type receivable

# Scan for incoming payments (auto-matches to receivable invoices)
python $SCRIPTS/treasury.py watch --chain base_sepolia
```

### Wallet Management

```bash
# Add a wallet to track
python $SCRIPTS/treasury.py wallet add 0xADDRESS --name "Cold Storage"

# List wallets
python $SCRIPTS/treasury.py wallet list

# Remove wallet
python $SCRIPTS/treasury.py wallet remove 0xADDRESS

# Check balance on a specific wallet
python $SCRIPTS/treasury.py balance --wallet 0xADDRESS
```

### Reconciliation

```bash
# Full reconciliation (all chains)
python $SCRIPTS/reconcile.py full

# Reconcile specific chain
python $SCRIPTS/reconcile.py full --chain ethereum_sepolia

# Override scan start block
python $SCRIPTS/reconcile.py full --from-block 37200000

# Reconcile specific invoice
python $SCRIPTS/reconcile.py invoice INV-0001

# Fetch on-chain transfers
python $SCRIPTS/reconcile.py fetch ethereum_sepolia --from-block 37200000
```

### Reports

```bash
# FASB-compliant balance sheet
python $SCRIPTS/reports.py balance-sheet

# Income statement
python $SCRIPTS/reports.py income-statement --start 2026-02-01 --end 2026-02-28

# Period comparison (current vs previous)
python $SCRIPTS/reports.py compare --start 2026-02-01 --end 2026-02-28

# Counterparty report
python $SCRIPTS/reports.py counterparty --name "Acme"

# Per-chain report
python $SCRIPTS/reports.py chain

# Treasury summary
python $SCRIPTS/reports.py summary

# CSV output (any report)
python $SCRIPTS/reports.py summary --format csv

# Date filtering (any report)
python $SCRIPTS/reports.py summary --start 2026-02-01 --end 2026-02-28
```

### Event Monitor

```bash
# Continuous monitoring for incoming USDC (Ctrl-C to stop)
python $SCRIPTS/treasury.py monitor

# Monitor specific chain
python $SCRIPTS/treasury.py monitor --chain base_sepolia --interval 15
```

## Features

### Treasury Management
- **Multi-chain balance tracking** — Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia
- **USDC transfers** with memo and category tagging
- **Budget limits** with spending alerts (90% threshold)
- **Transaction history** with filtering by chain, category, counterparty

### Invoice System
- **Create invoices** with line items, counterparty, due date
- **On-chain payment** — invoices are paid by sending USDC on-chain
- **Partial payments** — pay invoices in installments
- **Overpayment handling** — detects and flags overpayments
- **Full audit trail** — Invoice # → Payment → Tx hash → Wallets → Timestamp → Status
- **Two-way linkage** — every payment references its invoice and vice versa

### CCTP Cross-Chain Bridging
- **Circle CCTP v2** for native USDC bridging between testnets
- **4-step flow:** approve → burn → attest → mint
- **Automatic attestation polling** from Circle's API
- **Transaction recording** for both burn and mint legs

### Reconciliation Engine
- **On-chain verification** — fetches Transfer events from chain
- **Internal vs on-chain matching** — detects discrepancies
- **Invoice payment verification** — confirms payments match records
- **Balance verification** — compares recorded vs actual on-chain balance

### FASB ASU 2023-08 Reporting
- **Balance sheet** with fair value measurement for digital assets
- **Income statement** with categorized expenses/revenue
- **Accounts receivable aging** (current, 30/60/90+ days)
- **Counterparty reports** — total invoiced, paid, outstanding per entity
- **Cost basis tracking** using specific identification method
- **Required disclosures** for significant crypto holdings

## Contract Addresses (Testnet)

| Chain | USDC | CCTP Domain |
|-------|------|-------------|
| Ethereum Sepolia | `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238` | 0 |
| Base Sepolia | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` | 6 |
| Arbitrum Sepolia | `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d` | 3 |

**CCTP v2 (all testnets):**
- TokenMessengerV2: `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA`
- MessageTransmitterV2: `0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275`

## Data Storage

All data persists in `data/treasury.db` (SQLite database):
- `transactions` — Full transaction ledger with indexes
- `invoices` — Invoice records with payment history
- `budgets` — Budget configurations
- `wallets` — Tracked wallet addresses
- `counters` — Monotonic counters (invoice numbering)
- `high_water_marks` — Reconciliation scan progress per chain
- `cctp_bridges` — Pending CCTP bridge state for resume

## Dependencies

- Python 3.11+
- web3.py 7.x
- requests (for CCTP attestation API)
- sqlite3 (stdlib)
