# CCTP Production Implementations Reference

> Last updated: 2026-02-04
> Catalog of real-world CCTP integrations, what they do, and what we can learn

---

## Implementation Matrix

| Project | Type | Repo | CCTP Version | Language | Key Differentiator |
|---------|------|------|-------------|----------|-------------------|
| **Circle EVM Contracts** | Core protocol | [circlefin/evm-cctp-contracts](https://github.com/circlefin/evm-cctp-contracts) | V2 | Solidity 0.7.6 | Reference implementation, canonical |
| **Circle Bridge Kit** | SDK | [@circle-fin/bridge-kit](https://www.npmjs.com/package/@circle-fin/bridge-kit) | V2 | TypeScript | Official SDK, handles everything |
| **Circle Forwarding Service** | Infrastructure | N/A (Circle-hosted) | V2 | N/A | Zero destination infrastructure |
| **Synapse Protocol** | Wrapper contract | [synapsecns/synapse-contracts](https://github.com/synapsecns/synapse-contracts/blob/master/contracts/cctp/SynapseCCTP.sol) | V1 (migrating) | Solidity 0.8.17 | Fee mgmt, swap integration, replay protection |
| **Wormhole CCTP Bridge** | Cross-protocol bridge | [wormhole-foundation/wormhole](https://github.com/wormhole-foundation/wormhole) | V1+V2 | Solidity + TS | Composable with Wormhole messaging |
| **Wormhole SDK** | SDK | [@wormhole-foundation/sdk](https://www.npmjs.com/package/@wormhole-foundation/sdk) | V1+V2 | TypeScript | Multi-chain, auto/manual relaying |
| **LI.FI** | Bridge aggregator | [lifinance/sdk](https://github.com/lifinance/sdk) | V2 | TypeScript | Routes through CCTP when optimal |
| **Socket / Bungee** | Bridge aggregator | [socket.tech](https://docs.socket.tech) | V2 | TypeScript/Solidity | Cross-chain abstraction layer |
| **Circle Sample Scripts** | Reference | [circlefin/circle-cctp-crosschain-transfer](https://github.com/circlefin/circle-cctp-crosschain-transfer) | V1+V2 | TypeScript | Simple tutorial code |
| **Circle Bridge Kit Transfer Demo** | Demo | [circlefin/circle-bridge-kit-transfer](https://github.com/circlefin/circle-bridge-kit-transfer) | V2 | TypeScript | Wallet-connect demo app |
| **Our Treasury Skill** | Treasury tool | local: skills/usdc-treasury | V2 | Python | Agent-controlled treasury bridging |

---

## Detailed Analysis

### 1. Circle EVM CCTP Contracts (Canonical)

**Repo**: https://github.com/circlefin/evm-cctp-contracts

**What it is**: The actual deployed CCTP contracts. This IS the protocol.

**Key contracts (V2)**:
- `src/v2/TokenMessengerV2.sol` — Entry point for burns and mints
- `src/v2/MessageTransmitterV2.sol` — Message sending/receiving, attestation verification
- `src/v2/BaseTokenMessenger.sol` — Shared admin logic (roles, fee config, minter management)
- `src/v2/BaseMessageTransmitter.sol` — Shared message logic (attester management, nonces)
- `src/messages/v2/BurnMessageV2.sol` — Burn message format library
- `src/messages/v2/MessageV2.sol` — Top-level message format library
- `src/roles/v2/Denylistable.sol` — Address denylist functionality

**Architecture patterns we should note**:
- **Upgradeable proxies** via CREATE2Factory — deterministic addresses across all chains
- **Role separation**: owner, rescuer, pauser, attesterManager, feeRecipient, denylister, minFeeController — each with specific privileges
- **Dual receive handlers**: `handleReceiveFinalizedMessage` vs `handleReceiveUnfinalizedMessage` — allows recipient contracts to differentiate by finality level
- **Fee model**: `minFee` in 1/1000 basis points with `MIN_FEE_MULTIPLIER = 10_000_000`
- **Message expiration**: 24-hour `expirationBlock` to prevent stale replay

**Lessons**:
1. Use separate roles for different admin functions (don't put everything on `owner`)
2. Support both finalized and unfinalized message handling
3. Fee precision matters — use enough decimal places
4. Message expiration is a safety net worth implementing

---

### 2. Circle Bridge Kit SDK

**Package**: `@circle-fin/bridge-kit` + adapters (`@circle-fin/adapter-viem-v2`, `@circle-fin/adapter-ethers-v6`, `@circle-fin/adapter-solana-kit`)

**What it does**: Abstracts the entire CCTP flow into a few lines of code:

```typescript
import { BridgeKit } from "@circle-fin/bridge-kit";
import { createAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";

const kit = new BridgeKit();
const adapter = createAdapterFromPrivateKey({
  privateKey: process.env.PRIVATE_KEY,
});

const result = await kit.bridge({
  from: { adapter, chain: "Ethereum" },
  to: { adapter, chain: "Base" },
  amount: "100",
  config: {
    transferSpeed: "FAST",
    maxFee: "5000000",
  },
});
```

**Key features**:
- Handles approval, burn, attestation polling, and mint in one call
- Built-in fee calculation
- Type-safe chain/token handling
- Monetization support (collect fees from transfers)
- Multi-adapter (viem, ethers, Solana, Circle Wallets)

**Lessons**:
1. If building a JS/TS app, use this instead of raw contract calls
2. Our Python implementation can mirror its interface design
3. The "transfer speed" abstraction is clean — we should support it

---

### 3. Circle Forwarding Service

**What it is**: Circle-hosted infrastructure that automatically handles the destination chain mint transaction.

**How to use it**: Include magic bytes in `hookData` when calling `depositForBurnWithHook`:

```python
# Static forwarding hook data
FORWARD_HOOK = bytes.fromhex(
    "636374702d666f72776172640000000000000000000000000000000000000000"
)
# "cctp-forward" (24 bytes) + version uint32(0) + data_length uint32(0)
```

**Fees**:
- Ethereum destination: $1.25 USDC
- All other chains: $0.20 USDC
- Fee comes from `maxFee` parameter

**Supported chains**: Arbitrum, Avalanche, Base, Ethereum, HyperEVM, Ink, Linea, Monad, OP Mainnet, Polygon PoS, Sei, Sonic, Unichain, World Chain

**Lessons**:
1. **This is the recommended approach for mainnet** — eliminates managing gas wallets on destination chains
2. Trade-off: slightly higher cost ($0.20-$1.25) vs managing your own infrastructure
3. For a treasury tool, the forwarding service is perfect — set and forget
4. No need to set `destinationCaller` (forwarding doesn't support it)

---

### 4. Synapse Protocol (SynapseCCTP.sol)

**Repo**: https://github.com/synapsecns/synapse-contracts/blob/master/contracts/cctp/SynapseCCTP.sol

**What it is**: A production wrapper contract that adds business logic on top of raw CCTP.

**Key features analyzed from source code**:

#### Fee Management
```solidity
// Two-tier fee model: protocol + relayer
mapping(address => mapping(address => uint256)) public accumulatedFees;
// accumulatedFees[address(0)][token] = protocol fees
// accumulatedFees[relayer][token] = relayer fees

function withdrawProtocolFees(address token) external onlyOwner { ... }
function withdrawRelayerFees(address token) external { ... }  // Anyone can claim their own
```

#### Pausable Sending (but not receiving!)
```solidity
function pauseSending() external onlyOwner { _pause(); }
function unpauseSending() external onlyOwner { _unpause(); }
// Note: receiveCircleToken is NOT guarded by whenNotPaused
// This is deliberate — always accept incoming funds
```

#### Replay Protection via CREATE2 Forwarders
```solidity
// For each bridge request, deploy a deterministic MinimalForwarder
// That forwarder becomes the destinationCaller, preventing unauthorized claims
function _mintCircleToken(bytes calldata message, bytes calldata signature, bytes32 requestID) internal {
    address forwarder = MinimalForwarderLib.deploy(requestID);
    bytes memory payload = abi.encodeWithSelector(
        IMessageTransmitter.receiveMessage.selector, message, signature
    );
    bytes memory returnData = forwarder.forwardCall(address(messageTransmitter), payload);
    if (!abi.decode(returnData, (bool))) revert CCTPMessageNotReceived();
}
```

#### Post-Mint Swap Integration
```solidity
// After minting USDC, optionally swap to another token via a configured pool
mapping(address => address) public circleTokenPool;

function _fulfillRequest(address recipient, address token, uint256 amount, bytes memory swapParams)
    internal returns (address tokenOut, uint256 amountOut)
{
    if (swapParams.length == 0) {
        // No swap — just transfer USDC
        IERC20(token).safeTransfer(recipient, amount);
        return (token, amount);
    }
    address pool = circleTokenPool[token];
    if (pool == address(0)) {
        // Fallback — no pool configured
        IERC20(token).safeTransfer(recipient, amount);
        return (token, amount);
    }
    // Try swap, fallback to raw transfer if swap fails
    amountOut = _trySwap(pool, tokenIndexFrom, tokenIndexTo, amount, deadline, minAmountOut);
    if (amountOut == 0) {
        IERC20(token).safeTransfer(recipient, amount);
        return (token, amount);
    }
    IERC20(tokenOut).safeTransfer(recipient, amountOut);
}
```

**Lessons we can steal**:
1. **Pause sending but not receiving** — critical safety pattern
2. **Separate protocol fees from relayer fees** — useful for multi-party systems
3. **Graceful swap fallback** — if swap fails, just send USDC (never lose funds)
4. **Use requestID as unique identifier** — hash of (domain, nonce, request) ensures global uniqueness
5. **Infinite approve pattern** — check allowance, reset to 0 if non-zero, then set to max
6. **Store balance-before, verify balance-after** — protects against unexpected transfer behavior

---

### 5. Wormhole CCTP Bridge

**Repo**: https://github.com/wormhole-foundation/wormhole
**SDK**: `@wormhole-foundation/sdk`
**Demo**: https://github.com/wormhole-foundation/demo-cctp-transfer

**What it does**: Wraps CCTP with Wormhole's generic messaging layer for composability.

**Architecture**:
```
Source Chain:
  User → CircleIntegration contract → {
    1. Custody USDC
    2. Approve + call depositForBurnWithCaller
    3. Emit Wormhole message with payload
  }

Wormhole Network:
  - Guardian network observes both CCTP burn and Wormhole message
  - Signs VAA (Verified Action Approval)
  - Fetches Circle attestation

Destination Chain:
  Relayer → CircleIntegration contract → {
    1. Verify VAA
    2. Call receiveMessage with Circle attestation
    3. Execute custom logic from payload
  }
```

**Two modes**:
1. **Automatic**: Submit tx, relayer handles everything (recommended for production)
2. **Manual**: Fetch VAA + attestation yourself, call redeem

**Lessons**:
1. **Composability**: Wormhole adds arbitrary payload alongside CCTP burn — enables complex cross-chain logic
2. **Relayer pattern**: Having a relayer service watch for events and auto-complete is production-grade
3. **ReentrancyGuard**: Their contracts use it — important for any contract handling tokens
4. **Recovery flow**: If relayer fails, manual VAA fetch + attestation fetch + redeem

---

### 6. LI.FI Bridge Aggregator

**Repo**: https://github.com/lifinance/sdk
**Contracts**: https://github.com/lifinance/contracts (diamond proxy pattern)

**What it does**: Routes cross-chain swaps through the optimal bridge. CCTP is one of many bridge options.

**How they wrap CCTP**:
- Use a Diamond (EIP-2535) proxy pattern with facets for each bridge
- CCTP facet handles approval → depositForBurn → attestation → receiveMessage
- SDK handles routing logic: given source/dest/token, pick the best bridge
- CCTP chosen when: USDC transfer, supported chain pair, best cost/speed tradeoff

**Integration pattern**:
```typescript
import { createConfig, getQuote, executeRoute } from '@lifi/sdk';

createConfig({ integrator: 'your-app' });

// SDK automatically considers CCTP for USDC routes
const quote = await getQuote({
  fromChain: 'ETH',
  toChain: 'BASE',
  fromToken: 'USDC',
  toToken: 'USDC',
  fromAmount: '1000000000', // 1000 USDC
});

const result = await executeRoute(quote.route);
```

**Lessons**:
1. **Aggregation layer**: Don't hardcode one bridge — abstract so you can add alternatives
2. **Diamond pattern**: If building an on-chain wrapper, facets allow upgradeable bridge integrations
3. **Quote before execute**: Always check fees/speed before initiating a bridge

---

### 7. Socket / Bungee

**Docs**: https://docs.socket.tech

**What it does**: Similar to LI.FI — a cross-chain abstraction layer that routes through CCTP among other bridges.

**How they integrate CCTP**:
- SocketGateway contract handles approvals and bridge calls
- API returns optimal route including CCTP for USDC
- SDK provides transaction builder for the selected route

**Lessons**:
1. API-first approach — build quotes server-side, execute client-side
2. Transaction builder pattern — separate quote from execution

---

## What Each Implementation Does Differently

| Feature | Circle Core | Bridge Kit | Forwarding | Synapse | Wormhole | LI.FI |
|---------|-------------|-----------|------------|---------|----------|-------|
| **Attestation** | Raw API | Auto-handled | Circle-handled | Relayer polls | Guardian network | SDK handles |
| **Destination tx** | Manual | Auto-handled | Circle relays | Relayer submits | Relayer/manual | SDK handles |
| **Fee model** | Protocol fee | Pass-through | +$0.20-$1.25 | Protocol + relayer | Wormhole fees | Aggregator fee |
| **Access control** | Multi-role | Wallet-based | N/A | Ownable + pausable | ReentrancyGuard | Diamond admin |
| **Post-mint logic** | Hooks | N/A | N/A | Swap integration | Arbitrary payload | Multi-hop swaps |
| **Error recovery** | Reattest API | Auto-retry | Auto-retry | Manual resume | VAA re-fetch | SDK retry |
| **Gas mgmt** | Manual both chains | Auto both chains | Source only | Relayer covers | Relayer covers | SDK handles |

---

## Patterns Worth Stealing for Our Implementation

### 1. V2 API Workflow (from Circle docs)
Replace our V1-style event extraction with a single V2 API call. **Priority: HIGH**

### 2. Forwarding Service (from Circle)
Use magic bytes in hookData to eliminate destination chain management. **Priority: HIGH for mainnet**

### 3. Pause Sending Not Receiving (from Synapse)
Allow emergency pause of new bridges but always complete incoming ones. **Priority: MEDIUM**

### 4. Exponential Backoff with Jitter (from Wormhole/general)
Replace our fixed 10s polling with progressive backoff. **Priority: MEDIUM**

### 5. Fast Transfer Support (from Circle V2)
Add `speed="fast"` option with proper fee querying. **Priority: MEDIUM**

### 6. Balance-Before/After Verification (from Synapse)
Verify token balances before and after each operation. **Priority: MEDIUM**

### 7. Infinite Approval Pattern (from Synapse)
Check allowance → reset to 0 → set to max. Save gas on repeated bridges. **Priority: LOW**

### 8. Bridge Aggregation Interface (from LI.FI/Socket)
Abstract bridge selection so we could add alternatives to CCTP later. **Priority: LOW**

### 9. Reattest Support (from Circle V2 API)
Handle expired messages by calling POST /v2/reattest/{nonce}. **Priority: LOW**

### 10. Nonce Idempotency Check (from Circle contracts)
Before calling receiveMessage, check if nonce is already used. **Priority: LOW**

---

## USDC Addresses by Chain (for reference)

### Mainnet
| Chain | USDC Address |
|-------|-------------|
| Ethereum | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` |
| Arbitrum | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` |
| Base | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| OP Mainnet | `0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85` |
| Polygon PoS | `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359` |
| Avalanche | `0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E` |

### Testnet (Sepolia)
| Chain | USDC Address |
|-------|-------------|
| Ethereum Sepolia | `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238` |
| Base Sepolia | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Arbitrum Sepolia | `0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d` |
| OP Sepolia | `0x5fd84259d66Cd46123540766Be93DFE6D43130D7` |

---

## Additional Circle GitHub Repos

| Repo | What |
|------|------|
| [circlefin/evm-cctp-contracts](https://github.com/circlefin/evm-cctp-contracts) | Core EVM contracts (V1 + V2) |
| [circlefin/solana-cctp-contracts](https://github.com/circlefin/solana-cctp-contracts) | Solana program (Rust) |
| [circlefin/noble-cctp](https://github.com/circlefin/noble-cctp) | Cosmos/Noble implementation |
| [circlefin/stablecoin-evm](https://github.com/circlefin/stablecoin-evm) | USDC token contract |
| [circlefin/cctp-go](https://github.com/circlefin/cctp-go) | Go library for CCTP |
| [circlefin/circle-cctp-crosschain-transfer](https://github.com/circlefin/circle-cctp-crosschain-transfer) | Sample transfer scripts |
| [circlefin/circle-bridge-kit-transfer](https://github.com/circlefin/circle-bridge-kit-transfer) | Bridge Kit demo app |

---

## Quick Reference: Finality Times

### Fast Transfer (minFinalityThreshold ≤ 1000)
| Source | Confirmations | Time |
|--------|--------------|------|
| Ethereum | 2 | ~20s |
| Arbitrum | 1 | ~8s |
| Base | 1 | ~8s |
| OP Mainnet | 1 | ~8s |
| Solana | 2-3 | ~8s |

### Standard Transfer (minFinalityThreshold ≥ 2000)
| Source | Confirmations | Time |
|--------|--------------|------|
| Ethereum | ~65 | 15-19 min |
| Arbitrum | ~65 ETH blocks | 15-19 min |
| Base | ~65 ETH blocks | 15-19 min |
| Avalanche | 1 | ~8s |
| Polygon PoS | 2-3 | ~8s |
| Linea | 1 | 6-32 hours |

---

## API Rate Limits

- **35 requests/second** per instance
- Exceeding → **5-minute block** (HTTP 429)
- Recommendation: exponential backoff, max 2 req/s sustained for polling
