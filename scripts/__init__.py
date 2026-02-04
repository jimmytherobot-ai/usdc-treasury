"""
USDC Treasury — Python Package Exports

Usage:
    from skills.usdc_treasury.scripts import get_balances, transfer_usdc
    from skills.usdc_treasury.scripts import create_invoice, pay_invoice
"""

# Treasury
from .treasury import (
    get_balance,
    get_all_balances as get_balances,
    transfer_usdc,
    get_transactions as get_transaction_history,
    set_budget,
    get_budget_status,
    watch_incoming,
    wallet_add,
    wallet_list,
    wallet_remove,
)

# Invoices
from .invoices import (
    create_invoice,
    create_receivable_invoice,
    pay_invoice,
    list_invoices,
    get_invoice,
    cancel_invoice,
    get_invoice_audit_trail,
)

# Reconciliation
from .reconcile import (
    reconcile,
    reconcile_invoice,
    fetch_onchain_usdc_transfers,
)

# Reports
from .reports import (
    generate_balance_sheet as balance_sheet,
    generate_income_statement as income_statement,
    generate_treasury_summary as treasury_summary,
    generate_counterparty_report as counterparty_report,
    generate_chain_report as chain_report,
    generate_period_comparison as period_comparison,
)

# CCTP Cross-Chain Bridge
from .cctp import (
    bridge_usdc,
    complete_bridge,
    get_bridge_status,
    list_pending as list_pending_bridges,
)

__all__ = [
    # Treasury
    "get_balance", "get_balances", "transfer_usdc", "get_transaction_history",
    "set_budget", "get_budget_status", "watch_incoming",
    "wallet_add", "wallet_list", "wallet_remove",
    # Invoices
    "create_invoice", "create_receivable_invoice", "pay_invoice",
    "list_invoices", "get_invoice", "cancel_invoice", "get_invoice_audit_trail",
    # Reconciliation
    "reconcile", "reconcile_invoice", "fetch_onchain_usdc_transfers",
    # Reports
    "balance_sheet", "income_statement", "treasury_summary",
    "counterparty_report", "chain_report", "period_comparison",
    # CCTP
    "bridge_usdc", "complete_bridge", "get_bridge_status", "list_pending_bridges",
]
