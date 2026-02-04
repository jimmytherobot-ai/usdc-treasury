---
name: usdc-treasury
version: 2.1.0
description: "USDC Treasury & Invoice Management — QuickBooks for AI agents, settled in USDC on-chain. Multi-chain testnet treasury tracking, invoicing with on-chain payment settlement, CCTP bridging, reconciliation, FASB ASU 2023-08 compliant reporting, and inter-agent REST API."
author: jimmytherobot-ai
homepage: https://github.com/jimmytherobot-ai/usdc-treasury
tags: [usdc, treasury, invoicing, accounting, cctp, stablecoin, defi]
chains: [ethereum-sepolia, base-sepolia, arbitrum-sepolia]
---

# USDC Treasury & Invoice Management

**QuickBooks for AI agents, settled in USDC.**

A complete treasury management and invoicing system built on USDC testnet. Track balances across chains, create and pay invoices with on-chain settlement, bridge USDC via CCTP, and generate FASB-compliant reports.

No macOS dependencies. No hardcoded paths. Just env vars, Python, and a wallet.

## Getting Started

You just cloned this repo. Here's everything you need.

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

That's `web3` and `requests`. Everything else is stdlib.

### 2. Set your wallet

```bash
# Your EVM private key (testnet only!)
export TREASURY_PRIVATE_KEY=0xYourPrivateKeyHere

# Optional — wallet address (auto-derived from key if not set)
export TREASURY_WALLET=0xYourWalletAddress
```

That's the minimum. The skill derives your wallet address from the key if `TREASURY_WALLET` isn't set.

### 3. Run setup to verify everything

```bash
python scripts/setup.py
```

This checks Python version, dependencies, RPC connectivity, wallet config, and shows your balances. Fix any ❌ items it flags.

### 4. Get testnet tokens

