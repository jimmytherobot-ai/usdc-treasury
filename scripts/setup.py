#!/usr/bin/env python3
"""
USDC Treasury — First-Run Setup

Validates environment, creates data directory, tests RPC connectivity,
and optionally derives wallet address from private key.

Usage:
    python scripts/setup.py
    
    # Or with env vars pre-set:
    TREASURY_PRIVATE_KEY=0x... python scripts/setup.py
"""

import os
import sys
import json

# Resolve paths relative to this script
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")

# Allow imports from scripts/
sys.path.insert(0, SCRIPTS_DIR)


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def ok(msg):
    print(f"  ✅ {msg}")


def warn(msg):
    print(f"  ⚠️  {msg}")


def fail(msg):
    print(f"  ❌ {msg}")


def section(msg):
    print(f"\n--- {msg} ---")


def main():
    banner("USDC Treasury — Setup")
    errors = []

    # ========================================
    # 1. Python version
    # ========================================
    section("Python")
    v = sys.version_info
    if v >= (3, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 9):
        warn(f"Python {v.major}.{v.minor} — works but 3.11+ recommended")
    else:
        fail(f"Python {v.major}.{v.minor} — requires 3.9+")
        errors.append("Python version too old")

    # ========================================
    # 2. Dependencies
    # ========================================
    section("Dependencies")
    try:
        import web3
        ok(f"web3.py {web3.__version__}")
    except ImportError:
        fail("web3 not installed — run: pip install -r requirements.txt")
        errors.append("web3 not installed")

    try:
        import requests
        ok(f"requests {requests.__version__}")
    except ImportError:
        fail("requests not installed — run: pip install -r requirements.txt")
        errors.append("requests not installed")

    # ========================================
    # 3. Data directory
    # ========================================
    section("Data Directory")
    from config import DATA_DIR
    if os.path.isdir(DATA_DIR):
        ok(f"Exists: {DATA_DIR}")
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        ok(f"Created: {DATA_DIR}")

    # Test SQLite
    try:
        import db  # This triggers init_db() on import
        ok(f"SQLite database initialized: {db.DB_PATH}")
    except Exception as e:
        fail(f"Database init failed: {e}")
        errors.append(f"DB init: {e}")

    # ========================================
    # 4. Wallet configuration
    # ========================================
    section("Wallet")
    wallet = os.environ.get("TREASURY_WALLET")
    if wallet:
        ok(f"TREASURY_WALLET: {wallet}")
    else:
        warn("TREASURY_WALLET not set — will try to derive from private key")

    # Check private key
    key_source = None
    try:
        from config import get_private_key
        _key = get_private_key()
        # Derive address
        from web3 import Web3
        addr = Web3().eth.account.from_key(_key).address
        ok(f"Private key found → wallet: {addr}")
        key_source = "found"

        if not wallet:
            ok(f"Derived wallet address: {addr}")
            print(f"\n  💡 Tip: export TREASURY_WALLET={addr}")
            print(f"     to skip derivation on future runs")
    except RuntimeError as e:
        if not wallet:
            fail(f"No private key: {e}")
            errors.append("No private key configured")
            print("\n  To configure, set one of:")
            print("    export TREASURY_PRIVATE_KEY=0xYourKeyHere")
            print("    export ETH_PRIVATE_KEY=0xYourKeyHere")
        else:
            warn(f"Private key not available — read-only mode (balance checks only)")
            print("  Transfers and payments require a private key.")

    # ========================================
    # 5. RPC connectivity
    # ========================================
    section("RPC Connectivity")
    from config import CHAINS

    try:
        from web3 import Web3
    except ImportError:
        warn("Skipping RPC checks — web3 not installed")
        Web3 = None

    if Web3:
        for chain_key, cfg in CHAINS.items():
            rpc = cfg["rpc"]
            env_key = f"TREASURY_RPC_{chain_key.upper()}"
            is_custom = bool(os.environ.get(env_key))
            label = f"{cfg['name']} {'(custom)' if is_custom else '(default)'}"
            try:
                w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
                block = w3.eth.block_number
                ok(f"{label}: block #{block:,}")
            except Exception as e:
                fail(f"{label}: {e}")
                errors.append(f"RPC {chain_key}: {e}")

    # ========================================
    # 6. USDC balance check
    # ========================================
    if Web3 and (wallet or key_source):
        section("USDC Balances")
        try:
            from treasury import get_all_balances
            result = get_all_balances()
            for chain_bal in result.get("chains", []):
                if "error" in chain_bal:
                    warn(f"{chain_bal['chain']}: {chain_bal['error']}")
                else:
                    usdc = chain_bal["usdc_balance"]
                    eth = chain_bal["eth_balance"]
                    status = "✅" if float(eth) > 0 else "⚠️ "
                    print(f"  {status} {chain_bal['chain']}: {usdc} USDC, {eth} ETH")
                    if float(eth) == 0:
                        print(f"     ↳ Need testnet ETH for gas!")

            total = result.get("total_usdc", "0")
            print(f"\n  Total USDC: {total}")
            if float(total) == 0:
                print(f"\n  💡 Get testnet USDC: https://faucet.circle.com")
        except Exception as e:
            warn(f"Could not check balances: {e}")

    # ========================================
    # Summary
    # ========================================
    banner("Setup Complete" if not errors else "Setup Complete (with issues)")

    if errors:
        print("Issues to fix:")
        for e in errors:
            print(f"  ❌ {e}")
        print()
    else:
        print("Everything looks good! 🎉\n")

    print("Quick start:")
    print("  python scripts/treasury.py balance")
    print("  python scripts/invoices.py list")
    print("  python scripts/reports.py summary")
    print()
    print("Start the API server:")
    print("  python scripts/server.py")
    print()

    if not wallet and not key_source:
        print("⚡ Minimum setup — just set these two env vars:")
        print("  export TREASURY_PRIVATE_KEY=0xYourKeyHere")
        print("  export TREASURY_WALLET=0xYourAddressHere")
        print()

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
