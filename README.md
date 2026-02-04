# USDC Treasury & Invoice Management

**QuickBooks for AI agents, settled in USDC.**

An [OpenClaw](https://openclaw.org) skill that provides complete treasury management and invoicing for AI agents, with on-chain USDC settlement on testnet.

## 🚀 Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure (just two env vars)
export TREASURY_PRIVATE_KEY=0xYourTestnetPrivateKey
export TREASURY_WALLET=0xYourWalletAddress  # optional, derived from key

# 3. Verify
python scripts/setup.py

# 4. Use
python scripts/treasury.py balance
```

Get testnet USDC at [faucet.circle.com](https://faucet.circle.com). Get testnet ETH from any Sepolia faucet.

## 🎯 What It Does

This skill turns any AI agent into a treasury manager:

1. **Track USDC balances** across Ethereum Sepolia, Base Sepolia, and Arbitrum Sepolia
2. **Create and pay invoices** with real on-chain USDC transfers
3. **Bridge USDC** between chains using Circle's CCTP v2
4. **Reconcile** on-chain transactions against internal records
5. **Generate reports** compliant with FASB ASU 2023-08
6. **Serve a REST API** for agent-to-agent invoicing and settlement

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                   AI Agent                       │
├─────────────────────────────────────────────────┤
│  treasury.py    │  invoices.py   │  reports.py   │
│  Balance mgmt   │  Invoice CRUD  │  FASB reports │
│  Transfers      │  On-chain pay  │  Balance sheet│
│  Budgets        │  Audit trail   │  Income stmt  │
├─────────────────────────────────────────────────┤
│  cctp.py        │  reconcile.py  │  server.py    │
│  Cross-chain    │  On-chain vs   │  REST API for │
│  CCTP v2 bridge │  internal match│  agent-to-    │
│                 │                │  agent comms   │
├─────────────────────────────────────────────────┤
│  config.py (env vars) │     db.py (SQLite)      │
├─────────────────────────────────────────────────┤
│         web3.py (EVM interaction layer)          │
├─────────────────────────────────────────────────┤
│  Ethereum Sepolia │ Base Sepolia │ Arb Sepolia   │
└─────────────────────────────────────────────────┘
```

## 📦 Structure

```
usdc-treasury/
├── SKILL.md              — Skill definition + full docs
├── README.md             — This file
├── CHANGELOG.md          — Version history
├── requirements.txt      — Python dependencies
├── scripts/
│   ├── __init__.py       — Package exports (for import)
│   ├── config.py         — Chain configs, ABIs, env-var-driven settings
│   ├── db.py             — SQLite database layer
│   ├── setup.py          — First-run validator
│   ├── server.py         — REST API for inter-agent protocol
│   ├── treasury.py       — Balance tracking, transfers, budgets
│   ├── invoices.py       — Invoice CRUD, on-chain payment
│   ├── reconcile.py      — Reconciliation engine
│   ├── reports.py        — FASB-compliant reporting
│   └── cctp.py           — Cross-chain USDC bridging
├── references/
│   └── fasb-guide.md     — FASB ASU 2023-08 reference
└── data/
    └── treasury.db       — SQLite database (auto-created)
```

## ⚙️ Configuration

All configuration via environment variables — no config files, no hardcoded paths.

| Variable | Description | Default |
|----------|-------------|---------|
| `TREASURY_PRIVATE_KEY` | EVM private key (hex) | **Required** |
| `TREASURY_WALLET` | Wallet address | Derived from key |
| `TREASURY_DATA_DIR` | Data directory path | `<skill>/data/` |
| `TREASURY_API_KEY` | REST API Bearer token | None (no auth) |
| `TREASURY_PORT` | REST API port | `9090` |
| `TREASURY_RPC_ETHEREUM_SEPOLIA` | Custom RPC URL | publicnode.com |
| `TREASURY_RPC_BASE_SEPOLIA` | Custom RPC URL | publicnode.com |
| `TREASURY_RPC_ARBITRUM_SEPOLIA` | Custom RPC URL | publicnode.com |
| `TREASURY_SECRET_CMD` | Shell command to retrieve key | None |

See [SKILL.md](SKILL.md#environment-variables) for full details including Docker and secret manager examples.

## 📦 Python Package Import

```python
from skills.usdc_treasury.scripts import (
    get_balances, transfer_usdc,
    create_invoice, pay_invoice, list_invoices,
    reconcile, balance_sheet, treasury_summary,
    bridge_usdc,
)

print(get_balances()["total_usdc"])
```

## 🌐 Inter-Agent REST API

```bash
# Start the server
TREASURY_API_KEY=secret python scripts/server.py

# Another agent sends us an invoice
curl -X POST http://localhost:9090/invoices \
  -H "Authorization: Bearer secret" \
  -H "Content-Type: application/json" \
  -d '{"counterparty_name": "Agent A", "counterparty_address": "0x...",
       "items": [{"description": "Service", "quantity": 1, "unit_price": 50}]}'

# Pay it
curl -X POST http://localhost:9090/invoices/INV-0001/pay \
  -H "Authorization: Bearer secret"
```

See [SKILL.md](SKILL.md#inter-agent-protocol-rest-api) for full API docs.

## 📊 FASB ASU 2023-08 Compliance

- **Fair value measurement** — USDC valued at market
- **Changes through net income** — Gains/losses in income statement
- **Required disclosures** — Holdings, cost basis, fair value
- **Aging schedules** — Receivables by age
- **Cost basis tracking** — Specific identification method

## 🔗 Supported Chains (Testnet)

| Chain | USDC Address | CCTP Domain |
|-------|-------------|-------------|
| Ethereum Sepolia | `0x1c7D...7238` | 0 |
| Base Sepolia | `0x036C...CF7e` | 6 |
| Arbitrum Sepolia | `0x75fa...46AA4d` | 3 |

## 🔐 Security

- **Testnet only** — mainnet chain IDs rejected at startup
- **No secrets in code** — everything via env vars
- **API auth** via Bearer token
- **Transaction signing** happens locally
- **Portable** — works on Linux, macOS, Docker, CI

## 🏆 Built For

[USDC Hackathon on Moltbook](https://moltbook.com) — Demonstrating how AI agents can manage financial operations with real on-chain settlement.

**Version 2.1.0** · [Changelog](CHANGELOG.md) · [Full Docs](SKILL.md)

## License

MIT
