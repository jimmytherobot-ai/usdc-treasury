#!/usr/bin/env python3
"""
USDC Treasury - Invoice Management
Create, pay, track invoices with on-chain USDC settlement.
Supports both payable (we owe them) and receivable (they owe us) invoices.
"""

import sys
import os
import json
import argparse
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from web3 import Web3
from config import CHAINS, TREASURY_WALLET, ERC20_ABI, get_private_key
import db
from treasury import record_transaction, check_budget_limit


# ============================================================
# Invoice CRUD
# ============================================================

def create_invoice(
    counterparty_name,
    counterparty_address,
    line_items,
    chain_key="ethereum_sepolia",
    due_days=30,
    memo="",
    category="services",
    invoice_type="payable",
    wallet=None,
):
    """
    Create a new invoice.
    
    line_items: list of {"description": str, "quantity": float, "unit_price": float}
    invoice_type: "payable" (we pay them) or "receivable" (they pay us)
    Returns the created invoice.
    """
    wallet = wallet or TREASURY_WALLET
    
    # Validate counterparty address
    if not Web3.is_address(counterparty_address):
        raise ValueError(f"Invalid Ethereum address: {counterparty_address}")
    
    # Validate line items
    if not line_items:
        raise ValueError("Invoice must have at least one line item")
    
    for item in line_items:
        if Decimal(str(item.get("quantity", 0))) <= 0:
            raise ValueError(f"Line item quantity must be positive: {item.get('description', 'unknown')}")
        if Decimal(str(item.get("unit_price", 0))) < 0:
            raise ValueError(f"Line item unit_price cannot be negative: {item.get('description', 'unknown')}")
    
    # Generate monotonic invoice number (never reused)
    inv_num = db.next_counter("invoice_number")
    invoice_id = f"INV-{inv_num:04d}"
    
    # Calculate totals
    for item in line_items:
        item["amount"] = str(Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"])))
    
    total = sum(Decimal(item["amount"]) for item in line_items)
    if total <= 0:
        raise ValueError(f"Invoice total must be positive, got {total}")
    now = datetime.now(timezone.utc)
    
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_number": invoice_id,
        "status": "pending",  # pending, partial, paid, overpaid, cancelled
        "counterparty": {
            "name": counterparty_name,
            "address": counterparty_address,
        },
        "from_wallet": wallet,
        "chain": chain_key,
        "chain_name": CHAINS[chain_key]["name"],
        "line_items": line_items,
        "total_usdc": str(total),
        "paid_usdc": "0",
        "remaining_usdc": str(total),
        "payments": [],
        "category": category,
        "memo": memo,
        "invoice_type": invoice_type,
        "created_at": now.isoformat(),
        "due_date": (now + timedelta(days=due_days)).isoformat(),
        "updated_at": now.isoformat(),
    }
    
    db.insert_invoice(invoice)
    
    return invoice


def create_receivable_invoice(
    counterparty_name,
    counterparty_address,
    line_items,
    chain_key="ethereum_sepolia",
    due_days=30,
    memo="",
    category="services",
    wallet=None,
):
    """
    Create a receivable invoice (someone owes US money).
    Wrapper around create_invoice with invoice_type="receivable".
    """
    return create_invoice(
        counterparty_name, counterparty_address, line_items,
        chain_key, due_days, memo, category,
        invoice_type="receivable", wallet=wallet,
    )


def get_invoice(invoice_number=None, invoice_id=None):
    """Get a specific invoice by number or ID"""
    return db.get_invoice(invoice_number=invoice_number, invoice_id=invoice_id)


def list_invoices(status=None, counterparty=None, chain_key=None, invoice_type=None, wallet=None):
    """List invoices with optional filters"""
    return db.list_invoices(
        status=status, counterparty=counterparty, chain=chain_key,
        invoice_type=invoice_type, wallet=wallet,
    )