- **Testnet ETH** (for gas): Use a Sepolia faucet — [Google Cloud Faucet](https://cloud.google.com/application/web3/faucet/ethereum/sepolia), [Alchemy Faucet](https://www.alchemy.com/faucets/ethereum-sepolia)
- **Testnet USDC**: https://faucet.circle.com — select the chain you want

### 5. Verify it works

```bash
# Check balances across all chains
python scripts/treasury.py balance

# Create an invoice
python scripts/invoices.py create \
  --counterparty-name "Test Corp" \
  --counterparty-address 0x000000000000000000000000000000000000dEaD \
  --items '[{"description": "Test service", "quantity": 1, "unit_price": 1.00}]' \
  --chain base_sepolia

# Pay it (sends real testnet USDC)
python scripts/invoices.py pay INV-0001

# Check the audit trail
python scripts/invoices.py audit INV-0001
```

You're live. Everything below is reference.

---

## Environment Variables

**All configuration is via env vars.** No config files to edit, no secrets in code.

### Required

| Variable | Description |
|----------|-------------|
| `TREASURY_PRIVATE_KEY` | EVM private key (hex, with or without `0x` prefix) |

Or use the common alias: `ETH_PRIVATE_KEY`

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `TREASURY_WALLET` | Wallet address | Derived from private key |
| `TREASURY_DATA_DIR` | Where to store the SQLite database | `<skill>/data/` |
| `TREASURY_API_KEY` | Bearer token for the REST API server | None (no auth) |
| `TREASURY_PORT` | REST API server port | `9090` |
| `TREASURY_RPC_ETHEREUM_SEPOLIA` | Custom RPC for Ethereum Sepolia | publicnode.com |
| `TREASURY_RPC_BASE_SEPOLIA` | Custom RPC for Base Sepolia | publicnode.com |
| `TREASURY_RPC_ARBITRUM_SEPOLIA` | Custom RPC for Arbitrum Sepolia | publicnode.com |
| `TREASURY_SECRET_CMD` | Shell command that prints private key to stdout | None |
| `TREASURY_KEYCHAIN_ACCOUNT` | macOS Keychain account (macOS only) | None |
| `TREASURY_KEYCHAIN_SERVICE` | macOS Keychain service (macOS only) | None |

**Private key resolution order:**
1. `TREASURY_PRIVATE_KEY` env var
2. `ETH_PRIVATE_KEY` env var
3. `TREASURY_SECRET_CMD` (runs command, reads stdout — works with any secret manager)
4. macOS Keychain (only if on macOS and `TREASURY_KEYCHAIN_*` vars are set)

### Docker Example

```bash
docker run -e TREASURY_PRIVATE_KEY=0x... \
           -e TREASURY_WALLET=0x... \
           -e TREASURY_DATA_DIR=/data \
           -v treasury-data:/data \
           your-agent-image
```

### Secret Manager Integration

The `TREASURY_SECRET_CMD` env var lets you plug in any secret backend:

```bash
# 1Password CLI
export TREASURY_SECRET_CMD="op read op://Vault/eth-key/password"

# HashiCorp Vault
export TREASURY_SECRET_CMD="vault kv get -field=key secret/treasury"

# AWS Secrets Manager
export TREASURY_SECRET_CMD="aws secretsmanager get-secret-value --secret-id treasury-key --query SecretString --output text"

# Custom script
export TREASURY_SECRET_CMD="/path/to/get-secret.sh treasury-key"
```

---

## Quick Reference

```bash
# All commands are run from the skill directory
cd usdc-treasury
```

### Treasury

```bash
# Check all balances
python scripts/treasury.py balance

# Check specific chain
python scripts/treasury.py balance --chain ethereum_sepolia

# Transfer USDC
python scripts/treasury.py transfer ethereum_sepolia 0xRECIPIENT 10.00 --memo "Payment" --category services

# Transaction history
python scripts/treasury.py history --chain ethereum_sepolia --category services

# Set budget
python scripts/treasury.py budget set --chain ethereum_sepolia --category services --limit 1000 --period monthly

# Check budget status
python scripts/treasury.py budget status
```

### Invoices

```bash
# Create invoice (we owe them)
python scripts/invoices.py create \
  --counterparty-name "Acme Corp" \
  --counterparty-address 0xRECIPIENT \
  --items '[{"description": "Consulting", "quantity": 10, "unit_price": 50}]' \
  --chain ethereum_sepolia \
  --due-days 30 \
  --category services

# Create receivable (they owe us)
python scripts/invoices.py receive \
  --counterparty-name "Client Corp" \
  --counterparty-address 0xCLIENT \
  --items '[{"description": "Consulting", "quantity": 5, "unit_price": 100}]' \
  --chain base_sepolia

# List / filter
python scripts/invoices.py list --status pending
python scripts/invoices.py list --type receivable

# Pay invoice (full or partial)
python scripts/invoices.py pay INV-0001
python scripts/invoices.py pay INV-0001 --amount 100

# Audit trail
python scripts/invoices.py audit INV-0001

# Cancel invoice
python scripts/invoices.py cancel INV-0001
```

### Cross-Chain Bridge (CCTP v2)

```bash
# Bridge USDC between chains
python scripts/cctp.py bridge ethereum_sepolia base_sepolia 10.00

# Check bridge status
python scripts/cctp.py status BURN_TX_HASH

# Resume a pending bridge
python scripts/cctp.py complete BURN_TX_HASH

# List pending bridges
python scripts/cctp.py pending
```

### Reconciliation

```bash
# Full reconciliation (all chains)
python scripts/reconcile.py full

# Reconcile specific chain
python scripts/reconcile.py full --chain ethereum_sepolia

# Reconcile specific invoice
python scripts/reconcile.py invoice INV-0001
```

### Reports

```bash
# FASB-compliant balance sheet
python scripts/reports.py balance-sheet

# Income statement
python scripts/reports.py income-statement --start 2026-02-01 --end 2026-02-28

# Period comparison
python scripts/reports.py compare --start 2026-02-01 --end 2026-02-28

# Counterparty report
python scripts/reports.py counterparty --name "Acme"

# Per-chain report
python scripts/reports.py chain

# Treasury summary (quick overview)
python scripts/reports.py summary

# CSV output (any report)
python scripts/reports.py summary --format csv
```

### Wallet Management

```bash
python scripts/treasury.py wallet add 0xADDRESS --name "Cold Storage"
python scripts/treasury.py wallet list
python scripts/treasury.py wallet remove 0xADDRESS
```

### Event Monitor

```bash
# Scan for incoming transfers (one-shot)
python scripts/treasury.py watch --chain base_sepolia

# Continuous monitoring (Ctrl-C to stop)
python scripts/treasury.py monitor --interval 15
```

---

## Python Package Usage

The skill is importable as a Python package:

```python
from skills.usdc_treasury.scripts import (
    get_balances, transfer_usdc,
    create_invoice, pay_invoice, list_invoices, get_invoice_audit_trail,
    reconcile,
    balance_sheet, income_statement, treasury_summary,
    bridge_usdc,
)

# Check balances across all chains
balances = get_balances()
print(f"Total USDC: {balances['total_usdc']}")

# Create and pay an invoice
inv = create_invoice(
    counterparty_name="Agent B",
    counterparty_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
    line_items=[{"description": "API calls", "quantity": 1000, "unit_price": 0.01}],
    chain_key="base_sepolia",
)
result = pay_invoice(inv["invoice_number"])
print(f"Paid: {result['payment']['explorer_url']}")

# Generate FASB-compliant balance sheet
sheet = balance_sheet()
```

---

## Inter-Agent Protocol (REST API)

The treasury exposes a REST API for agent-to-agent USDC invoicing and settlement.

### Start the Server

```bash
export TREASURY_PRIVATE_KEY=0x...
export TREASURY_API_KEY=your-secret-key
python scripts/server.py --port 9090
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/balance` | Treasury balances (all chains) |
| `GET` | `/balance?chain=base_sepolia` | Balance on specific chain |
| `GET` | `/invoices` | List invoices (filterable) |
| `GET` | `/invoices?status=pending&type=payable` | Filter by status/type |
| `GET` | `/invoices/INV-0001` | Get invoice details |
| `GET` | `/invoices/INV-0001/audit` | Full audit trail |
| `POST` | `/invoices` | Create/receive an invoice |
| `POST` | `/invoices/INV-0001/pay` | Pay an invoice on-chain |

### Authentication

All requests require a Bearer token when `TREASURY_API_KEY` is set:
```
Authorization: Bearer your-secret-key
```

### Example: Agent A Invoices Agent B

**Agent A** (vendor) sends an invoice to **Agent B** (payer):

```bash
# Agent A → Agent B's treasury API
curl -X POST http://agent-b:9090/invoices \
  -H "Authorization: Bearer agent-b-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "counterparty_name": "Agent A",
    "counterparty_address": "0xAgentA...",
    "items": [{"description": "Data processing", "quantity": 500, "unit_price": 0.10}],
    "chain": "base_sepolia",
    "due_days": 7,
    "memo": "January data processing"
  }'
```

**Agent B** reviews and pays:

```bash
curl -X POST http://agent-b:9090/invoices/INV-0005/pay \
  -H "Authorization: Bearer agent-b-api-key"
```

**Agent A** confirms receipt:

```bash
python scripts/treasury.py watch --chain base_sepolia
```

### Flow Diagram

```
Agent A (Vendor)              Agent B (Payer)
     │                              │
     │── POST /invoices ──────────→ │  (A sends invoice to B)
     │                              │  Invoice created: INV-0005
     │                              │
     │                              │── POST /invoices/INV-0005/pay
     │                              │  (B pays on-chain)
     │                              │  USDC tx confirmed ✓
     │                              │
     │← on-chain USDC ────────────│
     │  (A detects via watch)       │
     │  Auto-matched to receivable  │
     │                              │
     │── reconcile ────────────────│  Both agents reconcile ✓
```

---

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

---

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

All data persists in SQLite (`data/treasury.db` by default, override with `TREASURY_DATA_DIR`):
- `transactions` — Full transaction ledger with indexes
- `invoices` — Invoice records with payment history
- `budgets` — Budget configurations
- `wallets` — Tracked wallet addresses
- `counters` — Monotonic counters (invoice numbering)
- `high_water_marks` — Reconciliation scan progress per chain
- `cctp_bridges` — Pending CCTP bridge state for resume

## Dependencies

- Python 3.9+ (3.11+ recommended)
- web3.py 7.x
- requests
- sqlite3 (stdlib)

Install: `pip install -r requirements.txt`
