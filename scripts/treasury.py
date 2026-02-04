#!/usr/bin/env python3
"""
USDC Treasury - Core Treasury Management
Multi-chain balance tracking, transfers, budget management, transaction history
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from web3 import Web3
from config import (
    CHAINS, TREASURY_WALLET, ERC20_ABI,
    TRANSACTIONS_FILE, BUDGETS_FILE,
    get_private_key, load_json, save_json
)


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

def transfer_usdc(chain_key, to_address, amount_usdc, memo=None, category=None):
    """
    Transfer USDC on a specific chain.
    amount_usdc: human-readable amount (e.g., "10.50")
    Returns tx receipt and records transaction.
    """
    w3, cfg = get_web3(chain_key)
    private_key = get_private_key()
    account = w3.eth.account.from_key(private_key)
    
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
    }
    record_transaction(tx_record)
    
    return tx_record


# ============================================================
# Transaction History
# ============================================================

def record_transaction(tx_record):
    """Record a transaction to the ledger"""
    txs = load_json(TRANSACTIONS_FILE)
    txs.append(tx_record)
    save_json(TRANSACTIONS_FILE, txs)


def get_transactions(chain_key=None, category=None, counterparty=None, limit=50):
    """Query transaction history with filters"""
    txs = load_json(TRANSACTIONS_FILE)
    
    if chain_key:
        txs = [t for t in txs if t.get("chain") == chain_key]
    if category:
        txs = [t for t in txs if t.get("category") == category]
    if counterparty:
        cp = counterparty.lower()
        txs = [t for t in txs if t.get("to", "").lower() == cp or t.get("from", "").lower() == cp]
    
    # Sort by timestamp descending
    txs.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
    return txs[:limit]


# ============================================================
# Budget Management
# ============================================================

def set_budget(chain_key, category, limit_usdc, period="monthly"):
    """Set a spending budget for a category on a chain"""
    budgets = load_json(BUDGETS_FILE)
    
    # Update or create
    found = False
    for b in budgets:
        if b["chain"] == chain_key and b["category"] == category:
            b["limit_usdc"] = str(limit_usdc)
            b["period"] = period
            b["updated"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    
    if not found:
        budgets.append({
            "chain": chain_key,
            "category": category,
            "limit_usdc": str(limit_usdc),
            "period": period,
            "created": datetime.now(timezone.utc).isoformat(),
        })
    
    save_json(BUDGETS_FILE, budgets)
    return {"status": "ok", "chain": chain_key, "category": category, "limit": str(limit_usdc)}


def get_budget_status(chain_key=None, category=None):
    """Get budget utilization"""
    budgets = load_json(BUDGETS_FILE)
    txs = load_json(TRANSACTIONS_FILE)
    
    now = datetime.now(timezone.utc)
    
    results = []
    for b in budgets:
        if chain_key and b["chain"] != chain_key:
            continue
        if category and b["category"] != category:
            continue
        
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
    
    # history
    hist = sub.add_parser("history", help="Transaction history")
    hist.add_argument("--chain", choices=list(CHAINS.keys()))
    hist.add_argument("--category")
    hist.add_argument("--counterparty")
    hist.add_argument("--limit", type=int, default=50)
    
    # budget
    budg = sub.add_parser("budget", help="Budget management")
    budg.add_argument("action", choices=["set", "status"])
    budg.add_argument("--chain", choices=list(CHAINS.keys()))
    budg.add_argument("--category")
    budg.add_argument("--limit", type=float)
    budg.add_argument("--period", default="monthly", choices=["monthly", "weekly", "daily"])
    
    args = parser.parse_args()
    
    if args.command == "balance":
        if args.chain:
            result = get_balance(args.chain, args.wallet)
        else:
            result = get_all_balances(args.wallet)
        print(json.dumps(result, indent=2))
    
    elif args.command == "transfer":
        result = transfer_usdc(args.chain, args.to, args.amount, args.memo, args.category)
        print(json.dumps(result, indent=2))
    
    elif args.command == "history":
        result = get_transactions(args.chain, args.category, args.counterparty, args.limit)
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
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
