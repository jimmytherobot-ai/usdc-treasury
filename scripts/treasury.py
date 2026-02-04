#!/usr/bin/env python3
"""
USDC Treasury - Core Treasury Management
Multi-chain balance tracking, transfers, budget management, transaction history,
wallet management, incoming payment detection, and event monitoring.
"""

import sys
import os
import json
import argparse
import time
import signal
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from web3 import Web3
from config import CHAINS, TREASURY_WALLET, ERC20_ABI, get_private_key
import db


# ============================================================
# Balance Tracking
# ============================================================

def get_web3(chain_key):
    """Get Web3 instance for a chain"""
    cfg = CHAINS[chain_key]
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
    return w3, cfg


def get_balance(chain_key, wallet=None):
    """Get ETH and USDC balance on a specific chain"""
    wallet = wallet or TREASURY_WALLET
    w3, cfg = get_web3(chain_key)
    
    eth_balance = w3.eth.get_balance(wallet)
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["usdc_address"]),
        abi=ERC20_ABI
    )
    usdc_balance = usdc.functions.balanceOf(wallet).call()
    decimals = usdc.functions.decimals().call()
    
    return {
        "chain": cfg["name"],
        "chain_key": chain_key,
        "wallet": wallet,
        "eth_balance": str(Web3.from_wei(eth_balance, "ether")),
        "usdc_balance": str(Decimal(usdc_balance) / Decimal(10 ** decimals)),
        "usdc_raw": usdc_balance,
        "decimals": decimals,
    }


def get_all_balances(wallet=None):
    """Get balances across all supported chains"""
    wallet = wallet or TREASURY_WALLET
    results = []
    total_usdc = Decimal("0")
    
    for chain_key in CHAINS:
        try:
            bal = get_balance(chain_key, wallet)
            results.append(bal)
            total_usdc += Decimal(bal["usdc_balance"])
        except Exception as e:
            results.append({
                "chain": CHAINS[chain_key]["name"],
                "chain_key": chain_key,
                "wallet": wallet,
                "error": str(e),
            })
    
    return {
        "wallet": wallet,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chains": results,
        "total_usdc": str(total_usdc),
    }


# ============================================================
# USDC Transfer
# ============================================================

def transfer_usdc(chain_key, to_address, amount_usdc, memo=None, category=None, wallet=None):
    """
    Transfer USDC on a specific chain.
    amount_usdc: human-readable amount (e.g., "10.50")
    Returns tx receipt and records transaction.
    """
    wallet = wallet or TREASURY_WALLET
    w3, cfg = get_web3(chain_key)
    private_key = get_private_key()
    account = w3.eth.account.from_key(private_key)
    
    # Validate recipient address
    if not Web3.is_address(to_address):
        raise ValueError(f"Invalid Ethereum address: {to_address}")
    
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["usdc_address"]),
        abi=ERC20_ABI
    )
    decimals = usdc.functions.decimals().call()
    amount_raw = int(Decimal(amount_usdc) * Decimal(10 ** decimals))
    
    # Check balance
    balance = usdc.functions.balanceOf(account.address).call()
    if balance < amount_raw:
        raise ValueError(
            f"Insufficient USDC balance on {cfg['name']}: "
            f"have {Decimal(balance) / Decimal(10**decimals)}, need {amount_usdc}"
        )
    
    # Check budget limits
    check_budget_limit(chain_key, Decimal(amount_usdc), category)
    
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
    
    # Record transaction
    tx_record = {
        "tx_hash": receipt.transactionHash.hex(),
        "chain": chain_key,
        "chain_name": cfg["name"],
        "from": account.address,
        "to": to_address,
        "amount_usdc": str(amount_usdc),
        "amount_raw": amount_raw,
        "type": "transfer",
        "category": category or "uncategorized",
        "memo": memo or "",
        "status": "confirmed" if receipt.status == 1 else "failed",
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "explorer_url": f"{cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}",
        "wallet": wallet,
    }
    record_transaction(tx_record)
    
    return tx_record


# ============================================================
# Transaction History
# ============================================================

def record_transaction(tx_record):
    """Record a transaction to the ledger"""
    db.insert_transaction(tx_record)