def cancel_invoice(invoice_number):
    """Cancel an unpaid invoice"""
    inv = db.get_invoice(invoice_number=invoice_number)
    if not inv:
        raise ValueError(f"Invoice {invoice_number} not found")
    
    if inv["status"] in ("paid", "overpaid"):
        raise ValueError(f"Cannot cancel {invoice_number}: already {inv['status']}")
    if Decimal(inv["paid_usdc"]) > 0:
        raise ValueError(f"Cannot cancel {invoice_number}: has partial payments")
    
    db.update_invoice(invoice_number, {
        "status": "cancelled",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    
    return db.get_invoice(invoice_number=invoice_number)


# ============================================================
# Invoice Payment (on-chain)
# ============================================================

def pay_invoice(invoice_number, amount_usdc=None, chain_key=None, wallet=None):
    """
    Pay an invoice with USDC on-chain.
    
    If amount_usdc is None, pays the full remaining amount.
    Supports partial payments and tracks overpayments.
    Returns payment record with tx hash.
    """
    wallet = wallet or TREASURY_WALLET
    invoice = get_invoice(invoice_number=invoice_number)
    if not invoice:
        raise ValueError(f"Invoice {invoice_number} not found")
    
    if invoice["status"] in ("cancelled", "overpaid"):
        raise ValueError(f"Invoice {invoice_number} is {invoice['status']}")
    
    remaining = Decimal(invoice["remaining_usdc"])
    if remaining <= 0 and invoice["status"] == "paid":
        raise ValueError(f"Invoice {invoice_number} is already fully paid")
    
    # Use invoice chain if not specified
    chain_key = chain_key or invoice["chain"]
    cfg = CHAINS[chain_key]
    
    # Determine payment amount
    if amount_usdc is None:
        amount = remaining
    else:
        amount = Decimal(str(amount_usdc))
    
    if amount <= 0:
        raise ValueError("Payment amount must be positive")
    
    # Execute on-chain transfer
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
    private_key = get_private_key()
    account = w3.eth.account.from_key(private_key)
    
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["usdc_address"]),
        abi=ERC20_ABI
    )
    decimals = usdc.functions.decimals().call()
    amount_raw = int(amount * Decimal(10 ** decimals))
    
    # Check balance
    balance = usdc.functions.balanceOf(account.address).call()
    if balance < amount_raw:
        raise ValueError(
            f"Insufficient USDC on {cfg['name']}: "
            f"have {Decimal(balance) / Decimal(10**decimals)}, need {amount}"
        )
    
    to_address = invoice["counterparty"]["address"]
    
    # Build and send transaction
    nonce = w3.eth.get_transaction_count(account.address)
    tx = usdc.functions.transfer(
        Web3.to_checksum_address(to_address),
        amount_raw
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "chainId": cfg["chain_id"],
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    now = datetime.now(timezone.utc)
    tx_hash_hex = receipt.transactionHash.hex()
    
    # Create payment record
    payment = {
        "payment_id": str(uuid.uuid4()),
        "tx_hash": tx_hash_hex,
        "chain": chain_key,
        "chain_name": cfg["name"],
        "from_wallet": account.address,
        "to_wallet": to_address,
        "amount_usdc": str(amount),
        "status": "confirmed" if receipt.status == 1 else "failed",
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "timestamp": now.isoformat(),
        "explorer_url": f"{cfg['explorer']}/tx/0x{tx_hash_hex}",
    }
    
    if receipt.status != 1:
        payment["status"] = "failed"
        # Record failed payment but don't update invoice totals
        record_transaction({
            **payment,
            "from": account.address,
            "to": to_address,
            "type": "invoice_payment_failed",
            "invoice_number": invoice_number,
            "category": invoice.get("category", "uncategorized"),
            "memo": f"Failed payment for {invoice_number}",
            "wallet": wallet,
        })
        return {"invoice": invoice, "payment": payment, "error": "Transaction failed"}
    
    # Update invoice
    inv = db.get_invoice(invoice_number=invoice_number)
    payments = inv.get("payments", [])
    payments.append(payment)
    
    new_paid = Decimal(inv["paid_usdc"]) + amount
    total = Decimal(inv["total_usdc"])
    new_remaining = total - new_paid
    
    if new_paid >= total:
        new_status = "overpaid" if new_paid > total else "paid"
    elif new_paid > 0:
        new_status = "partial"
    else:
        new_status = inv["status"]
    
    db.update_invoice(invoice_number, {
        "payments_json": json.dumps(payments, default=str),
        "paid_usdc": str(new_paid),
        "remaining_usdc": str(new_remaining),
        "status": new_status,
        "updated_at": now.isoformat(),
    })
    
    invoice = db.get_invoice(invoice_number=invoice_number)
    
    # Record in transaction ledger
    record_transaction({
        "tx_hash": tx_hash_hex,
        "chain": chain_key,
        "chain_name": cfg["name"],
        "from": account.address,
        "to": to_address,
        "amount_usdc": str(amount),
        "amount_raw": amount_raw,
        "type": "invoice_payment",
        "invoice_number": invoice_number,
        "category": invoice.get("category", "uncategorized"),
        "memo": f"Payment for {invoice_number}",
        "status": "confirmed",
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "timestamp": now.isoformat(),
        "explorer_url": f"{cfg['explorer']}/tx/0x{tx_hash_hex}",
        "wallet": wallet,
    })
    
    return {
        "invoice": invoice,
        "payment": payment,
    }


def get_invoice_audit_trail(invoice_number):
    """
    Full audit trail for an invoice:
    Invoice # → Payments → Tx hashes → Wallets → Timestamps → Status
    """
    invoice = get_invoice(invoice_number=invoice_number)
    if not invoice:
        raise ValueError(f"Invoice {invoice_number} not found")
    
    trail = {
        "invoice_number": invoice["invoice_number"],
        "status": invoice["status"],
        "invoice_type": invoice.get("invoice_type", "payable"),
        "counterparty": invoice["counterparty"],
        "total_usdc": invoice["total_usdc"],
        "paid_usdc": invoice["paid_usdc"],
        "remaining_usdc": invoice["remaining_usdc"],
        "created_at": invoice["created_at"],
        "due_date": invoice["due_date"],
        "line_items": invoice["line_items"],
        "payments": [],
    }
    
    for p in invoice.get("payments", []):
        trail["payments"].append({
            "payment_id": p["payment_id"],
            "tx_hash": p["tx_hash"],
            "chain": p["chain_name"],
            "from_wallet": p["from_wallet"],
            "to_wallet": p["to_wallet"],
            "amount_usdc": p["amount_usdc"],
            "status": p["status"],
            "block_number": p.get("block_number"),
            "timestamp": p["timestamp"],
            "explorer_url": p["explorer_url"],
        })
    
    return trail


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC Invoice Management")
    sub = parser.add_subparsers(dest="command")
    
    # create
    create = sub.add_parser("create", help="Create invoice (payable — we pay them)")
    create.add_argument("--counterparty-name", required=True)
    create.add_argument("--counterparty-address", required=True)
    create.add_argument("--items", required=True, help="JSON array of line items")
    create.add_argument("--chain", default="ethereum_sepolia", choices=list(CHAINS.keys()))
    create.add_argument("--due-days", type=int, default=30)
    create.add_argument("--memo", default="")
    create.add_argument("--category", default="services")
    create.add_argument("--wallet", default=TREASURY_WALLET)
    
    # receive — create receivable invoice
    receive = sub.add_parser("receive", help="Create receivable invoice (they owe us)")
    receive.add_argument("--counterparty-name", required=True)
    receive.add_argument("--counterparty-address", required=True)
    receive.add_argument("--items", required=True, help="JSON array of line items")
    receive.add_argument("--chain", default="ethereum_sepolia", choices=list(CHAINS.keys()))
    receive.add_argument("--due-days", type=int, default=30)
    receive.add_argument("--memo", default="")
    receive.add_argument("--category", default="services")
    receive.add_argument("--wallet", default=TREASURY_WALLET)
    
    # pay
    pay = sub.add_parser("pay", help="Pay invoice")
    pay.add_argument("invoice_number", help="e.g., INV-0001")
    pay.add_argument("--amount", type=float, help="Partial payment amount (default: full)")
    pay.add_argument("--chain", choices=list(CHAINS.keys()))
    pay.add_argument("--wallet", default=TREASURY_WALLET)
    
    # list
    ls = sub.add_parser("list", help="List invoices")
    ls.add_argument("--status", choices=["pending", "partial", "paid", "overpaid", "cancelled"])
    ls.add_argument("--counterparty")
    ls.add_argument("--chain", choices=list(CHAINS.keys()))
    ls.add_argument("--type", dest="invoice_type", choices=["payable", "receivable"])
    ls.add_argument("--wallet", default=None)
    
    # audit
    audit = sub.add_parser("audit", help="Invoice audit trail")
    audit.add_argument("invoice_number")
    
    # cancel
    cancel = sub.add_parser("cancel", help="Cancel invoice")
    cancel.add_argument("invoice_number")
    
    args = parser.parse_args()
    
    if args.command == "create":
        items = json.loads(args.items)
        result = create_invoice(
            args.counterparty_name,
            args.counterparty_address,
            items,
            args.chain,
            args.due_days,
            args.memo,
            args.category,
            wallet=args.wallet,
        )
        print(json.dumps(result, indent=2))
    
    elif args.command == "receive":
        items = json.loads(args.items)
        result = create_receivable_invoice(
            args.counterparty_name,
            args.counterparty_address,
            items,
            args.chain,
            args.due_days,
            args.memo,
            args.category,
            wallet=args.wallet,
        )
        print(json.dumps(result, indent=2))
    
    elif args.command == "pay":
        result = pay_invoice(args.invoice_number, args.amount, args.chain, args.wallet)
        print(json.dumps(result, indent=2))
    
    elif args.command == "list":
        result = list_invoices(args.status, args.counterparty, args.chain,
                               args.invoice_type, args.wallet)
        print(json.dumps(result, indent=2))
    
    elif args.command == "audit":
        result = get_invoice_audit_trail(args.invoice_number)
        print(json.dumps(result, indent=2))
    
    elif args.command == "cancel":
        result = cancel_invoice(args.invoice_number)
        print(json.dumps(result, indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}), file=sys.stderr)
        sys.exit(1)
