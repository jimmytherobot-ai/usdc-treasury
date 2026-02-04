#!/usr/bin/env python3
"""
USDC Treasury - Reporting & FASB ASU 2023-08 Compliance
Financial reports, balance sheets, and regulatory categorization.
Supports date filtering, CSV output, and period comparison.
"""

import sys
import os
import json
import csv
import io
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from config import CHAINS, TREASURY_WALLET
import db
from treasury import get_all_balances


# ============================================================
# FASB ASU 2023-08 Categorization
# ============================================================

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
# Output Formatting
# ============================================================

def _output(data, fmt="json"):
    """Output data in the requested format."""
    if fmt == "csv":
        return _to_csv(data)
    return json.dumps(data, indent=2)


def _to_csv(data):
    """Convert data to CSV string. Handles dicts, lists of dicts, nested structures."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        # List of dicts - straightforward
        headers = list(data[0].keys())
        writer.writerow(headers)
        for row in data:
            writer.writerow([_flatten_value(row.get(h, "")) for h in headers])
    elif isinstance(data, dict):
        # Single dict - flatten to key/value rows
        _dict_to_csv(writer, data)
    else:
        writer.writerow(["value"])
        writer.writerow([str(data)])
    
    return output.getvalue()


def _dict_to_csv(writer, d, prefix=""):
    """Recursively flatten a dict to CSV rows."""
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _dict_to_csv(writer, value, full_key)
        elif isinstance(value, list):
            if len(value) > 0 and isinstance(value[0], dict):
                # Write list of dicts as sub-table
                writer.writerow([])
                writer.writerow([full_key])
                headers = list(value[0].keys())
                writer.writerow(headers)
                for item in value:
                    writer.writerow([_flatten_value(item.get(h, "")) for h in headers])
            else:
                writer.writerow([full_key, _flatten_value(value)])
        else:
            writer.writerow([full_key, _flatten_value(value)])


def _flatten_value(v):
    """Flatten a value for CSV output."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return str(v) if v is not None else ""


# ============================================================
# Reports
# ============================================================

