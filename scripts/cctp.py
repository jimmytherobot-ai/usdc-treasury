#!/usr/bin/env python3
"""
USDC Treasury - Cross-Chain Transfer Protocol (CCTP v2)
Bridge USDC between testnets using Circle's CCTP.
Supports resume of incomplete bridges via `complete` command.
"""

import sys
import os
import json
import time
import argparse
import requests
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from web3 import Web3
from config import (
    CHAINS, TREASURY_WALLET, ERC20_ABI,
    TOKEN_MESSENGER_V2_ABI, MESSAGE_TRANSMITTER_V2_ABI,
    CCTP_ATTESTATION_API,
    get_private_key
)
from treasury import record_transaction
import db


# ============================================================
# CCTP Bridge
# ============================================================

def bridge_usdc(
    source_chain,
    dest_chain,
    amount_usdc,
    recipient=None,
    max_fee=0,
    min_finality=2000,
):
    """
    Bridge USDC from source chain to destination chain via CCTP v2.
    
    Steps:
    1. Approve TokenMessenger to spend USDC
    2. Call depositForBurn on source chain
    3. Wait for Circle attestation
    4. Call receiveMessage on destination chain
    
    Pending bridges are stored in SQLite so they survive restarts.
    """
    if source_chain == dest_chain:
        raise ValueError("Source and destination chains must be different")
    
    recipient = recipient or TREASURY_WALLET
    src_cfg = CHAINS[source_chain]
    dst_cfg = CHAINS[dest_chain]
    
    # Connect to source chain
    w3_src = Web3(Web3.HTTPProvider(src_cfg["rpc"], request_kwargs={"timeout": 15}))
    private_key = get_private_key()
    account = w3_src.eth.account.from_key(private_key)
    
    # USDC contract on source
    usdc_src = w3_src.eth.contract(
        address=Web3.to_checksum_address(src_cfg["usdc_address"]),
        abi=ERC20_ABI
    )
    decimals = usdc_src.functions.decimals().call()
    amount_raw = int(Decimal(amount_usdc) * Decimal(10 ** decimals))
    
    # Check balance
    balance = usdc_src.functions.balanceOf(account.address).call()
    if balance < amount_raw:
        raise ValueError(
            f"Insufficient USDC on {src_cfg['name']}: "
            f"have {Decimal(balance) / Decimal(10**decimals)}, need {amount_usdc}"
        )
    
    token_messenger = Web3.to_checksum_address(src_cfg["token_messenger_v2"])
    
    # Step 1: Approve TokenMessenger to spend USDC
    print(f"Step 1: Approving {amount_usdc} USDC for CCTP on {src_cfg['name']}...")
    
    allowance = usdc_src.functions.allowance(account.address, token_messenger).call()
    if allowance < amount_raw:
        nonce = w3_src.eth.get_transaction_count(account.address)
        approve_tx = usdc_src.functions.approve(
            token_messenger, amount_raw
        ).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "gas": 100000,
            "gasPrice": w3_src.eth.gas_price,
            "chainId": src_cfg["chain_id"],
        })
        
        signed = account.sign_transaction(approve_tx)
        tx_hash = w3_src.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3_src.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status != 1:
            raise RuntimeError(f"Approval failed: {receipt.transactionHash.hex()}")
        print(f"  Approved: {src_cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}")
    else:
        print("  Already approved")
    
    # Step 2: Call depositForBurn
    print(f"Step 2: Depositing {amount_usdc} USDC for burn (→ {dst_cfg['name']})...")
    
    messenger = w3_src.eth.contract(
        address=token_messenger,
        abi=TOKEN_MESSENGER_V2_ABI
    )
    
    # Encode recipient as bytes32
    mint_recipient = Web3.to_bytes(hexstr=recipient).rjust(32, b'\x00')
    destination_caller = b'\x00' * 32  # Allow any caller
    
    nonce = w3_src.eth.get_transaction_count(account.address)
    burn_tx = messenger.functions.depositForBurn(
        amount_raw,
        dst_cfg["cctp_domain"],
        mint_recipient,
        Web3.to_checksum_address(src_cfg["usdc_address"]),
        destination_caller,
        max_fee,
        min_finality,
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3_src.eth.gas_price,
        "chainId": src_cfg["chain_id"],
    })
    
    signed = account.sign_transaction(burn_tx)
    tx_hash = w3_src.eth.send_raw_transaction(signed.raw_transaction)
    burn_receipt = w3_src.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    if burn_receipt.status != 1:
        raise RuntimeError(f"depositForBurn failed: {burn_receipt.transactionHash.hex()}")
    
    burn_tx_hash = burn_receipt.transactionHash.hex()
    print(f"  Burn tx: {src_cfg['explorer']}/tx/0x{burn_tx_hash}")
    
    # Extract message hash from logs
    message_hash = None
    message_bytes = None
    
    msg_transmitter_addr = Web3.to_checksum_address(src_cfg["message_transmitter_v2"])
    for log in burn_receipt.logs:
        if log.address.lower() == msg_transmitter_addr.lower():
            if len(log.topics) > 0:
                message_bytes = log.data
                message_hash = Web3.keccak(log.data).hex()
                break
    
    now = datetime.now(timezone.utc)
    
    # Store bridge in SQLite for resume capability
    bridge_record = {
        "burn_tx_hash": burn_tx_hash,
        "source_chain": source_chain,
        "dest_chain": dest_chain,
        "amount_usdc": str(amount_usdc),
        "recipient": recipient,
        "message_hash": message_hash,
        "message_bytes": message_bytes.hex() if isinstance(message_bytes, bytes) else message_bytes,
        "status": "burn_confirmed",
        "created_at": now.isoformat(),
    }
    db.insert_bridge(bridge_record)
    
    # Record the burn transaction
    record_transaction({
        "tx_hash": burn_tx_hash,
        "chain": source_chain,
        "chain_name": src_cfg["name"],
        "from": account.address,
        "to": f"CCTP→{dst_cfg['name']}",
        "amount_usdc": str(amount_usdc),
        "amount_raw": amount_raw,
        "type": "cctp_bridge",
        "category": "bridging_fees",
        "memo": f"CCTP bridge {src_cfg['name']} → {dst_cfg['name']}",
        "status": "burn_confirmed",
        "block_number": burn_receipt.blockNumber,
        "gas_used": burn_receipt.gasUsed,
        "timestamp": now.isoformat(),
        "explorer_url": f"{src_cfg['explorer']}/tx/0x{burn_tx_hash}",
        "cctp_message_hash": message_hash,
        "wallet": TREASURY_WALLET,
    })
    
    result = {
        "source_chain": src_cfg["name"],
        "dest_chain": dst_cfg["name"],
        "amount_usdc": str(amount_usdc),
        "recipient": recipient,
        "burn_tx_hash": burn_tx_hash,
        "burn_explorer": f"{src_cfg['explorer']}/tx/0x{burn_tx_hash}",
        "message_hash": message_hash,
        "status": "burn_confirmed",
        "timestamp": now.isoformat(),
    }
    
    # Step 3: Wait for attestation and complete on destination
    print(f"Step 3: Waiting for Circle attestation...")
    attestation = wait_for_attestation(message_hash)
    
    if attestation:
        # Store attestation
        db.update_bridge(burn_tx_hash, {
            "attestation": attestation,
            "status": "attestation_received",
        })
        
        print(f"Step 4: Receiving message on {dst_cfg['name']}...")
        try:
            mint_result = receive_message(
                dest_chain, message_bytes, attestation, private_key
            )
            result["mint_tx_hash"] = mint_result["tx_hash"]
            result["mint_explorer"] = mint_result["explorer_url"]
            result["status"] = "completed"
            
            # Update bridge record
            db.update_bridge(burn_tx_hash, {
                "mint_tx_hash": mint_result["tx_hash"],
                "status": "completed",
            })
            
            # Record mint transaction
            record_transaction({
                "tx_hash": mint_result["tx_hash"],
                "chain": dest_chain,
                "chain_name": dst_cfg["name"],
                "from": f"CCTP←{src_cfg['name']}",
                "to": recipient,
                "amount_usdc": str(amount_usdc),
                "type": "cctp_mint",
                "category": "bridging_fees",
                "memo": f"CCTP mint from {src_cfg['name']}",
                "status": "confirmed",
                "block_number": mint_result.get("block_number"),
                "gas_used": mint_result.get("gas_used"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "explorer_url": mint_result["explorer_url"],
                "cctp_burn_tx": burn_tx_hash,
                "wallet": TREASURY_WALLET,
            })
        except Exception as e:
            result["mint_error"] = str(e)
            result["status"] = "attestation_received"
            print(f"  Mint failed: {e}")
    else:
        result["status"] = "awaiting_attestation"
        result["note"] = "Attestation pending. Use 'cctp.py complete <burn_tx_hash>' to finish later."
        print("  Attestation not yet available. Bridge is in progress.")
    
    return result


# ============================================================
# Complete a pending bridge
# ============================================================

def complete_bridge(burn_tx_hash, max_wait=600, poll_interval=10):
    """
    Resume and complete a pending CCTP bridge.
    Looks up the stored message_hash, polls for attestation, and calls receiveMessage.
    """
    bridge = db.get_bridge(burn_tx_hash)
    if not bridge:
        raise ValueError(f"Bridge with burn tx {burn_tx_hash} not found in database")
    
    if bridge["status"] == "completed":
        print(f"Bridge {burn_tx_hash} is already completed.")
        return bridge
    
    dest_chain = bridge["dest_chain"]
    dst_cfg = CHAINS[dest_chain]
    message_hash = bridge.get("message_hash")
    message_bytes = bridge.get("message_bytes")
    attestation = bridge.get("attestation")
    
    if not message_hash:
        raise ValueError(f"No message_hash stored for bridge {burn_tx_hash}. Cannot complete.")
    
    # Step 1: Get attestation if we don't have it
    if not attestation:
        print(f"Polling for attestation (message_hash: {message_hash})...")
        attestation = wait_for_attestation(message_hash, max_wait=max_wait, poll_interval=poll_interval)
        
        if not attestation:
            db.update_bridge(burn_tx_hash, {"status": "awaiting_attestation"})
            raise RuntimeError(
                f"Attestation not available after {max_wait}s. "
                f"Try again later: cctp.py complete {burn_tx_hash}"
            )
        
        db.update_bridge(burn_tx_hash, {
            "attestation": attestation,
            "status": "attestation_received",
        })
        print("  Attestation received!")
    
    # Step 2: Call receiveMessage on destination chain
    print(f"Calling receiveMessage on {dst_cfg['name']}...")
    
    # Convert message_bytes from hex string if needed
    if isinstance(message_bytes, str):
        msg_bytes = bytes.fromhex(message_bytes.replace("0x", ""))
    else:
        msg_bytes = message_bytes
    
    private_key = get_private_key()
    mint_result = receive_message(dest_chain, msg_bytes, attestation, private_key)
    
    # Update bridge record
    db.update_bridge(burn_tx_hash, {
        "mint_tx_hash": mint_result["tx_hash"],
        "status": "completed",
    })
    
    # Record mint transaction
    src_cfg = CHAINS[bridge["source_chain"]]
    record_transaction({
        "tx_hash": mint_result["tx_hash"],
        "chain": dest_chain,
        "chain_name": dst_cfg["name"],
        "from": f"CCTP←{src_cfg['name']}",
        "to": bridge["recipient"],
        "amount_usdc": bridge["amount_usdc"],
        "type": "cctp_mint",
        "category": "bridging_fees",
        "memo": f"CCTP mint from {src_cfg['name']} (resumed)",
        "status": "confirmed",
        "block_number": mint_result.get("block_number"),
        "gas_used": mint_result.get("gas_used"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "explorer_url": mint_result["explorer_url"],
        "cctp_burn_tx": burn_tx_hash,
        "wallet": TREASURY_WALLET,
    })
    
    print(f"  ✅ Bridge completed! Mint tx: {mint_result['explorer_url']}")
    
    return {
        **bridge,
        "mint_tx_hash": mint_result["tx_hash"],
        "mint_explorer": mint_result["explorer_url"],
        "status": "completed",
    }


def wait_for_attestation(message_hash, max_wait=300, poll_interval=10):
    """
    Poll Circle's attestation API for the message attestation.
    Returns attestation bytes or None if timeout.
    """
    if not message_hash:
        return None
    
    # Clean hash format
    if not message_hash.startswith("0x"):
        message_hash = f"0x{message_hash}"
    
    start = time.time()
    while time.time() - start < max_wait:
        try:
            url = f"{CCTP_ATTESTATION_API}/{message_hash}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "complete":
                    return data.get("attestation")
        except Exception as e:
            print(f"  Attestation poll error: {e}")
        
        time.sleep(poll_interval)
        elapsed = int(time.time() - start)
        print(f"  Waiting for attestation... ({elapsed}s)")
    
    return None


def receive_message(dest_chain, message_bytes, attestation, private_key=None):
    """
    Call receiveMessage on the destination chain to complete the bridge.
    """
    dst_cfg = CHAINS[dest_chain]
    w3 = Web3(Web3.HTTPProvider(dst_cfg["rpc"], request_kwargs={"timeout": 15}))
    
    if not private_key:
        private_key = get_private_key()
    account = w3.eth.account.from_key(private_key)
    
    transmitter = w3.eth.contract(
        address=Web3.to_checksum_address(dst_cfg["message_transmitter_v2"]),
        abi=MESSAGE_TRANSMITTER_V2_ABI
    )
    
    # Convert attestation from hex string to bytes
    if isinstance(attestation, str):
        attestation = bytes.fromhex(attestation.replace("0x", ""))
    if isinstance(message_bytes, str):
        message_bytes = bytes.fromhex(message_bytes.replace("0x", ""))
    
    nonce = w3.eth.get_transaction_count(account.address)
    tx = transmitter.functions.receiveMessage(
        message_bytes,
        attestation
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "chainId": dst_cfg["chain_id"],
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    if receipt.status != 1:
        raise RuntimeError(f"receiveMessage failed on {dst_cfg['name']}")
    
    return {
        "tx_hash": receipt.transactionHash.hex(),
        "explorer_url": f"{dst_cfg['explorer']}/tx/0x{receipt.transactionHash.hex()}",
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
    }


def get_bridge_status(burn_tx_hash):
    """Check status of a CCTP bridge by burn tx hash"""
    # Check SQLite first
    bridge = db.get_bridge(burn_tx_hash)
    if bridge:
        return bridge
    
    # Fallback: check transaction records
    txs = db.get_all_transactions()
    burn_tx = None
    mint_tx = None
    
    for tx in txs:
        if tx.get("tx_hash") == burn_tx_hash:
            burn_tx = tx
        if tx.get("cctp_burn_tx") == burn_tx_hash:
            mint_tx = tx
    
    return {
        "burn_tx": burn_tx,
        "mint_tx": mint_tx,
        "status": "completed" if mint_tx else ("burn_confirmed" if burn_tx else "not_found"),
    }


def list_pending():
    """List all pending/incomplete bridges."""
    return db.list_pending_bridges()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC CCTP Cross-Chain Bridge")
    sub = parser.add_subparsers(dest="command")
    
    # Bridge
    br = sub.add_parser("bridge", help="Bridge USDC between chains")
    br.add_argument("source", choices=list(CHAINS.keys()))
    br.add_argument("dest", choices=list(CHAINS.keys()))
    br.add_argument("amount", help="Amount in USDC")
    br.add_argument("--recipient", default=TREASURY_WALLET)
    
    # Status
    st = sub.add_parser("status", help="Check bridge status")
    st.add_argument("burn_tx_hash")
    
    # Complete — resume a pending bridge
    comp = sub.add_parser("complete", help="Complete a pending bridge")
    comp.add_argument("burn_tx_hash", help="Burn tx hash from the source chain")
    comp.add_argument("--max-wait", type=int, default=600, help="Max wait for attestation (seconds)")
    comp.add_argument("--poll-interval", type=int, default=10, help="Poll interval (seconds)")
    
    # List pending bridges
    sub.add_parser("pending", help="List pending/incomplete bridges")
    
    args = parser.parse_args()
    
    if args.command == "bridge":
        result = bridge_usdc(args.source, args.dest, args.amount, args.recipient)
        print(json.dumps(result, indent=2))
    
    elif args.command == "status":
        result = get_bridge_status(args.burn_tx_hash)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.command == "complete":
        result = complete_bridge(args.burn_tx_hash, args.max_wait, args.poll_interval)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.command == "pending":
        result = list_pending()
        print(json.dumps(result, indent=2, default=str))
    
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
