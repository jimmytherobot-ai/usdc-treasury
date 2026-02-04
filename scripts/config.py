"""
USDC Treasury - Configuration and Constants
Testnet contract addresses, chain configs, ABIs

All configuration can be overridden via environment variables:
- TREASURY_PRIVATE_KEY / ETH_PRIVATE_KEY — wallet private key
- TREASURY_WALLET — wallet address (or derived from private key)
- TREASURY_DATA_DIR — data directory (default: <skill>/data/)
- TREASURY_RPC_ETHEREUM_SEPOLIA — override Ethereum Sepolia RPC
- TREASURY_RPC_BASE_SEPOLIA — override Base Sepolia RPC
- TREASURY_RPC_ARBITRUM_SEPOLIA — override Arbitrum Sepolia RPC
"""

import os
import json
import subprocess


def _load_dotenv():
    """Load .env file from skill root if it exists. No dependencies required."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Don't override existing env vars
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# ============================================================
# Chain Configuration
# ============================================================

CHAINS = {
    "ethereum_sepolia": {
        "name": "Ethereum Sepolia",
        "chain_id": 11155111,
        "rpc": os.environ.get("TREASURY_RPC_ETHEREUM_SEPOLIA",
                              "https://ethereum-sepolia-rpc.publicnode.com"),
        "explorer": "https://sepolia.etherscan.io",
        "usdc_address": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        "cctp_domain": 0,
        "token_messenger_v2": "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA",
        "message_transmitter_v2": "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275",
    },
    "base_sepolia": {
        "name": "Base Sepolia",
        "chain_id": 84532,
        "rpc": os.environ.get("TREASURY_RPC_BASE_SEPOLIA",
                              "https://base-sepolia-rpc.publicnode.com"),
        "explorer": "https://base-sepolia.blockscout.com",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "cctp_domain": 6,
        "token_messenger_v2": "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA",
        "message_transmitter_v2": "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275",
    },
    "arbitrum_sepolia": {
        "name": "Arbitrum Sepolia",
        "chain_id": 421614,
        "rpc": os.environ.get("TREASURY_RPC_ARBITRUM_SEPOLIA",
                              "https://arbitrum-sepolia-rpc.publicnode.com"),
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

def _is_macos():
    """Check if running on macOS."""
    import platform
    return platform.system() == "Darwin"


def get_private_key():
    """
    Retrieve private key. Resolution order:
    1. TREASURY_PRIVATE_KEY env var         (works everywhere)
    2. ETH_PRIVATE_KEY env var              (common convention)
    3. Secret helper script                 (if TREASURY_SECRET_CMD is set)
    4. macOS Keychain                       (if on macOS and configured)
    """
    # 1-2. Environment variables — primary method
    key = os.environ.get("TREASURY_PRIVATE_KEY") or os.environ.get("ETH_PRIVATE_KEY")
    if key:
        return key if key.startswith("0x") else f"0x{key}"

    # 3. Secret helper command (e.g. KeePassXC, Vault, 1Password CLI, etc.)
    #    Set TREASURY_SECRET_CMD to the full command that prints the key to stdout.
    #    Example: TREASURY_SECRET_CMD="op read op://Vault/eth-key/password"
    #    Example: TREASURY_SECRET_CMD="/path/to/get-secret.sh my-wallet-key"
    secret_cmd = os.environ.get("TREASURY_SECRET_CMD")
    if secret_cmd:
        try:
            result = subprocess.run(
                secret_cmd, shell=True,
                capture_output=True, text=True, timeout=10
            )
            key = result.stdout.strip()
            if key and len(key) >= 64 and result.returncode == 0:
                return key if key.startswith("0x") else f"0x{key}"
        except Exception:
            pass

    # 4. macOS Keychain (only on macOS — skipped silently on Linux/Docker)
    if _is_macos():
        kc_account = os.environ.get("TREASURY_KEYCHAIN_ACCOUNT", "")
        kc_service = os.environ.get("TREASURY_KEYCHAIN_SERVICE", "")
        if kc_account and kc_service:
            try:
                result = subprocess.run(
                    ["security", "find-generic-password",
                     "-a", kc_account, "-s", kc_service, "-w"],
                    capture_output=True, text=True, timeout=10
                )
                key = result.stdout.strip()
                if key and len(key) >= 64:
                    return key if key.startswith("0x") else f"0x{key}"
            except Exception:
                pass

    raise RuntimeError(
        "No private key found. Set the TREASURY_PRIVATE_KEY environment variable.\n"
        "Example: export TREASURY_PRIVATE_KEY=0xYourPrivateKeyHere\n"
        "See SKILL.md for all configuration options."
    )


def _resolve_wallet():
    """
    Resolve wallet address. Order:
    1. TREASURY_WALLET env var
    2. Derived from private key (if available)
    Returns None if neither is available (read-only mode still works for some operations).
    """
    addr = os.environ.get("TREASURY_WALLET")
    if addr:
        return addr
    # Try deriving from private key
    try:
        from web3 import Web3
        key = get_private_key()
        return Web3().eth.account.from_key(key).address
    except Exception:
        return None


TREASURY_WALLET = _resolve_wallet()


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

DATA_DIR = os.environ.get("TREASURY_DATA_DIR", 
                         os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "treasury.db")

# Legacy JSON paths — no longer used for storage, only for migration detection
INVOICES_FILE = os.path.join(DATA_DIR, "invoices.json")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.json")
BUDGETS_FILE = os.path.join(DATA_DIR, "budgets.json")
