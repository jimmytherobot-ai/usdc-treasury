# FASB ASU 2023-08 — Accounting for and Disclosure of Crypto Assets

## Overview

**Effective Date:** December 15, 2024 (fiscal years beginning after)
**Standard:** ASU 2023-08 (Subtopic 350-60)
**Scope:** Intangible assets that are crypto assets (fungible, on blockchain, not created/issued by reporting entity)

## Key Changes from Prior GAAP

### Before ASU 2023-08
- Crypto assets classified as **indefinite-lived intangible assets**
- Measured at **cost less impairment** (impairment-only model)
- Impairment losses recognized but **no upward adjustments** allowed
- Result: Balance sheet systematically understated crypto holdings

### After ASU 2023-08
- Crypto assets measured at **fair value** each reporting period
- Changes in fair value recognized in **net income**
- Both gains AND losses flow through the income statement
- More accurate representation of economic reality

## Application to USDC (Stablecoins)

### Classification Question
USDC presents an interesting classification challenge:

1. **As Crypto Asset (ASU 2023-08):** If classified as an intangible crypto asset, measured at fair value through net income. Fair value ≈ $1.00 per token.

2. **As Financial Instrument:** USDC may qualify as a financial instrument under ASC 825 given:
   - Fully reserved in cash and short-term US Treasuries
   - Redeemable 1:1 for USD
   - Functions as a medium of exchange
   
3. **As Cash Equivalent:** Under ASC 230, if readily convertible to known amounts of cash and subject to insignificant risk of value change, could be classified as cash equivalent.

### Recommended Treatment for This System
This treasury system treats USDC as a **digital asset measured at fair value** per ASU 2023-08:
- **Fair value** = USD peg (1:1)
- **Cost basis** = Acquisition cost (typically also 1:1)
- **Unrealized gain/loss** = Minimal (peg deviation only)
- **Balance sheet line:** "Digital assets, at fair value"

## Required Disclosures

### Annual Disclosures
1. **Name, cost basis, fair value, and number of units** for each significant crypto asset holding
2. **Significant holdings** must be disaggregated by type
3. **Cost basis roll-forward:**
   - Beginning balance
   - Additions
   - Dispositions
   - Ending balance
4. **Realized gains/losses** from dispositions during the period

### Interim Disclosures
1. Fair value of significant holdings
2. Any new significant holdings since last annual report

## FASB Categories Used in This System

| Category | Description | Measurement |
|----------|-------------|-------------|
| `digital_asset_stablecoin` | USDC holdings across chains | Fair value (≈ $1.00) |
| `accounts_receivable` | Outstanding invoices in USDC | Amortized cost |
| `accounts_payable` | Payable invoices in USDC | Amortized cost |

## Expense Categories (ASC 220 - Income Statement)

| Code | Category | Income Statement Line |
|------|----------|----------------------|
| `services` | Professional services | Operating expenses |
| `infrastructure` | Cloud/hosting/RPC | Operating expenses |
| `development` | Software development | Operating expenses |
| `marketing` | Marketing & outreach | Operating expenses |
| `payroll` | Compensation | Operating expenses |
| `bridging_fees` | Cross-chain bridge costs | Operating expenses |
| `gas_fees` | Network transaction fees | Operating expenses |

## Cost Basis Tracking

This system uses **specific identification** method:
- Each USDC acquisition is tracked individually
- On disposition (payment, bridge), specific lots are identified
- For stablecoins, this is simplified since cost ≈ fair value ≈ $1.00

## Fair Value Measurement (ASC 820)

For USDC fair value:
- **Level 1 Input:** Observable market prices on exchanges
- **Principal market:** Major centralized exchanges (Coinbase, Kraken)
- **Measurement frequency:** Each reporting period (or real-time for this system)

## References

- [FASB ASU 2023-08 Full Text](https://fasb.org/Page/Document?pdf=ASU+2023-08.pdf)
- [Circle USDC Attestation Reports](https://www.circle.com/en/transparency)
- [ASC 350-60 (Crypto Assets)](https://asc.fasb.org/350-60)
- [ASC 820 (Fair Value Measurement)](https://asc.fasb.org/820)
- [ASC 230 (Statement of Cash Flows)](https://asc.fasb.org/230)
