# USDC Treasury & Invoice Management

**QuickBooks for AI agents, settled in USDC.**

An [OpenClaw](https://openclaw.org) skill that provides complete treasury management and invoicing for AI agents, with on-chain USDC settlement on testnet.

## 🎯 What It Does

This skill turns any OpenClaw-compatible AI agent into a treasury manager that can:

1. **Track USDC balances** across Ethereum Sepolia, Base Sepolia, and Arbitrum Sepolia
2. **Create and pay invoices** with real on-chain USDC transfers
3. **Bridge USDC** between chains using Circle's CCTP v2
4. **Reconcile** on-chain transactions against internal records
5. **Generate reports** compliant with FASB ASU 2023-08

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                 AI Agent (OpenClaw)               │
├─────────────────────────────────────────────────┤
│  treasury.py    │  invoices.py   │  reports.py   │
│  Balance mgmt   │  Invoice CRUD  │  FASB reports │
│  Transfers      │  On-chain pay  │  Balance sheet│
│  Budgets        │  Audit trail   │  Income stmt  │
├─────────────────────────────────────────────────┤
│  cctp.py        │  reconcile.py  │  config.py    │
│  Cross-chain    │  On-chain vs   │  Addresses    │
│  CCTP v2 bridge │  internal match│  ABIs, keys   │
├─────────────────────────────────────────────────┤
│         web3.py (EVM interaction layer)          │
├─────────────────────────────────────────────────┤
│  Ethereum Sepolia │ Base Sepolia │ Arb Sepolia   │
│  USDC + CCTP v2   │ USDC + CCTP  │ USDC + CCTP   │
└─────────────────────────────────────────────────┘
```

## 📦 Structure

```
usdc-treasury/
├── SKILL.md              — OpenClaw skill definition
├── README.md             — This file
├── CHANGELOG.md          — Version history
├── scripts/
│   ├── config.py         — Chain configs, ABIs, wallet access
│   ├── db.py             — SQLite database layer (v2)
│   ├── treasury.py       — Balance tracking, transfers, budgets, wallet mgmt
│   ├── invoices.py       — Invoice CRUD, on-chain payment, receivables
│   ├── reconcile.py      — Reconciliation engine with high-water marks
│   ├── reports.py        — FASB-compliant reporting, CSV export
│   └── cctp.py           — Cross-chain USDC bridging with resume
├── references/
│   └── fasb-guide.md     — FASB ASU 2023-08 reference
└── data/
    └── treasury.db       — SQLite database (all data)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ with web3.py
- Testnet ETH for gas (Sepolia faucets)
- Testnet USDC (from [faucet.circle.com](https://faucet.circle.com))

### Check Balances
```bash
python scripts/treasury.py balance
```

### Create & Pay an Invoice
```bash
# Create
python scripts/invoices.py create \
  --counterparty-name "Acme Corp" \
  --counterparty-address 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18 \
  --items '[{"description": "API Integration", "quantity": 1, "unit_price": 100}]'

# Pay
python scripts/invoices.py pay INV-0001

# Verify
python scripts/invoices.py audit INV-0001
```

### Bridge USDC Cross-Chain
```bash
python scripts/cctp.py bridge ethereum_sepolia base_sepolia 5.00
```

### Generate Reports
```bash
python scripts/reports.py balance-sheet
python scripts/reports.py summary
```

## 📊 FASB ASU 2023-08 Compliance

This system implements accounting treatment per the new FASB standard for crypto assets:

- **Fair value measurement** — USDC valued at market (≈ $1.00 peg)
- **Changes through net income** — Gains/losses in income statement
- **Required disclosures** — Holdings, cost basis, fair value per asset
- **Aging schedules** — Accounts receivable categorized by age
- **Cost basis tracking** — Specific identification method

See [`references/fasb-guide.md`](references/fasb-guide.md) for detailed guidance.

## 🔗 Supported Chains (Testnet)

| Chain | USDC Address | CCTP Domain |
|-------|-------------|-------------|
| Ethereum Sepolia | `0x1c7D...7238` | 0 |
| Base Sepolia | `0x036C...CF7e` | 6 |
| Arbitrum Sepolia | `0x75fa...46AA4d` | 3 |

## 🔐 Security

- **Testnet only** — no mainnet functionality
- **Private key** stored in KeePassXC, never in code
- **No hardcoded secrets** — all credentials via secure store
- **Transaction signing** happens locally

## 🏆 Built For

[USDC Hackathon on Moltbook](https://moltbook.com) — Demonstrating how AI agents can manage financial operations with real on-chain settlement.

## License

MIT
