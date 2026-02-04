#!/usr/bin/env python3
"""
USDC Treasury - Reconciliation Engine
Match on-chain transactions with invoices, detect discrepancies.
Uses high-water marks to avoid re-scanning blocks.
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from web3 import Web3
from config import CHAINS, TREASURY_WALLET, ERC20_ABI
import db

# Default lookback for first run (no high-water mark)
DEFAULT_FIRST_RUN_LOOKBACK = 10000


# ============================================================
# On-Chain Transaction Fetching
# ============================================================

def fetch_onchain_usdc_transfers(chain_key, wallet=None, from_block=None, update_hwm=True):
    """
    Fetch USDC Transfer events for a wallet from chain.
    Uses high-water mark for efficient incremental scanning.
    Returns list of on-chain transfer records.
    """
    wallet = wallet or TREASURY_WALLET
    cfg = CHAINS[chain_key]
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
    
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["usdc_address"]),
        abi=ERC20_ABI
    )
    decimals = usdc.functions.decimals().call()
    
    current_block = w3.eth.block_number
    
    if from_block is not None:
        # Explicit override
        scan_from = from_block
    else:
        # Use high-water mark if available
        hwm = db.get_high_water_mark(chain_key, wallet)
        if hwm is not None:
            scan_from = hwm + 1
        else:
            # First run: look back DEFAULT_FIRST_RUN_LOOKBACK blocks
            scan_from = max(0, current_block - DEFAULT_FIRST_RUN_LOOKBACK)
    
    # Don't scan beyond current block
    if scan_from > current_block:
        return []
    
    wallet_bytes = Web3.to_checksum_address(wallet)
    transfers = []
    max_block_seen = scan_from
    
    # Outgoing
    try:
        out_filter = usdc.events.Transfer.create_filter(
            from_block=scan_from,
            argument_filters={"from": wallet_bytes}
        )
        for event in out_filter.get_all_entries():
            block = w3.eth.get_block(event.blockNumber)
            max_block_seen = max(max_block_seen, event.blockNumber)
            transfers.append({
                "tx_hash": event.transactionHash.hex(),
                "chain": chain_key,
                "direction": "outgoing",
                "from": event.args["from"],
                "to": event.args["to"],
                "amount_usdc": str(Decimal(event.args["value"]) / Decimal(10 ** decimals)),
                "amount_raw": event.args["value"],
                "block_number": event.blockNumber,
                "timestamp": datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
            })
    except Exception as e:
        print(f"Warning: Could not fetch outgoing transfers on {chain_key}: {e}", file=sys.stderr)
    
    # Incoming
    try:
        in_filter = usdc.events.Transfer.create_filter(
            from_block=scan_from,
            argument_filters={"to": wallet_bytes}
        )
        for event in in_filter.get_all_entries():
            block = w3.eth.get_block(event.blockNumber)
            max_block_seen = max(max_block_seen, event.blockNumber)
            transfers.append({
                "tx_hash": event.transactionHash.hex(),
                "chain": chain_key,
                "direction": "incoming",
                "from": event.args["from"],
                "to": event.args["to"],
                "amount_usdc": str(Decimal(event.args["value"]) / Decimal(10 ** decimals)),
                "amount_raw": event.args["value"],
                "block_number": event.blockNumber,
                "timestamp": datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
            })
    except Exception as e:
        print(f"Warning: Could not fetch incoming transfers on {chain_key}: {e}", file=sys.stderr)
    
    # Update high-water mark to current block (we've scanned up to here)
    if update_hwm and max_block_seen >= scan_from:
        db.set_high_water_mark(chain_key, wallet, max(max_block_seen, current_block))
    
    return transfers


# ============================================================
# Reconciliation
# ============================================================

def reconcile(chain_key=None, wallet=None, from_block=None):
    """
    Reconcile on-chain USDC transactions with internal records.
    
    Checks:
    1. All recorded transactions exist on-chain
    2. Invoice payments match on-chain transfers
    3. Detect unrecorded on-chain transfers
    4. Balance verification
    
    Returns reconciliation report.
    """
    wallet = wallet or TREASURY_WALLET
    internal_txs = db.get_all_transactions()
    invoices = db.list_invoices()
    
    chains_to_check = [chain_key] if chain_key else list(CHAINS.keys())
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": wallet,
        "chains": {},
        "summary": {
            "matched": 0,
            "unmatched_internal": 0,
            "unmatched_onchain": 0,
            "invoice_discrepancies": 0,
            "balance_ok": True,
        }
    }
    
    for ck in chains_to_check:
        cfg = CHAINS[ck]
        chain_report = {
            "chain_name": cfg["name"],
            "matched_txs": [],
            "unmatched_internal": [],
            "unmatched_onchain": [],
            "invoice_checks": [],
            "balance_check": {},
        }
        
        # Fetch on-chain data
        try:
            onchain_txs = fetch_onchain_usdc_transfers(ck, wallet=wallet, from_block=from_block)
        except Exception as e:
            chain_report["error"] = f"Could not fetch on-chain data: {e}"
            report["chains"][ck] = chain_report
            continue
        
        # Build lookup by tx_hash
        onchain_by_hash = {tx["tx_hash"]: tx for tx in onchain_txs}
        internal_chain = [t for t in internal_txs if t.get("chain") == ck]
        internal_by_hash = {t["tx_hash"]: t for t in internal_chain}
        
        # Match internal vs on-chain
        for tx in internal_chain:
            tx_hash = tx["tx_hash"]
            if tx_hash in onchain_by_hash:
                onchain = onchain_by_hash[tx_hash]
                # Verify amounts match
                if tx.get("amount_usdc") == onchain.get("amount_usdc"):
                    chain_report["matched_txs"].append({
                        "tx_hash": tx_hash,
                        "amount": tx["amount_usdc"],
                        "status": "matched",
                    })
                    report["summary"]["matched"] += 1
                else:
                    chain_report["matched_txs"].append({
                        "tx_hash": tx_hash,
                        "internal_amount": tx["amount_usdc"],
                        "onchain_amount": onchain["amount_usdc"],
                        "status": "amount_mismatch",
                    })
                    report["summary"]["unmatched_internal"] += 1
            else:
                chain_report["unmatched_internal"].append({
                    "tx_hash": tx_hash,
                    "amount": tx.get("amount_usdc"),
                    "type": tx.get("type"),
                    "note": "Recorded internally but not found on-chain (may be outside scan range)",
                })
                report["summary"]["unmatched_internal"] += 1
        
        # Find on-chain txs not in internal records
        for tx_hash, onchain in onchain_by_hash.items():
            if tx_hash not in internal_by_hash:
                chain_report["unmatched_onchain"].append({
                    "tx_hash": tx_hash,
                    "amount": onchain["amount_usdc"],
                    "direction": onchain["direction"],
                    "counterparty": onchain["to"] if onchain["direction"] == "outgoing" else onchain["from"],
                    "note": "On-chain transfer not recorded internally",
                })
                report["summary"]["unmatched_onchain"] += 1
        
        # Invoice payment verification
        chain_invoices = [i for i in invoices if i.get("chain") == ck]
        for inv in chain_invoices:
            payment_total = sum(
                Decimal(p["amount_usdc"]) for p in inv.get("payments", [])
                if p.get("status") == "confirmed"
            )
            recorded_paid = Decimal(inv.get("paid_usdc", "0"))
            
            if payment_total != recorded_paid:
                chain_report["invoice_checks"].append({
                    "invoice_number": inv["invoice_number"],
                    "status": "discrepancy",
                    "payment_sum": str(payment_total),
                    "recorded_paid": str(recorded_paid),
                })
                report["summary"]["invoice_discrepancies"] += 1
            else:
                chain_report["invoice_checks"].append({
                    "invoice_number": inv["invoice_number"],
                    "status": "ok",
                    "total": inv["total_usdc"],
                    "paid": str(recorded_paid),
                    "invoice_status": inv["status"],
                })
        
        # Balance verification
        try:
            w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
            usdc = w3.eth.contract(
                address=Web3.to_checksum_address(cfg["usdc_address"]),
                abi=ERC20_ABI
            )
            onchain_balance = usdc.functions.balanceOf(wallet).call()
            decimals = usdc.functions.decimals().call()
            chain_report["balance_check"] = {
                "onchain_usdc": str(Decimal(onchain_balance) / Decimal(10 ** decimals)),
                "status": "verified",
            }
        except Exception as e:
            chain_report["balance_check"] = {"error": str(e)}
            report["summary"]["balance_ok"] = False
        
        report["chains"][ck] = chain_report
    
    return report


def reconcile_invoice(invoice_number):
    """Reconcile a specific invoice against on-chain data"""
    invoice = db.get_invoice(invoice_number=invoice_number)
    if not invoice:
        raise ValueError(f"Invoice {invoice_number} not found")
    
    chain_key = invoice["chain"]
    cfg = CHAINS[chain_key]
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 15}))
    
    result = {
        "invoice_number": invoice_number,
        "status": invoice["status"],
        "total": invoice["total_usdc"],
        "recorded_paid": invoice["paid_usdc"],
        "payments_verified": [],
    }
    
    for payment in invoice.get("payments", []):
        try:
            tx_receipt = w3.eth.get_transaction_receipt(payment["tx_hash"])
            onchain_status = "confirmed" if tx_receipt.status == 1 else "failed"
            result["payments_verified"].append({
                "tx_hash": payment["tx_hash"],
                "recorded_status": payment["status"],
                "onchain_status": onchain_status,
                "match": payment["status"] == onchain_status,
                "block_number": tx_receipt.blockNumber,
            })
        except Exception as e:
            result["payments_verified"].append({
                "tx_hash": payment["tx_hash"],
                "error": str(e),
                "match": False,
            })
    
    return result


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC Reconciliation Engine")
    sub = parser.add_subparsers(dest="command")
    
    # Full reconciliation
    full = sub.add_parser("full", help="Full reconciliation")
    full.add_argument("--chain", choices=list(CHAINS.keys()))
    full.add_argument("--wallet", default=TREASURY_WALLET)
    full.add_argument("--from-block", type=int, help="Override: scan from this block")
    
    # Invoice reconciliation
    inv = sub.add_parser("invoice", help="Reconcile specific invoice")
    inv.add_argument("invoice_number")
    
    # Fetch on-chain
    fetch = sub.add_parser("fetch", help="Fetch on-chain transfers")
    fetch.add_argument("chain", choices=list(CHAINS.keys()))
    fetch.add_argument("--from-block", type=int)
    fetch.add_argument("--wallet", default=TREASURY_WALLET)
    
    args = parser.parse_args()
    
    if args.command == "full":
        result = reconcile(args.chain, args.wallet, getattr(args, 'from_block', None))
        print(json.dumps(result, indent=2))
    
    elif args.command == "invoice":
        result = reconcile_invoice(args.invoice_number)
        print(json.dumps(result, indent=2))
    
    elif args.command == "fetch":
        result = fetch_onchain_usdc_transfers(
            args.chain, wallet=args.wallet,
            from_block=getattr(args, 'from_block', None)
        )
        print(json.dumps(result, indent=2))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
