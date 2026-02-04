"""
USDC Treasury - Configuration and Constants
Testnet contract addresses, chain configs, ABIs
"""

import os
import json
import subprocess

# ============================================================
# Chain Configuration
# ============================================================

CHAINS = {
    "ethereum_sepolia": {
        "name": "Ethereum Sepolia",
        "chain_id": 11155111,
        "rpc": "https://ethereum-sepolia-rpc.publicnode.com",
        "explorer": "https://sepolia.etherscan.io",
        "usdc_address": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        "cctp_domain": 0,
        "token_messenger_v2": "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA",
        "message_transmitter_v2": "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275",
    },
    "base_sepolia": {
        "name": "Base Sepolia",
        "chain_id": 84532,
        "rpc": "https://base-sepolia-rpc.publicnode.com",
        "explorer": "https://base-sepolia.blockscout.com",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "cctp_domain": 6,
        "token_messenger_v2": "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA",
        "message_transmitter_v2": "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275",
    },
    "arbitrum_sepolia": {
        "name": "Arbitrum Sepolia",
        "chain_id": 421614,
        "rpc": "https://arbitrum-sepolia-rpc.publicnode.com",
        "explorer": "https://sepolia.arbiscan.io",
        "usdc_address": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        "cctp_domain": 3,
        "token_messenger_v2": "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA",
        "message_transmitter_v2": "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275",
    },
}

# Circle CCTP attestation API (testnet)
CCTP_ATTESTATION_API = "https://iris-api-sandbox.circle.com/v2/attestations"

# Safety: reject mainnet chain IDs to prevent accidental mainnet transactions
MAINNET_CHAIN_IDS = {1, 8453, 42161, 10, 137, 43114, 56}  # ETH, Base, Arb, OP, Polygon, Avalanche, BSC
for _chain_key, _chain_cfg in CHAINS.items():
    if _chain_cfg["chain_id"] in MAINNET_CHAIN_IDS:
        raise RuntimeError(
            f"SAFETY: Mainnet chain ID {_chain_cfg['chain_id']} detected in CHAINS['{_chain_key}']. "
            f"This tool is testnet-only. Remove mainnet chains from config."
        )

# ============================================================
# Wallet
# ============================================================

TREASURY_WALLET = "0x8fcc48751905c01cB7ddCC7A0c3d491389805ba8"

def get_private_key():
    """Retrieve private key from env vars, KeePassXC, or macOS Keychain"""
    # Try environment variables first (for Docker/Linux/CI)
    key = os.environ.get("TREASURY_PRIVATE_KEY") or os.environ.get("ETH_PRIVATE_KEY")
    if key:
        return key if key.startswith("0x") else f"0x{key}"
    
    # Try KeePassXC
    try:
        result = subprocess.run(
            [os.path.expanduser("~/clawd/scripts/get-secret.sh"), "jimmy-wallet-eth"],
            capture_output=True, text=True, timeout=10
        )
        key = result.stdout.strip()
        if key and len(key) >= 64 and not key.startswith("Error"):
            return key if key.startswith("0x") else f"0x{key}"
    except Exception:
        pass
    
    # Fallback to macOS Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "jimmy", "-s", "jimmy-wallet-eth", "-w"],
            capture_output=True, text=True, timeout=10
        )
        key = result.stdout.strip()
        if key and len(key) >= 64:
            return key if key.startswith("0x") else f"0x{key}"
    except Exception:
        pass
    
    raise RuntimeError("Failed to get private key from KeePassXC or macOS Keychain")


# ============================================================
# ABIs
# ============================================================

# Minimal ERC20 ABI (USDC)
ERC20_ABI = json.loads("""[
    {"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"from","type":"address"},{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"owner","type":"address"},{"indexed":true,"name":"spender","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Approval","type":"event"}
]""")

# CCTP TokenMessengerV2 ABI (depositForBurn)
TOKEN_MESSENGER_V2_ABI = json.loads("""[
    {
        "inputs": [
            {"name": "amount", "type": "uint256"},
            {"name": "destinationDomain", "type": "uint32"},
            {"name": "mintRecipient", "type": "bytes32"},
            {"name": "burnToken", "type": "address"},
            {"name": "destinationCaller", "type": "bytes32"},
            {"name": "maxFee", "type": "uint256"},
            {"name": "minFinalityThreshold", "type": "uint32"}
        ],
        "name": "depositForBurn",
        "outputs": [
            {"name": "nonce", "type": "uint64"},
            {"name": "messageHash", "type": "bytes32"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")

# CCTP MessageTransmitterV2 ABI (receiveMessage)
MESSAGE_TRANSMITTER_V2_ABI = json.loads("""[
    {
        "inputs": [
            {"name": "message", "type": "bytes"},
            {"name": "attestation", "type": "bytes"}
        ],
        "name": "receiveMessage",
        "outputs": [
            {"name": "success", "type": "bool"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")


# ============================================================
# Data paths (legacy — kept for backward compat references)
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "treasury.db")

# Legacy JSON paths — no longer used for storage, only for migration detection
INVOICES_FILE = os.path.join(DATA_DIR, "invoices.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")
BUDGETS_FILE = os.path.join(DATA_DIR, "budgets.json")