def get_transactions(chain_key=None, category=None, counterparty=None, limit=50,
                     wallet=None, start=None, end=None):
    """Query transaction history with filters"""
    return db.get_transactions(
        chain=chain_key, category=category, counterparty=counterparty,
        wallet=wallet, limit=limit, start=start, end=end
    )


# ============================================================
# Budget Management
# ============================================================

def set_budget(chain_key, category, limit_usdc, period="monthly"):
    """Set a spending budget for a category on a chain"""
    return db.set_budget(chain_key, category, limit_usdc, period)


def get_budget_status(chain_key=None, category=None):
    """Get budget utilization"""
    budgets = db.get_budgets(chain_key, category)
    txs = db.get_all_transactions()
    
    now = datetime.now(timezone.utc)
    
    results = []
    for b in budgets:
        # Calculate spending in current period
        period_txs = [
            t for t in txs
            if t.get("chain") == b["chain"]
            and t.get("category") == b["category"]
            and t.get("type") in ("transfer", "invoice_payment")
            and t.get("status") == "confirmed"
        ]
        
        # Filter by period
        if b["period"] == "monthly":
            period_txs = [
                t for t in period_txs
                if t.get("timestamp", "")[:7] == now.strftime("%Y-%m")
            ]
        elif b["period"] == "weekly":
            week_start = now.strftime("%Y-%W")
            period_txs = [
                t for t in period_txs
                if datetime.fromisoformat(t["timestamp"]).strftime("%Y-%W") == week_start
            ]
        
        spent = sum(Decimal(t.get("amount_usdc", "0")) for t in period_txs)
        limit = Decimal(b["limit_usdc"])
        
        results.append({
            "chain": b["chain"],
            "category": b["category"],
            "limit_usdc": str(limit),
            "spent_usdc": str(spent),
            "remaining_usdc": str(limit - spent),
            "utilization_pct": float(spent / limit * 100) if limit > 0 else 0,
            "period": b["period"],
            "alert": spent >= limit * Decimal("0.9"),
        })
    
    return results


def check_budget_limit(chain_key, amount, category=None):
    """Check if a transfer would exceed budget limits. Raises ValueError if over."""
    if not category:
        return  # No category, no budget check
    
    statuses = get_budget_status(chain_key, category)
    for s in statuses:
        remaining = Decimal(s["remaining_usdc"])
        if amount > remaining:
            raise ValueError(
                f"⚠️ Budget alert: {category} on {chain_key} — "
                f"spending {amount} USDC would exceed budget "
                f"(remaining: {remaining} of {s['limit_usdc']})"
            )
        if Decimal(s["spent_usdc"]) + amount >= Decimal(s["limit_usdc"]) * Decimal("0.9"):
            print(f"⚠️ Budget warning: {category} on {chain_key} approaching limit "
                  f"({s['utilization_pct']:.1f}% used)")


# ============================================================
# Incoming Payment Detection (watch command)
# ============================================================

