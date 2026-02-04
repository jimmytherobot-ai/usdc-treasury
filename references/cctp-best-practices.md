# CCTP Best Practices & Production Reference

> Last updated: 2026-02-04
> Covers CCTP V2 (canonical version, V1 deprecated July 2026)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [CCTP V2 vs V1 Key Differences](#2-cctp-v2-vs-v1-key-differences)
3. [Contract Addresses (V2)](#3-contract-addresses-v2)
4. [Production Implementation Patterns](#4-production-implementation-patterns)
5. [Attestation Handling Best Practices](#5-attestation-handling-best-practices)
6. [Error Recovery & Stuck Bridges](#6-error-recovery--stuck-bridges)
7. [Gas Optimization](#7-gas-optimization)
8. [Security Patterns](#8-security-patterns)
9. [Monitoring & Observability](#9-monitoring--observability)
10. [Testing Patterns](#10-testing-patterns)
11. [Recommended Improvements for Our Implementation](#11-recommended-improvements-for-our-implementation)
12. [Code Snippets & Patterns](#12-code-snippets--patterns)

---

## 1. Architecture Overview

CCTP is a **burn-and-mint** protocol for native USDC transfers across chains. No wrapped tokens, no liquidity pools.

### Core Flow (3 steps)

```
Source Chain                    Circle Iris                    Destination Chain
─────────────                  ───────────                    ──────────────────
1. depositForBurn()    ──►    2. Attest (sign message)  ──►  3. receiveMessage()
   (burns USDC)                  (offchain service)            (mints USDC)
```

### Core Contracts (V2)

| Contract | Purpose |
|----------|---------|
| **TokenMessengerV2** | Entry point — handles `depositForBurn()`, validates messages, mints tokens |
| **MessageTransmitterV2** | Sends/receives raw messages, verifies attestation signatures |
| **TokenMinterV2** | Actually mints/burns USDC tokens |
| **MessageV2** | Library for message format encoding/decoding |

### Key V2 Features

- **Fast Transfer**: Attestation in seconds (vs 15-19 minutes standard) with fee
- **Hooks**: Arbitrary post-mint execution via `hookData` parameter
- **Forwarding Service**: Circle auto-relays destination mint (no need for your own infrastructure)
- **Fees**: Variable fee model (0 bps standard, 1-14 bps fast depending on chain)
- **Denylist**: Protocol-level address blocking
- **Message Expiration**: 24-hour expiration blocks prevent stale messages

---

## 2. CCTP V2 vs V1 Key Differences

| Feature | V1 (Legacy) | V2 (Current) |
|---------|------------|--------------|
| **Speed** | 13-19 min standard only | Fast (seconds) + Standard |
| **Fees** | None | Standard: 0 bps; Fast: 1-14 bps |
| **Hooks** | ❌ | ✅ Arbitrary post-mint logic |
| **Forwarding** | ❌ | ✅ Circle relays destination tx |
| **API** | Extract MessageSent event → hash → poll /v1/attestations/{hash} | Single call: /v2/messages/{sourceDomainId}?transactionHash={hash} |
| **depositForBurn** | (amount, destDomain, mintRecipient, burnToken) | + destinationCaller, maxFee, minFinalityThreshold |
| **Nonces** | On-chain sequential | Off-chain assigned by Circle |
| **Contracts** | Non-upgradeable | Upgradeable proxies via CREATE2 |
| **Chains** | ~8 chains | 20+ chains |

### Migration: Key Breaking Changes

1. **New contract addresses** (same address on all chains via CREATE2)
2. **`depositForBurn()` signature changed** — 3 new params: `destinationCaller`, `maxFee`, `minFinalityThreshold`
3. **`depositForBurnWithCaller()` REMOVED** — use `destinationCaller` param instead
4. **`replaceDepositForBurn()` REMOVED** — no V2 equivalent
5. **New API workflow** — no more event extraction + hash + separate attestation call
6. **V1 deadline**: Phase-out begins July 31, 2026

---

## 3. Contract Addresses (V2)

### Mainnet — Same address on ALL chains (deterministic CREATE2)

| Contract | Address |
|----------|---------|
| **TokenMessengerV2** | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` |
| **MessageTransmitterV2** | `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` |
| **TokenMinterV2** | `0xfd78EE919681417d192449715b2594ab58f5D002` |
| **MessageV2** | `0xec546b6B005471ECf012e5aF77FBeC07e0FD8f78` |

Deployed on: Ethereum (0), Avalanche (1), OP Mainnet (2), Arbitrum (3), Base (6), Polygon PoS (7), Unichain (10), Linea (11), Codex (12), Sonic (13), World Chain (14), Monad (15), Sei (16), XDC (18), HyperEVM (19), Ink (21), Plume (22)

### Testnet — Same address on ALL testnets

| Contract | Address |
|----------|---------|
| **TokenMessengerV2** | `0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA` |
| **MessageTransmitterV2** | `0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275` |
| **TokenMinterV2** | `0xb43db544E2c27092c107639Ad201b3dEfAbcF192` |
| **MessageV2** | `0xbaC0179bB358A8936169a63408C8481D582390C4` |

Testnets: Ethereum Sepolia (0), Avalanche Fuji (1), OP Sepolia (2), Arbitrum Sepolia (3), Base Sepolia (6), Polygon PoS Amoy (7), Unichain Sepolia (10), Linea Sepolia (11), Codex Testnet (12), Sonic Testnet (13), World Chain Sepolia (14), Monad Testnet (15), Sei Testnet (16), XDC Apothem (18), HyperEVM Testnet (19), Ink Testnet (21), Plume Testnet (22), Arc Testnet (26)

### Domain ID Mapping

| Domain | Chain (Mainnet) | Chain (Testnet) |
|--------|----------------|-----------------|
| 0 | Ethereum | Ethereum Sepolia |
| 1 | Avalanche | Avalanche Fuji |
| 2 | OP Mainnet | OP Sepolia |
| 3 | Arbitrum | Arbitrum Sepolia |
| 5 | Solana | Solana Devnet |
| 6 | Base | Base Sepolia |
| 7 | Polygon PoS | Polygon PoS Amoy |
| 10 | Unichain | Unichain Sepolia |
| 11 | Linea | Linea Sepolia |
| 12 | Codex | Codex Testnet |
| 13 | Sonic | Sonic Testnet |
| 14 | World Chain | World Chain Sepolia |
| 15 | Monad | Monad Testnet |
| 16 | Sei | Sei Testnet |
| 17 | BNB Smart Chain | — |
| 18 | XDC | XDC Apothem |
| 19 | HyperEVM | HyperEVM Testnet |
| 21 | Ink | Ink Testnet |
| 22 | Plume | Plume Testnet |
| 25 | — | Starknet Testnet |
| 26 | — | Arc Testnet |

### API Endpoints

| Environment | Base URL |
|------------|---------|
| Testnet | `https://iris-api-sandbox.circle.com` |
| Mainnet | `https://iris-api.circle.com` |

Key endpoints:
- `GET /v2/messages/{sourceDomainId}?transactionHash={hash}` — Get message + attestation
- `POST /v2/reattest/{nonce}` — Re-attest expired/stuck messages
- `GET /v2/burn/USDC/fees/{sourceDomainId}/{destDomainId}` — Get current fees
- `GET /v2/fastBurn/USDC/allowance` — Check Fast Transfer capacity

---

## 4. Production Implementation Patterns

### Pattern A: Direct CCTP (What we do now)

```
User → approve USDC → depositForBurn() → poll attestation → receiveMessage()
```

**Pros**: Simple, no middleware
**Cons**: Must manage attestation polling, destination tx, gas on both chains

### Pattern B: Bridge Kit SDK (Circle's recommended approach)

```javascript
import { BridgeKit } from "@circle-fin/bridge-kit";
import { createAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";

const kit = new BridgeKit();
const adapter = createAdapterFromPrivateKey({ privateKey: key });

// One call handles everything
const result = await kit.bridge({
  from: { adapter, chain: "Ethereum" },
  to: { adapter, chain: "Base" },
  amount: "100",
  config: {
    transferSpeed: "FAST",  // or "STANDARD"
    maxFee: "5000000",      // Max 5 USDC fee
  },
});
```

**Pros**: Handles attestation polling, retries, gas estimation
**Cons**: TypeScript only, abstracts away control

### Pattern C: Forwarding Service (Zero destination infrastructure)

```
User → depositForBurnWithHook(hookData=forwardingMagicBytes) → Circle handles everything
```

The Forwarding Service charges $1.25 USDC (Ethereum) or $0.20 (other chains) and handles:
- Attestation fetching
- Destination chain gas
- Broadcasting the mint tx

Magic bytes for forwarding hook:
```python
# "cctp-forward" + version(0) + empty data length(0)
FORWARD_HOOK_DATA = bytes.fromhex(
    "636374702d666f72776172640000000000000000000000000000000000000000"
)
```

### Pattern D: Synapse CCTP Wrapper (Production wrapper contract)

Synapse Protocol built a full wrapper (`SynapseCCTP.sol`) that adds:
- **Fee management**: Protocol fees + relayer fees, with withdrawal functions
- **Pausability**: Owner can pause sending (but not receiving)
- **Swap integration**: Post-mint swaps via liquidity pools
- **MinimalForwarder**: CREATE2-deployed forwarders as `destinationCaller` for replay protection
- **Request tracking**: Unique request IDs from (domain, nonce, requestHash)

Key pattern — the `destinationCaller` trick:
```solidity
// Deploy a deterministic forwarder as the destinationCaller
// This prevents replay and ensures only the intended contract can call receiveMessage
function _destinationCaller(address synapseCCTP, bytes32 requestID) internal pure returns (bytes32) {
    return synapseCCTP.predictAddress(requestID).addressToBytes32();
}
```

### Pattern E: Wormhole CCTP Integration

Wormhole wraps CCTP with their own messaging layer:
- Burns USDC via CCTP + emits Wormhole message
- Automatic relayer handles attestation + VAA
- Supports composable execution on destination

---

## 5. Attestation Handling Best Practices

### V2 Workflow (Recommended)

The V2 API is dramatically simpler than V1. You no longer need to extract events and hash messages.

```python
# V2: Single API call with transaction hash
def get_attestation_v2(source_domain_id: int, tx_hash: str, max_wait=300, poll_interval=5):
    """
    Poll Circle's V2 API for message and attestation.
    Returns (message_bytes, attestation) tuple or raises.
    """
    url = f"https://iris-api.circle.com/v2/messages/{source_domain_id}"
    params = {"transactionHash": tx_hash}
    
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                if messages and messages[0].get("status") == "complete":
                    msg = messages[0]
                    return msg["message"], msg["attestation"]
        except requests.RequestException as e:
            logger.warning(f"Attestation poll error: {e}")
        
        time.sleep(poll_interval)
    
    raise TimeoutError(f"Attestation not available after {max_wait}s")
```

### Polling Strategy: Exponential Backoff

```python
def poll_with_backoff(source_domain, tx_hash, max_wait=600):
    """Production-grade attestation polling with exponential backoff."""
    base_delay = 2
    max_delay = 30
    delay = base_delay
    
    start = time.time()
    attempts = 0
    
    while time.time() - start < max_wait:
        attempts += 1
        result = check_attestation(source_domain, tx_hash)
        
        if result.status == "complete":
            return result
        
        # Exponential backoff with jitter
        jitter = random.uniform(0, delay * 0.1)
        time.sleep(delay + jitter)
        delay = min(delay * 1.5, max_delay)
    
    raise TimeoutError(f"No attestation after {attempts} attempts ({max_wait}s)")
```

### Rate Limits

- **35 requests/second** per service instance
- Exceeding = **5-minute block** (HTTP 429)
- For high-volume: space requests, use backoff, share rate limit budget

### Fast vs Standard Transfer Timing

| Transfer Type | minFinalityThreshold | Typical Time |
|--------------|---------------------|-------------|
| Fast | ≤ 1000 | 8-20 seconds |
| Standard | ≥ 2000 | 8 seconds (Avalanche) to 6-32 hours (Linea) |

---

## 6. Error Recovery & Stuck Bridges

### Failure Modes

| Failure | Cause | Recovery |
|---------|-------|---------|
| Burn tx reverts | Insufficient balance, bad params | Check balance + params, retry |
| Attestation never comes | Iris outage, reorg | Use `/v2/reattest/{nonce}` endpoint |
| Attestation expired | 24-hour expiration block | Call `/v2/reattest/{nonce}` to get fresh attestation |
| Mint tx reverts | Nonce already used, bad attestation | Check if already minted (idempotent), verify attestation |
| Mint tx gas too low | L1 gas spike (L2 chains) | Retry with higher gas |

### Re-attestation (V2 Only)

```python
def reattest_message(nonce: str):
    """Re-attest a V2 message that expired or needs finality upgrade."""
    url = f"https://iris-api.circle.com/v2/reattest/{nonce}"
    resp = requests.post(url, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    raise RuntimeError(f"Reattest failed: {resp.status_code} {resp.text}")
```

### Idempotency Check

Before calling `receiveMessage`, check if the nonce is already used:

```python
def is_nonce_used(w3, message_transmitter_addr, nonce_bytes32):
    """Check if a CCTP nonce has already been consumed."""
    transmitter = w3.eth.contract(address=message_transmitter_addr, abi=MT_ABI)
    return transmitter.functions.usedNonces(nonce_bytes32).call() != 0
```

### Persistence Pattern (What our code already does well)

```python
# Store bridge state in SQLite at each step:
# 1. After burn tx confirmed → status: "burn_confirmed"
# 2. After attestation received → status: "attestation_received"
# 3. After mint tx confirmed → status: "completed"
# 
# Resume from any state with: cctp.py complete <burn_tx_hash>
```

---

## 7. Gas Optimization

### Source Chain (Burn)

- **Infinite approval**: Approve `type(uint256).max` once, save gas on subsequent burns
  ```python
  # Synapse pattern: approve once, check allowance before each tx
  if allowance < amount:
      if allowance != 0:
          approve(spender, 0)  # Reset first (required by some tokens)
      approve(spender, MAX_UINT256)
  ```

- **Gas estimation**: Use `eth_estimateGas` instead of hardcoded gas limits
  ```python
  gas_estimate = w3.eth.estimate_gas(tx)
  tx["gas"] = int(gas_estimate * 1.2)  # 20% buffer
  ```

- **EIP-1559 transactions** on supported chains (Ethereum, Base, Arbitrum):
  ```python
  tx["maxFeePerGas"] = w3.eth.gas_price * 2
  tx["maxPriorityFeePerGas"] = w3.to_wei(1, "gwei")
  # Remove "gasPrice" key
  ```

### Destination Chain (Mint)

- **Forwarding Service eliminates this entirely** — Circle pays gas from maxFee
- If self-relaying: pre-fund gas wallets on destination chains
- `receiveMessage` typically costs ~150k-250k gas

### V2 Fee Optimization

- **Standard Transfer**: 0 bps fee — use when speed isn't critical
- **Fast Transfer**: 1-14 bps — use for time-sensitive operations
- Query fees before sending: `GET /v2/burn/USDC/fees/{src}/{dst}`

---

## 8. Security Patterns

### From Circle's Contracts

1. **Denylist**: V2 has a `notDenylistedCallers` modifier — addresses can be blocked
2. **Pause mechanism**: `whenNotPaused` on `sendMessage` and `receiveMessage`
3. **Rescuable**: Owner can rescue stuck tokens from contracts
4. **Attestation verification**: Multi-attester with configurable threshold (signatures must be in increasing order of attester address)
5. **Message expiration**: 24-hour expiration blocks prevent stale message replay
6. **Nonce uniqueness**: Each nonce can only be used once (checked via `usedNonces` mapping)

### From Synapse's Wrapper

1. **Pausable sending** (but not receiving — always accept incoming funds)
2. **Owner-only config changes**: Remote domain config, token pool addresses
3. **Fee collection**: Separate protocol fees vs relayer fees
4. **CREATE2 forwarders as destinationCaller**: Prevents unauthorized mint claiming

### For Our Treasury Skill

```python
# Recommended security checklist:
SECURITY_CHECKS = {
    "amount_cap": 10_000,           # Max single bridge: $10k USDC
    "daily_limit": 50_000,          # Max daily: $50k USDC
    "allowed_chains": ["base_sepolia", "ethereum_sepolia", "arbitrum_sepolia"],
    "allowed_recipients": [TREASURY_WALLET],  # Whitelist recipients
    "require_confirmation": True,    # Human approval for large amounts
    "confirmation_threshold": 1_000, # Amounts over $1k need confirmation
}
```

### Best Practices

1. **Set `destinationCaller`** to a specific address (not `bytes32(0)`) to prevent front-running
2. **Rate limit bridges** — don't allow unlimited bridging frequency
3. **Cap amounts** — especially on testnet, but even more on mainnet
4. **Whitelist recipients** — prevent funds being minted to unknown addresses
5. **Monitor for anomalies** — unusual amounts, frequencies, or destinations
6. **Use the Forwarding Service** for mainnet to avoid managing destination gas wallets

---

## 9. Monitoring & Observability

### What to Monitor

```python
MONITORING_METRICS = {
    # Bridge health
    "attestation_latency_seconds",    # Time between burn tx and attestation
    "end_to_end_bridge_seconds",      # Total time: burn → mint
    "bridge_success_rate",            # % of bridges completing successfully
    "pending_bridges_count",          # Bridges stuck in intermediate states
    
    # API health
    "iris_api_response_time_ms",      # Circle API latency
    "iris_api_error_rate",            # 429s, 500s, timeouts
    
    # Financial
    "daily_bridge_volume_usdc",       # Total bridged per day
    "fees_paid_usdc",                 # Fees to Circle
    "gas_spent_native",               # Gas on both chains
    
    # Security
    "failed_bridge_count",            # Bridges that failed at any step
    "unusual_amount_alerts",          # Amounts above threshold
}
```

### Alerting Rules

- Bridge pending > 30 minutes → Warning
- Bridge pending > 2 hours → Critical
- Attestation API returning 429 → Throttle and alert
- Daily volume exceeds limit → Block new bridges
- Unknown recipient address → Block and alert

### Bridge State Machine

```
                    ┌──────────────┐
                    │   INITIATED  │
                    └──────┬───────┘
                           │ approve tx
                    ┌──────▼───────┐
                    │   APPROVED   │
                    └──────┬───────┘
                           │ depositForBurn tx
                    ┌──────▼───────┐
                    │BURN_CONFIRMED│──────────┐
                    └──────┬───────┘          │ burn reverted
                           │ attestation      │
                    ┌──────▼───────────┐ ┌────▼─────┐
                    │ATTESTATION_READY │ │  FAILED   │
                    └──────┬───────────┘ └──────────┘
                           │ receiveMessage tx
                    ┌──────▼───────┐
                    │  COMPLETED   │
                    └──────────────┘
```

---

## 10. Testing Patterns

### Unit Testing CCTP Integration

```python
# Mock the attestation API
@pytest.fixture
def mock_attestation():
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://iris-api-sandbox.circle.com/v2/messages/0",
            json={
                "messages": [{
                    "message": "0xabc...",
                    "attestation": "0xdef...",
                    "status": "complete",
                    "decodedMessage": {...}
                }]
            },
            status=200,
        )
        yield rsps
```

### Integration Testing on Testnet

1. Use Sepolia USDC faucet (Circle provides testnet USDC)
2. Bridge small amounts (1 USDC) between Sepolia ↔ Base Sepolia
3. Verify full round-trip: burn → attestation → mint → balance check
4. Test failure scenarios:
   - Cancel before attestation (not possible — burn is final)
   - Resume a pending bridge after restart
   - Double-claim protection (try receiveMessage twice)

### Foundry Testing (for Solidity wrappers)

Circle's repo uses Foundry with `forge test`:
```bash
# Run all tests
forge test

# Run with verbosity (shows console.log)
forge test -vv

# Integration test with anvil
make anvil-test
```

---

## 11. Recommended Improvements for Our Implementation

### Priority 1: Migrate to V2 API Workflow

**Current**: We extract `MessageSent` event from logs, keccak256 hash it, poll `/v1/attestations/{hash}`

**Should be**: Single call to `/v2/messages/{sourceDomainId}?transactionHash={hash}`

```python
# BEFORE (what we do now - V1 style)
for log in burn_receipt.logs:
    if log.address.lower() == msg_transmitter_addr.lower():
        message_bytes = log.data
        message_hash = Web3.keccak(log.data).hex()
        break
url = f"{CCTP_ATTESTATION_API}/{message_hash}"

# AFTER (V2 style - much simpler)
url = f"https://iris-api-sandbox.circle.com/v2/messages/{src_cfg['cctp_domain']}"
params = {"transactionHash": burn_tx_hash}
resp = requests.get(url, params=params, timeout=10)
data = resp.json()
message = data["messages"][0]["message"]
attestation = data["messages"][0]["attestation"]
```

### Priority 2: Exponential Backoff for Attestation Polling

**Current**: Fixed 10-second interval

**Should be**: Start at 2s, backoff to 30s, with jitter

### Priority 3: EIP-1559 Gas Handling

**Current**: Legacy `gasPrice` transactions

**Should be**: EIP-1559 `maxFeePerGas` + `maxPriorityFeePerGas` on supported chains

### Priority 4: Add Forwarding Service Support

For mainnet deployment, use Circle's Forwarding Service to eliminate managing destination-chain infrastructure:

```python
FORWARD_HOOK_DATA = bytes.fromhex(
    "636374702d666f72776172640000000000000000000000000000000000000000"
)

# Use depositForBurnWithHook instead of depositForBurn
# maxFee must cover protocol fee + forwarding fee ($0.20 or $1.25)
```

### Priority 5: Better Error Recovery

- Add `reattest` support for expired messages
- Check nonce usage before attempting mint (idempotency)
- Store more detailed state transitions in SQLite

### Priority 6: Add Mainnet Config with Safety Guards

```python
MAINNET_CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "chain_id": 1,
        "cctp_domain": 0,
        "token_messenger_v2": "0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d",
        "message_transmitter_v2": "0x81D40F21F12A8F0E3252Bccb954D722d4c464B64",
        # ...
    },
    # ... other chains
}

# Safety guards for mainnet
MAINNET_GUARDS = {
    "max_single_bridge": 10_000,    # $10k max per bridge
    "daily_limit": 50_000,          # $50k daily limit
    "require_confirmation": True,    # Always confirm mainnet
    "allowed_recipients": [TREASURY_WALLET],
}
```

### Priority 7: Support Fast Transfer

Add option for fast transfer (seconds instead of minutes):

```python
def bridge_usdc(source, dest, amount, speed="standard"):
    if speed == "fast":
        min_finality = 1000  # Fast
        # Query fee first
        fee_resp = requests.get(
            f"{IRIS_API}/v2/burn/USDC/fees/{src_domain}/{dst_domain}"
        )
        max_fee = calculate_max_fee(fee_resp.json(), amount)
    else:
        min_finality = 2000  # Standard
        max_fee = 0          # No fee for standard
```

---

## 12. Code Snippets & Patterns

### Complete V2 Bridge Flow (Python)

```python
"""Complete CCTP V2 bridge with best practices."""

import time
import random
import requests
from web3 import Web3
from decimal import Decimal

class CCTPBridgeV2:
    """Production-grade CCTP V2 bridge with best practices."""
    
    IRIS_API_MAINNET = "https://iris-api.circle.com"
    IRIS_API_TESTNET = "https://iris-api-sandbox.circle.com"
    
    FORWARD_HOOK = bytes.fromhex(
        "636374702d666f72776172640000000000000000000000000000000000000000"
    )
    
    def __init__(self, chains_config, private_key, is_testnet=True):
        self.chains = chains_config
        self.private_key = private_key
        self.iris_api = self.IRIS_API_TESTNET if is_testnet else self.IRIS_API_MAINNET
    
    def bridge(self, source, dest, amount, recipient=None, speed="standard", use_forwarding=False):
        """Full bridge flow with proper error handling."""
        src_cfg = self.chains[source]
        dst_cfg = self.chains[dest]
        w3 = Web3(Web3.HTTPProvider(src_cfg["rpc"]))
        account = w3.eth.account.from_key(self.private_key)
        
        # 1. Approve (infinite, check first)
        self._ensure_approval(w3, src_cfg, account, amount)
        
        # 2. Calculate fee
        max_fee, min_finality = self._get_fee_params(
            src_cfg["cctp_domain"], dst_cfg["cctp_domain"], amount, speed
        )
        
        # 3. Burn
        if use_forwarding:
            burn_hash = self._deposit_for_burn_with_hook(
                w3, src_cfg, dst_cfg, account, amount, recipient, max_fee, min_finality
            )
            return {"burn_tx": burn_hash, "status": "forwarding"}
        else:
            burn_hash = self._deposit_for_burn(
                w3, src_cfg, dst_cfg, account, amount, recipient, max_fee, min_finality
            )
        
        # 4. Get attestation (V2 API)
        message, attestation = self._poll_attestation_v2(
            src_cfg["cctp_domain"], burn_hash
        )
        
        # 5. Mint on destination
        mint_hash = self._receive_message(dst_cfg, message, attestation)
        
        return {
            "burn_tx": burn_hash,
            "mint_tx": mint_hash,
            "status": "completed"
        }
    
    def _poll_attestation_v2(self, source_domain, tx_hash, max_wait=600):
        """V2 API: Single endpoint for message + attestation."""
        url = f"{self.iris_api}/v2/messages/{source_domain}"
        params = {"transactionHash": tx_hash}
        
        delay = 2
        max_delay = 30
        start = time.time()
        
        while time.time() - start < max_wait:
            try:
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    msgs = data.get("messages", [])
                    if msgs and msgs[0].get("status") == "complete":
                        return msgs[0]["message"], msgs[0]["attestation"]
                elif resp.status_code == 429:
                    delay = min(delay * 3, 120)  # Aggressive backoff on rate limit
            except requests.RequestException:
                pass
            
            jitter = random.uniform(0, delay * 0.1)
            time.sleep(delay + jitter)
            delay = min(delay * 1.5, max_delay)
        
        raise TimeoutError(f"Attestation timeout after {max_wait}s")
    
    def _get_fee_params(self, src_domain, dst_domain, amount, speed):
        """Query Circle API for current fees."""
        if speed == "fast":
            resp = requests.get(
                f"{self.iris_api}/v2/burn/USDC/fees/{src_domain}/{dst_domain}"
            )
            if resp.status_code == 200:
                fee_data = resp.json()
                # Calculate maxFee from fee schedule
                # Add 10% buffer for fee fluctuation
                fee_bps = fee_data.get("fastFee", {}).get("basisPoints", 20)
                max_fee = int(amount * fee_bps / 10000 * 1.1)
                return max_fee, 1000
        
        return 0, 2000  # Standard: no fee, finalized finality
```

### Synapse-Style Fee Management (Solidity)

```solidity
// Key pattern from SynapseCCTP.sol
// Separate protocol fees from relayer fees

mapping(address => mapping(address => uint256)) public accumulatedFees;
// accumulatedFees[address(0)][token] = protocol fees
// accumulatedFees[relayer][token] = relayer fees

function withdrawProtocolFees(address token) external onlyOwner {
    uint256 fees = accumulatedFees[address(0)][token];
    require(fees > 0);
    accumulatedFees[address(0)][token] = 0;
    IERC20(token).safeTransfer(msg.sender, fees);
}
```

### Forwarding Service Hook Data

```python
# For automatic destination-chain relaying by Circle
def build_forwarding_hook():
    """Build hook data for Circle's Forwarding Service."""
    magic = b"cctp-forward"               # 12 bytes
    padding = b"\x00" * 12               # pad to 24 bytes
    version = (0).to_bytes(4, "big")     # uint32 version = 0
    data_length = (0).to_bytes(4, "big") # uint32 additional data length = 0
    return magic + padding + version + data_length
```

---

## Sources

- [Circle CCTP Docs](https://developers.circle.com/cctp)
- [Circle CCTP Technical Guide](https://developers.circle.com/cctp/references/technical-guide)
- [Circle V1→V2 Migration Guide](https://developers.circle.com/cctp/migration-from-v1-to-v2)
- [Circle EVM CCTP Contracts (GitHub)](https://github.com/circlefin/evm-cctp-contracts)
- [Circle Bridge Kit](https://developers.circle.com/bridge-kit)
- [Circle Forwarding Service](https://developers.circle.com/cctp/concepts/forwarding-service)
- [Synapse CCTP Wrapper](https://github.com/synapsecns/synapse-contracts/blob/master/contracts/cctp/SynapseCCTP.sol)
- [Wormhole CCTP Bridge](https://wormhole.com/docs/products/cctp-bridge/)
- [LI.FI CCTP Deep Dive](https://li.fi/knowledge-hub/circles-cross-chain-transfer-protocol-cctp-a-deep-dive/)
- [ChainSecurity CCTP V2 Audit](https://6778953.fs1.hubspotusercontent-na1.net/hubfs/6778953/PDFs/ChainSecurity_Circle_CCTP_V2_audit%20(1).pdf)