def generate_balance_sheet(as_of=None, wallet=None):
    """
    Generate a balance sheet with FASB ASU 2023-08 compliant categorization.
    """
    wallet = wallet or TREASURY_WALLET
    as_of = as_of or datetime.now(timezone.utc).isoformat()
    
    # Get current balances
    balances = get_all_balances(wallet)
    invoices = db.list_invoices(wallet=wallet)
    
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
            "fair_value_usd": str(usdc),
            "cost_basis_usd": str(usdc),
            "unrealized_gain_loss": "0.00",
            "fasb_category": FASB_CATEGORIES["digital_asset_stablecoin"],
        })
        total_digital += usdc
    
    # Accounts receivable (pending/partial invoices)
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
                "type": inv.get("invoice_type", "payable"),
            })
            total_ar += remaining
    
    balance_sheet = {
        "as_of": as_of,
        "wallet": wallet,
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
    except Exception:
        return "unknown"


def generate_income_statement(period_start=None, period_end=None, wallet=None):
    """
    Generate income statement for a period.
    Categorizes transactions by type with FASB compliance.
    """
    now = datetime.now(timezone.utc)
    if not period_start:
        period_start = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
    if not period_end:
        period_end = now.isoformat()
    
    txs = db.get_transactions(start=period_start, end=period_end, wallet=wallet, limit=None)
    
    # Filter confirmed
    period_txs = [t for t in txs if t.get("status") == "confirmed"]
    
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
        elif tx_type in ("incoming", "received", "incoming_payment"):
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


def generate_counterparty_report(counterparty_name=None, start=None, end=None, wallet=None):
    """Report by counterparty — total invoiced, paid, outstanding"""
    invoices = db.list_invoices(start=start, end=end, wallet=wallet)
    
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
        if inv["status"] not in ("cancelled",):
            counterparties[cp]["total_outstanding"] += Decimal(inv["remaining_usdc"])
        counterparties[cp]["invoice_count"] += 1
        counterparties[cp]["invoices"].append({
            "number": inv["invoice_number"],
            "status": inv["status"],
            "total": inv["total_usdc"],
            "paid": inv["paid_usdc"],
            "remaining": inv["remaining_usdc"],
            "type": inv.get("invoice_type", "payable"),
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


def generate_chain_report(start=None, end=None, wallet=None):
    """Report broken down by chain — balances, tx counts, volume"""
    wallet = wallet or TREASURY_WALLET
    txs = db.get_transactions(start=start, end=end, wallet=wallet, limit=None)
    balances = get_all_balances(wallet)
    
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


def generate_treasury_summary(start=None, end=None, wallet=None):
    """High-level treasury summary combining all data"""
    wallet = wallet or TREASURY_WALLET
    balances = get_all_balances(wallet)
    invoices = db.list_invoices(start=start, end=end, wallet=wallet)
    txs = db.get_transactions(start=start, end=end, wallet=wallet, limit=None)
    budgets = db.get_budgets()
    
    pending_invoices = [i for i in invoices if i["status"] in ("pending", "partial")]
    paid_invoices = [i for i in invoices if i["status"] == "paid"]
    
    total_ar = sum(Decimal(i["remaining_usdc"]) for i in pending_invoices)
    total_paid = sum(Decimal(i["paid_usdc"]) for i in invoices)
    total_volume = sum(Decimal(t.get("amount_usdc", "0")) for t in txs if t.get("status") == "confirmed")
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": wallet,
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
# Period Comparison
# ============================================================

def _parse_period_dates(start, end):
    """Parse start/end to datetime objects."""
    if start:
        s = datetime.fromisoformat(start)
    else:
        s = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if end:
        e = datetime.fromisoformat(end)
    else:
        e = datetime.now(timezone.utc)
    return s, e


def generate_period_comparison(start=None, end=None, wallet=None):
    """
    Compare current period vs previous period.
    If start/end given, previous period is the same duration immediately before.
    """
    current_start, current_end = _parse_period_dates(start, end)
    duration = current_end - current_start
    prev_start = current_start - duration
    prev_end = current_start
    
    current = generate_income_statement(
        current_start.isoformat(), current_end.isoformat(), wallet
    )
    previous = generate_income_statement(
        prev_start.isoformat(), prev_end.isoformat(), wallet
    )
    
    # Calculate changes
    cur_income = Decimal(current["total_income_usd"])
    prev_income = Decimal(previous["total_income_usd"])
    cur_expenses = Decimal(current["total_expenses_usd"])
    prev_expenses = Decimal(previous["total_expenses_usd"])
    cur_net = Decimal(current["net_income_usd"])
    prev_net = Decimal(previous["net_income_usd"])
    
    def pct_change(cur, prev):
        if prev == 0:
            return "N/A" if cur == 0 else "+∞"
        return f"{float((cur - prev) / abs(prev) * 100):+.1f}%"
    
    return {
        "current_period": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
            "income": current["total_income_usd"],
            "expenses": current["total_expenses_usd"],
            "net_income": current["net_income_usd"],
        },
        "previous_period": {
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
            "income": previous["total_income_usd"],
            "expenses": previous["total_expenses_usd"],
            "net_income": previous["net_income_usd"],
        },
        "changes": {
            "income_change": str(cur_income - prev_income),
            "income_pct_change": pct_change(cur_income, prev_income),
            "expenses_change": str(cur_expenses - prev_expenses),
            "expenses_pct_change": pct_change(cur_expenses, prev_expenses),
            "net_income_change": str(cur_net - prev_net),
            "net_income_pct_change": pct_change(cur_net, prev_net),
        },
        "current_detail": current,
        "previous_detail": previous,
    }


# ============================================================
# CLI
# ============================================================

def _add_common_args(p):
    """Add common arguments to a subparser."""
    p.add_argument("--format", dest="output_format", choices=["json", "csv"],
                    default="json", help="Output format")
    p.add_argument("--start", help="Start date filter (ISO)")
    p.add_argument("--end", help="End date filter (ISO)")
    p.add_argument("--wallet", default=None)


def main():
    parser = argparse.ArgumentParser(description="USDC Treasury Reports")
    sub = parser.add_subparsers(dest="command")
    
    # Balance sheet
    bs = sub.add_parser("balance-sheet", help="FASB-compliant balance sheet")
    _add_common_args(bs)
    
    # Income statement
    inc = sub.add_parser("income-statement", help="Income statement")
    _add_common_args(inc)
    inc.add_argument("--compare-period", action="store_true", help="Show current vs previous period")
    
    # Counterparty report
    cp = sub.add_parser("counterparty", help="Counterparty report")
    _add_common_args(cp)
    cp.add_argument("--name", help="Filter by counterparty name")
    
    # Chain report
    ch = sub.add_parser("chain", help="Per-chain report")
    _add_common_args(ch)
    
    # Treasury summary
    sm = sub.add_parser("summary", help="Treasury summary")
    _add_common_args(sm)
    
    # Period comparison
    pc = sub.add_parser("compare", help="Period comparison")
    _add_common_args(pc)
    
    args = parser.parse_args()
    fmt = getattr(args, 'output_format', 'json') or "json"
    
    if args.command == "balance-sheet":
        result = generate_balance_sheet(wallet=args.wallet)
    elif args.command == "income-statement":
        if hasattr(args, 'compare_period') and args.compare_period:
            result = generate_period_comparison(
                getattr(args, 'start', None),
                getattr(args, 'end', None),
                getattr(args, 'wallet', None)
            )
        else:
            result = generate_income_statement(
                getattr(args, 'start', None),
                getattr(args, 'end', None),
                getattr(args, 'wallet', None)
            )
    elif args.command == "counterparty":
        result = generate_counterparty_report(
            args.name,
            getattr(args, 'start', None),
            getattr(args, 'end', None),
            getattr(args, 'wallet', None)
        )
    elif args.command == "chain":
        result = generate_chain_report(
            getattr(args, 'start', None),
            getattr(args, 'end', None),
            getattr(args, 'wallet', None)
        )
    elif args.command == "summary":
        result = generate_treasury_summary(
            getattr(args, 'start', None),
            getattr(args, 'end', None),
            getattr(args, 'wallet', None)
        )
    elif args.command == "compare":
        result = generate_period_comparison(
            getattr(args, 'start', None),
            getattr(args, 'end', None),
            getattr(args, 'wallet', None)
        )
    else:
        parser.print_help()
        return
    
    print(_output(result, fmt))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