def watch_incoming(chain_key=None, wallet=None, from_block=None):
    """
    Scan for incoming USDC transfers to our wallet.
    Auto-match against open receivable invoices.
    """
    wallet = wallet or TREASURY_WALLET
    chains_to_check = [chain_key] if chain_key else list(CHAINS.keys())
    
    all_incoming = []
    
    for ck in chains_to_check:
        cfg = CHAINS[ck]
        w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
        
        usdc = w3.eth.contract(
            address=Web3.to_checksum_address(cfg["usdc_address"]),
            abi=ERC20_ABI
        )
        decimals = usdc.functions.decimals().call()
        
        if from_block is None:
            # Use high-water mark or default lookback
            hwm = db.get_high_water_mark(ck, wallet)
            if hwm is not None:
                scan_from = hwm + 1
            else:
                current = w3.eth.block_number
                scan_from = max(0, current - 10000)
        else:
            scan_from = from_block
        
        wallet_bytes = Web3.to_checksum_address(wallet)
        
        try:
            in_filter = usdc.events.Transfer.create_filter(
                from_block=scan_from,
                argument_filters={"to": wallet_bytes}
            )
            max_block = scan_from
            for event in in_filter.get_all_entries():
                block = w3.eth.get_block(event.blockNumber)
                max_block = max(max_block, event.blockNumber)
                
                tx_hash = event.transactionHash.hex()
                amount_usdc = str(Decimal(event.args["value"]) / Decimal(10 ** decimals))
                sender = event.args["from"]
                
                # Check if already recorded
                existing = db.get_transactions(counterparty=sender, limit=None)
                already_recorded = any(t.get("tx_hash") == tx_hash for t in existing)
                
                incoming = {
                    "tx_hash": tx_hash,
                    "chain": ck,
                    "chain_name": cfg["name"],
                    "from": sender,
                    "to": wallet,
                    "amount_usdc": amount_usdc,
                    "block_number": event.blockNumber,
                    "timestamp": datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
                    "already_recorded": already_recorded,
                    "matched_invoice": None,
                }
                
                if not already_recorded:
                    # Try to auto-match against open receivable invoices
                    match = _match_incoming_to_invoice(sender, amount_usdc, ck)
                    if match:
                        incoming["matched_invoice"] = match["invoice_number"]
                        _record_incoming_payment(incoming, match)
                    else:
                        # Record as unmatched incoming
                        record_transaction({
                            "tx_hash": tx_hash,
                            "chain": ck,
                            "chain_name": cfg["name"],
                            "from": sender,
                            "to": wallet,
                            "amount_usdc": amount_usdc,
                            "amount_raw": event.args["value"],
                            "type": "incoming",
                            "direction": "incoming",
                            "category": "incoming_transfer",
                            "memo": f"Incoming USDC from {sender}",
                            "status": "confirmed",
                            "block_number": event.blockNumber,
                            "gas_used": 0,
                            "timestamp": incoming["timestamp"],
                            "explorer_url": f"{cfg['explorer']}/tx/0x{tx_hash}",
                            "wallet": wallet,
                        })
                
                all_incoming.append(incoming)
            
            # Update high-water mark
            if max_block > scan_from:
                db.set_high_water_mark(ck, wallet, max_block)
                
        except Exception as e:
            print(f"Warning: Could not scan {ck}: {e}", file=sys.stderr)
    
    return {
        "wallet": wallet,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incoming_transfers": all_incoming,
        "total_found": len(all_incoming),
        "new_transfers": len([t for t in all_incoming if not t["already_recorded"]]),
    }


def _match_incoming_to_invoice(sender, amount_usdc, chain):
    """Try to match an incoming transfer to an open receivable invoice."""
    invoices = db.list_invoices(invoice_type="receivable")
    amount = Decimal(amount_usdc)
    
    for inv in invoices:
        if inv["status"] not in ("pending", "partial"):
            continue
        if inv.get("chain") != chain:
            continue
        # Match by sender address and remaining amount
        if inv["counterparty"]["address"].lower() == sender.lower():
            remaining = Decimal(inv["remaining_usdc"])
            if amount == remaining or abs(amount - remaining) < Decimal("0.01"):
                return inv
    
    # Try fuzzy match (just sender address, any amount)
    for inv in invoices:
        if inv["status"] not in ("pending", "partial"):
            continue
        if inv["counterparty"]["address"].lower() == sender.lower():
            return inv
    
    return None


