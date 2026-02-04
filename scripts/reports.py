#!/usr/bin/env python3
"""
USDC Treasury - Reporting & FASB ASU 2023-08 Compliance
Financial reports, balance sheets, and regulatory categorization
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    CHAINS, TREASURY_WALLET,
    INVOICES_FILE, TRANSACTIONS_FILE, BUDGETS_FILE,
    load_json
)
from treasury import get_all_balances


# ============================================================
# FASB ASU 2023-08 Categorization
# ============================================================

# Under FASB ASU 2023-08:
# - Digital assets are measured at fair value with changes in net income
# - USDC as a stablecoin pegged to USD is categorized differently than volatile crypto
# - Stablecoins may qualify as "financial instruments" under ASC 825 if fully reserved
# - For accounting purposes, USDC held = cash equivalent at fair value

FASB_CATEGORIES = {
    "digital_asset_stablecoin": {
        "description": "Fully-reserved USD-pegged stablecoin (USDC)",
        "measurement": "Fair value through net income (ASU 2023-08)",
        "classification": "Digital asset - stablecoin",
        "balance_sheet_line": "Digital assets, at fair value",
        "notes": [
            "USDC is issued by Circle, fully reserved in cash and US Treasuries",
            "Fair value approximates 1:1 USD peg",
            "Subject to fair value measurement per ASU 2023-08 if classified as intangible",
            "May alternatively be classified as cash equivalent if meeting ASC 230 criteria",
        ],
    },
    "accounts_receivable": {
        "description": "Outstanding invoices denominated in USDC",
        "measurement": "Amortized cost",
        "classification": "Accounts receivable - digital asset denominated",
        "balance_sheet_line": "Accounts receivable, net",
    },
    "accounts_payable": {
        "description": "Payable invoices denominated in USDC",
        "measurement": "Amortized cost",
        "classification": "Accounts payable - digital asset denominated",
        "balance_sheet_line": "Accounts payable",
    },
}

EXPENSE_CATEGORIES = {
    "services": "Operating expenses - Services",
    "infrastructure": "Operating expenses - Infrastructure",
    "development": "Operating expenses - Development",
    "marketing": "Operating expenses - Marketing",
    "payroll": "Operating expenses - Compensation",
    "bridging_fees": "Operating expenses - Cross-chain fees",
    "gas_fees": "Operating expenses - Network fees",
    "uncategorized": "Other expenses",
}

INCOME_CATEGORIES = {
    "service_revenue": "Revenue - Services",
    "product_revenue": "Revenue - Products",
    "interest": "Other income - Interest",
    "incoming_transfer": "Other income - Transfers received",
}


# ============================================================
# Reports
# ============================================================

def generate_balance_sheet(as_of=None):
    """
    Generate a balance sheet with FASB ASU 2023-08 compliant categorization.
    
    Assets:
    - Digital assets (USDC on each chain) at fair value
    - Accounts receivable (outstanding invoices)
    
    Liabilities:
    - Accounts payable (invoices we owe — not tracked yet, placeholder)
    """
    as_of = as_of or datetime.now(timezone.utc).isoformat()
    
    # Get current balances
    balances = get_all_balances()
    invoices = load_json(INVOICES_FILE)
    
    # Assets
    digital_assets = []
    total_digital = Decimal("0")
    for chain_bal in balances.get("chains", []):
        if "error" in chain_bal:
            continue
        usdc = Decimal(chain_bal["usdc_balance"])
        digital_assets.append({
            "chain": chain_bal["chain"],
            "usdc_balance": str(usdc),
            "fair_value_usd": str(usdc),  # 1:1 peg
            "cost_basis_usd": str(usdc),  # Stablecoin - cost = fair value
            "unrealized_gain_loss": "0.00",
            "fasb_category": FASB_CATEGORIES["digital_asset_stablecoin"],
        })
        total_digital += usdc
    
    # Accounts receivable (pending/partial invoices where we're owed money)
    ar_items = []
    total_ar = Decimal("0")
    for inv in invoices:
        if inv["status"] in ("pending", "partial"):
            remaining = Decimal(inv["remaining_usdc"])
            ar_items.append({
                "invoice_number": inv["invoice_number"],
                "counterparty": inv["counterparty"]["name"],
                "total": inv["total_usdc"],
                "paid": inv["paid_usdc"],
                "remaining": str(remaining),
                "due_date": inv["due_date"],
                "aging_category": _aging_category(inv["due_date"]),
            })
            total_ar += remaining
    
    balance_sheet = {
        "as_of": as_of,
        "wallet": TREASURY_WALLET,
        "fasb_standard": "ASU 2023-08 (Accounting for and Disclosure of Crypto Assets)",
        
        "assets": {
            "digital_assets_at_fair_value": {
                "items": digital_assets,
                "total_usd": str(total_digital),
                "measurement": "Fair value through net income",
            },
            "accounts_receivable": {
                "items": ar_items,
                "total_usd": str(total_ar),
                "measurement": "Amortized cost",
            },
            "total_assets_usd": str(total_digital + total_ar),
        },
        
        "equity": {
            "retained_earnings": str(total_digital + total_ar),
            "note": "Simplified — no liabilities tracked in current version",
        },
        
        "disclosures": {
            "cost_basis_method": "Specific identification",
            "fair_value_source": "USD peg (1:1 USDC:USD)",
            "impairment": "N/A for fair-value-through-income measurement",
            "significant_holdings": [
                {
                    "asset": "USDC (Circle)",
                    "total_held": str(total_digital),
                    "cost_basis": str(total_digital),
                    "fair_value": str(total_digital),
                    "chains": [a["chain"] for a in digital_assets],
                }
            ],
        },
    }
    
    return balance_sheet


def _aging_category(due_date_str):
    """Categorize receivables by age"""
    try:
        due = datetime.fromisoformat(due_date_str)
        now = datetime.now(timezone.utc)
        days = (now - due).days
        if days < 0:
            return "current"
        elif days <= 30:
            return "1-30 days past due"
        elif days <= 60:
            return "31-60 days past due"
        elif days <= 90:
            return "61-90 days past due"
        else:
            return "90+ days past due"
    except:
        return "unknown"


def generate_income_statement(period_start=None, period_end=None):
    """
    Generate income statement for a period.
    Categorizes transactions by type with FASB compliance.
    """
    txs = load_json(TRANSACTIONS_FILE)
    
    now = datetime.now(timezone.utc)
    if not period_start:
        period_start = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
    if not period_end:
        period_end = now.isoformat()
    
    # Filter by period
    period_txs = [
        t for t in txs
        if period_start <= t.get("timestamp", "") <= period_end
        and t.get("status") == "confirmed"
    ]
    
    # Categorize
    expenses = defaultdict(lambda: Decimal("0"))
    income = defaultdict(lambda: Decimal("0"))
    
    for tx in period_txs:
        amount = Decimal(tx.get("amount_usdc", "0"))
        cat = tx.get("category", "uncategorized")
        tx_type = tx.get("type", "")
        
        if tx_type in ("transfer", "invoice_payment", "cctp_bridge"):
            expense_label = EXPENSE_CATEGORIES.get(cat, f"Other expenses - {cat}")
            expenses[expense_label] += amount
        elif tx_type in ("incoming", "received"):
            income_label = INCOME_CATEGORIES.get(cat, f"Other income - {cat}")
            income[income_label] += amount
    
    total_income = sum(income.values())
    total_expenses = sum(expenses.values())
    
    return {
        "period_start": period_start,
        "period_end": period_end,
        "income": {k: str(v) for k, v in sorted(income.items())},
        "total_income_usd": str(total_income),
        "expenses": {k: str(v) for k, v in sorted(expenses.items())},
        "total_expenses_usd": str(total_expenses),
        "net_income_usd": str(total_income - total_expenses),
        "fasb_note": "Digital asset transactions measured at fair value per ASU 2023-08",
    }


def generate_counterparty_report(counterparty_name=None):
    """Report by counterparty — total invoiced, paid, outstanding"""
    invoices = load_json(INVOICES_FILE)
    
    counterparties = defaultdict(lambda: {
        "total_invoiced": Decimal("0"),
        "total_paid": Decimal("0"),
        "total_outstanding": Decimal("0"),
        "invoice_count": 0,
        "invoices": [],
    })
    
    for inv in invoices:
        cp = inv["counterparty"]["name"]
        if counterparty_name and counterparty_name.lower() not in cp.lower():
            continue
        
        counterparties[cp]["total_invoiced"] += Decimal(inv["total_usdc"])
        counterparties[cp]["total_paid"] += Decimal(inv["paid_usdc"])
        counterparties[cp]["total_outstanding"] += Decimal(inv["remaining_usdc"])
        counterparties[cp]["invoice_count"] += 1
        counterparties[cp]["invoices"].append({
            "number": inv["invoice_number"],
            "status": inv["status"],
            "total": inv["total_usdc"],
            "paid": inv["paid_usdc"],
            "remaining": inv["remaining_usdc"],
        })
    
    result = {}
    for cp, data in counterparties.items():
        result[cp] = {
            "total_invoiced_usdc": str(data["total_invoiced"]),
            "total_paid_usdc": str(data["total_paid"]),
            "total_outstanding_usdc": str(data["total_outstanding"]),
            "invoice_count": data["invoice_count"],
            "invoices": data["invoices"],
        }
    
    return result


def generate_chain_report():
    """Report broken down by chain — balances, tx counts, volume"""
    txs = load_json(TRANSACTIONS_FILE)
    balances = get_all_balances()
    
    result = {}
    for chain_bal in balances.get("chains", []):
        ck = chain_bal.get("chain_key", "")
        chain_txs = [t for t in txs if t.get("chain") == ck]
        
        volume = sum(Decimal(t.get("amount_usdc", "0")) for t in chain_txs)
        
        result[ck] = {
            "chain_name": chain_bal.get("chain", ck),
            "current_usdc_balance": chain_bal.get("usdc_balance", "0"),
            "current_eth_balance": chain_bal.get("eth_balance", "0"),
            "transaction_count": len(chain_txs),
            "total_volume_usdc": str(volume),
            "categories": _categorize_chain_txs(chain_txs),
        }
    
    return result


def _categorize_chain_txs(txs):
    """Categorize transactions for a chain"""
    cats = defaultdict(lambda: {"count": 0, "volume": Decimal("0")})
    for tx in txs:
        cat = tx.get("category", "uncategorized")
        cats[cat]["count"] += 1
        cats[cat]["volume"] += Decimal(tx.get("amount_usdc", "0"))
    
    return {k: {"count": v["count"], "volume_usdc": str(v["volume"])} for k, v in cats.items()}


def generate_treasury_summary():
    """High-level treasury summary combining all data"""
    balances = get_all_balances()
    invoices = load_json(INVOICES_FILE)
    txs = load_json(TRANSACTIONS_FILE)
    budgets = load_json(BUDGETS_FILE)
    
    pending_invoices = [i for i in invoices if i["status"] in ("pending", "partial")]
    paid_invoices = [i for i in invoices if i["status"] == "paid"]
    
    total_ar = sum(Decimal(i["remaining_usdc"]) for i in pending_invoices)
    total_paid = sum(Decimal(i["paid_usdc"]) for i in invoices)
    total_volume = sum(Decimal(t.get("amount_usdc", "0")) for t in txs if t.get("status") == "confirmed")
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": TREASURY_WALLET,
        "total_usdc_across_chains": balances.get("total_usdc", "0"),
        "chain_balances": {
            c.get("chain_key", c.get("chain", "")): c.get("usdc_balance", "0")
            for c in balances.get("chains", []) if "error" not in c
        },
        "invoices": {
            "total": len(invoices),
            "pending": len([i for i in invoices if i["status"] == "pending"]),
            "partial": len([i for i in invoices if i["status"] == "partial"]),
            "paid": len(paid_invoices),
            "cancelled": len([i for i in invoices if i["status"] == "cancelled"]),
        },
        "accounts_receivable_usdc": str(total_ar),
        "total_paid_usdc": str(total_paid),
        "transactions": {
            "total": len(txs),
            "confirmed": len([t for t in txs if t.get("status") == "confirmed"]),
            "total_volume_usdc": str(total_volume),
        },
        "active_budgets": len(budgets),
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC Treasury Reports")
    sub = parser.add_subparsers(dest="command")
    
    # Balance sheet
    bs = sub.add_parser("balance-sheet", help="FASB-compliant balance sheet")
    
    # Income statement
    inc = sub.add_parser("income-statement", help="Income statement")
    inc.add_argument("--start", help="Period start (ISO date)")
    inc.add_argument("--end", help="Period end (ISO date)")
    
    # Counterparty report
    cp = sub.add_parser("counterparty", help="Counterparty report")
    cp.add_argument("--name", help="Filter by counterparty name")
    
    # Chain report
    sub.add_parser("chain", help="Per-chain report")
    
    # Treasury summary
    sub.add_parser("summary", help="Treasury summary")
    
    args = parser.parse_args()
    
    if args.command == "balance-sheet":
        result = generate_balance_sheet()
    elif args.command == "income-statement":
        result = generate_income_statement(args.start, args.end)
    elif args.command == "counterparty":
        result = generate_counterparty_report(args.name)
    elif args.command == "chain":
        result = generate_chain_report()
    elif args.command == "summary":
        result = generate_treasury_summary()
    else:
        parser.print_help()
        return
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