def _record_incoming_payment(incoming, invoice):
    """Record an incoming payment that matches an invoice."""
    import uuid as uuid_mod
    
    payment = {
        "payment_id": str(uuid_mod.uuid4()),
        "tx_hash": incoming["tx_hash"],
        "chain": incoming["chain"],
        "chain_name": incoming["chain_name"],
        "from_wallet": incoming["from"],
        "to_wallet": incoming["to"],
        "amount_usdc": incoming["amount_usdc"],
        "status": "confirmed",
        "block_number": incoming["block_number"],
        "gas_used": 0,
        "timestamp": incoming["timestamp"],
        "explorer_url": "",
    }
    
    # Update invoice
    inv = db.get_invoice(invoice_number=invoice["invoice_number"])
    if inv:
        payments = inv.get("payments", [])
        payments.append(payment)
        
        new_paid = Decimal(inv["paid_usdc"]) + Decimal(incoming["amount_usdc"])
        total = Decimal(inv["total_usdc"])
        remaining = total - new_paid
        
        if new_paid >= total:
            new_status = "overpaid" if new_paid > total else "paid"
        elif new_paid > 0:
            new_status = "partial"
        else:
            new_status = inv["status"]
        
        db.update_invoice(invoice["invoice_number"], {
            "payments_json": json.dumps(payments),
            "paid_usdc": str(new_paid),
            "remaining_usdc": str(remaining),
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    
    # Record transaction
    cfg = CHAINS.get(incoming["chain"], {})
    record_transaction({
        "tx_hash": incoming["tx_hash"],
        "chain": incoming["chain"],
        "chain_name": incoming.get("chain_name", ""),
        "from": incoming["from"],
        "to": incoming["to"],
        "amount_usdc": incoming["amount_usdc"],
        "amount_raw": 0,
        "type": "incoming_payment",
        "direction": "incoming",
        "category": "incoming_transfer",
        "memo": f"Received payment for {invoice['invoice_number']}",
        "status": "confirmed",
        "block_number": incoming["block_number"],
        "gas_used": 0,
        "timestamp": incoming["timestamp"],
        "explorer_url": f"{cfg.get('explorer', '')}/tx/0x{incoming['tx_hash']}",
        "invoice_number": invoice["invoice_number"],
        "wallet": incoming["to"],
    })


# ============================================================
# Event Monitor (foreground polling)
# ============================================================

def monitor_incoming(chain_key=None, wallet=None, interval=30):
    """
    Poll for new incoming USDC transfers every `interval` seconds.
    Foreground process — Ctrl-C to stop.
    """
    wallet = wallet or TREASURY_WALLET
    chains = [chain_key] if chain_key else list(CHAINS.keys())
    
    print(f"🔍 Monitoring incoming USDC transfers to {wallet}")
    print(f"   Chains: {', '.join(chains)}")
    print(f"   Polling every {interval}s — Ctrl-C to stop")
    print()
    
    running = True
    
    def handle_sigint(sig, frame):
        nonlocal running
        running = False
        print("\n⏹  Stopping monitor...")
    
    signal.signal(signal.SIGINT, handle_sigint)
    
    while running:
        try:
            result = watch_incoming(chain_key=chain_key, wallet=wallet)
            new_count = result.get("new_transfers", 0)
            
            if new_count > 0:
                print(f"🔔 [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
                      f"Found {new_count} new incoming transfer(s)!")
                for tx in result["incoming_transfers"]:
                    if not tx["already_recorded"]:
                        match_info = f" → matched {tx['matched_invoice']}" if tx["matched_invoice"] else ""
                        print(f"   💰 {tx['amount_usdc']} USDC from {tx['from'][:10]}... "
                              f"on {tx['chain_name']}{match_info}")
            else:
                ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
                print(f"  [{ts}] No new transfers", end='\r')
            
        except Exception as e:
            print(f"⚠️ Monitor error: {e}", file=sys.stderr)
        
        # Sleep in small increments so Ctrl-C is responsive
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)
    
    print("Monitor stopped.")


# ============================================================
# Wallet Management
# ============================================================

def wallet_add(address, name=""):
    """Add a wallet to tracking."""
    if not Web3.is_address(address):
        raise ValueError(f"Invalid Ethereum address: {address}")
    address = Web3.to_checksum_address(address)
    db.add_wallet(address, name)
    return {"status": "ok", "address": address, "name": name}


def wallet_list():
    """List all tracked wallets."""
    wallets = db.list_wallets()
    # Always include the default treasury wallet
    addresses = {w["address"].lower() for w in wallets}
    if TREASURY_WALLET.lower() not in addresses:
        wallets.insert(0, {
            "address": TREASURY_WALLET,
            "name": "Default Treasury",
            "is_default": 1,
            "added_at": "",
        })
    return wallets


def wallet_remove(address):
    """Remove a wallet from tracking."""
    if address.lower() == TREASURY_WALLET.lower():
        raise ValueError("Cannot remove the default treasury wallet")
    db.remove_wallet(address)
    return {"status": "ok", "removed": address}


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC Treasury Management")
    sub = parser.add_subparsers(dest="command")
    
    # balance
    bal = sub.add_parser("balance", help="Check balances")
    bal.add_argument("--chain", choices=list(CHAINS.keys()), help="Specific chain")
    bal.add_argument("--wallet", default=TREASURY_WALLET)
    
    # transfer
    xfer = sub.add_parser("transfer", help="Transfer USDC")
    xfer.add_argument("chain", choices=list(CHAINS.keys()))
    xfer.add_argument("to", help="Recipient address")
    xfer.add_argument("amount", help="Amount in USDC")
    xfer.add_argument("--memo", default="")
    xfer.add_argument("--category", default="uncategorized")
    xfer.add_argument("--wallet", default=TREASURY_WALLET)
    
    # history
    hist = sub.add_parser("history", help="Transaction history")
    hist.add_argument("--chain", choices=list(CHAINS.keys()))
    hist.add_argument("--category")
    hist.add_argument("--counterparty")
    hist.add_argument("--limit", type=int, default=50)
    hist.add_argument("--wallet", default=None)
    hist.add_argument("--start", help="Start date filter (ISO)")
    hist.add_argument("--end", help="End date filter (ISO)")
    
    # budget
    budg = sub.add_parser("budget", help="Budget management")
    budg.add_argument("action", choices=["set", "status"])
    budg.add_argument("--chain", choices=list(CHAINS.keys()))
    budg.add_argument("--category")
    budg.add_argument("--limit", type=float)
    budg.add_argument("--period", default="monthly", choices=["monthly", "weekly", "daily"])
    
    # wallet management
    wal = sub.add_parser("wallet", help="Wallet management")
    wal_sub = wal.add_subparsers(dest="wallet_action")
    
    wal_add = wal_sub.add_parser("add", help="Add wallet")
    wal_add.add_argument("address")
    wal_add.add_argument("--name", default="")
    
    wal_sub.add_parser("list", help="List wallets")
    
    wal_rm = wal_sub.add_parser("remove", help="Remove wallet")
    wal_rm.add_argument("address")
    
    # watch — scan for incoming payments
    watch = sub.add_parser("watch", help="Scan for incoming USDC transfers")
    watch.add_argument("--chain", choices=list(CHAINS.keys()))
    watch.add_argument("--wallet", default=TREASURY_WALLET)
    watch.add_argument("--from-block", type=int)
    
    # monitor — continuous polling
    mon = sub.add_parser("monitor", help="Monitor incoming transfers (foreground)")
    mon.add_argument("--chain", choices=list(CHAINS.keys()))
    mon.add_argument("--wallet", default=TREASURY_WALLET)
    mon.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    
    args = parser.parse_args()
    
    if args.command == "balance":
        if args.chain:
            result = get_balance(args.chain, args.wallet)
        else:
            result = get_all_balances(args.wallet)
        print(json.dumps(result, indent=2))
    
    elif args.command == "transfer":
        result = transfer_usdc(args.chain, args.to, args.amount, args.memo, args.category, args.wallet)
        print(json.dumps(result, indent=2))
    
    elif args.command == "history":
        result = get_transactions(args.chain, args.category, args.counterparty, args.limit,
                                  args.wallet, args.start, args.end)
        print(json.dumps(result, indent=2))
    
    elif args.command == "budget":
        if args.action == "set":
            if not all([args.chain, args.category, args.limit]):
                print("Error: --chain, --category, --limit required for budget set")
                sys.exit(1)
            result = set_budget(args.chain, args.category, args.limit, args.period)
            print(json.dumps(result, indent=2))
        elif args.action == "status":
            result = get_budget_status(args.chain, args.category)
            print(json.dumps(result, indent=2))
    
    elif args.command == "wallet":
        if args.wallet_action == "add":
            result = wallet_add(args.address, args.name)
            print(json.dumps(result, indent=2))
        elif args.wallet_action == "list":
            result = wallet_list()
            print(json.dumps(result, indent=2))
        elif args.wallet_action == "remove":
            result = wallet_remove(args.address)
            print(json.dumps(result, indent=2))
        else:
            wal.print_help()
    
    elif args.command == "watch":
        result = watch_incoming(args.chain, args.wallet, getattr(args, 'from_block', None))
        print(json.dumps(result, indent=2))
    
    elif args.command == "monitor":
        monitor_incoming(args.chain, args.wallet, args.interval)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}), file=sys.stderr)
        sys.exit(1)
