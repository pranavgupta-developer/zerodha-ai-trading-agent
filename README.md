# Zerodha AI Trading Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18 + Vite](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB.svg)](https://react.dev/)
[![Kite Connect v3](https://img.shields.io/badge/Broker-Zerodha%20Kite%20v3-F1592A.svg)](https://kite.trade/)
[![Tests](https://img.shields.io/badge/Tests-189%20Passing-brightgreen.svg)](tests/)
[![Status](https://img.shields.io/badge/Status-Production--Ready%20MVP-success.svg)]()
[![Audit](https://img.shields.io/badge/Audit%20Ledger-SHA--256%20Chained-8A2BE2.svg)]()

> **An institutional-grade, semi-autonomous algorithmic trading and quantitative execution system built for Indian Equity markets (NSE/BSE). Powered by Zerodha Kite Connect API v3, real-time sub-second WebSocket market feeds, Google Gemini multimodal reasoning, classical ML ensembles, a 12-check deterministic risk firewall, dynamic volatility position sizing, and cryptographic SHA-256 audit chaining.**

---

## Table of Contents

1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [Core Principles & Architectural Guarantees](#2-core-principles--architectural-guarantees)
3. [System Architecture & End-to-End Pipeline](#3-system-architecture--end-to-end-pipeline)
4. [Deep-Dive: Subsystems & Core Modules](#4-deep-dive-subsystems--core-modules)
   - [4.1 Broker Integration Layer (`app/broker/`)](#41-broker-integration-layer-appbroker)
   - [4.2 Quantitative Strategy Engine (`app/trading/`)](#42-quantitative-strategy-engine-apptrading)
   - [4.3 Deterministic Risk Firewall (`risk_engine.py`)](#43-deterministic-risk-firewall-risk_enginepy)
   - [4.4 Dynamic Position Sizing (`position_sizer.py`)](#44-dynamic-position-sizing-position_sizerpy)
   - [4.5 Order & Position Lifecycle Management (`order_manager.py` & `position_manager.py`)](#45-order--position-lifecycle-management-order_managerpy--position_managerpy)
   - [4.6 Machine Learning & Champion–Challenger Registry](#46-machine-learning--championchallenger-registry)
   - [4.7 AI Reasoning Layer (`app/agent/`)](#47-ai-reasoning-layer-appagent)
   - [4.8 Security, Governance & Tamper-Evident Auditing (`app/security/`)](#48-security-governance--tamper-evident-auditing-appsecurity)
   - [4.9 Self-Healing & Resilience Framework (`app/core/self_healing.py`)](#49-self-healing--resilience-framework-appcoreself_healingpy)
   - [4.10 Backtesting Engine (`app/backtest/`)](#410-backtesting-engine-appbacktest)
   - [4.11 Database & State Persistence](#411-database--state-persistence)
5. [Mathematical Formulations & Quantitative Formulas](#5-mathematical-formulations--quantitative-formulas)
6. [Indian Statutory Charges & Net P&L Accounting](#6-indian-statutory-charges--net-pl-accounting)
7. [Real-Time Market Data Engine & Zero-Simulation Guarantee](#7-real-time-market-data-engine--zero-simulation-guarantee)
8. [Dual Frontend Interfaces](#8-dual-frontend-interfaces)
9. [Complete REST & WebSocket API Reference](#9-complete-rest--websocket-api-reference)
10. [Directory & File Structure](#10-directory--file-structure)
11. [Installation & Getting Started](#11-installation--getting-started)
12. [Configuration & Environment Variables (`.env`)](#12-configuration--environment-variables-env)
13. [Operational Runbook & Daily Checklist](#13-operational-runbook--daily-checklist)
14. [Testing & Quality Assurance](#14-testing--quality-assurance)
15. [Troubleshooting & Frequently Asked Questions (FAQ)](#15-troubleshooting--frequently-asked-questions-faq)
16. [Supplementary Documentation Links](#16-supplementary-documentation-links)

---

## 1. Executive Summary & Problem Statement

### 1.1 The Retail Algorithmic Trading Dilemma
Algorithmic trading systems for Indian retail participants consistently fail due to four structural obstacles:
1. **The "Simulation Gap":** Strategies backtested or paper-traded on idealized, zero-cost models fail when deployed live because they omit statutory Indian transaction friction (Securities Transaction Tax, GST, Exchange Turnover, SEBI turnover fees, Stamp Duty, and brokerage).
2. **LLM Hallucination Risk:** Generative AI models (e.g. Anthropic Claude, Google Gemini) offer exceptional contextual reasoning across market narratives, news, and technical setups, but granting an LLM direct API keys to broker order routing risks catastrophic loss from hallucinations, prompt injections, or stochastic drift.
3. **Black-Swan Blowup Risk:** Trading bots lacking deterministic, non-bypassable pre-trade risk controls can enter runaway execution loops, violating exchange circuit limits or triggering cascading margin calls.
4. **Audit Opacity:** Traditional retail bots lack cryptographic audit records, making trade disputes, execution slippage forensics, and compliance verification impossible.

### 1.2 The Solution
The **Zerodha AI Trading Agent** bridges this gap by decoupling **AI signal synthesis** from **execution authority**:
- **Advisory AI Reasoning:** Google Gemini 2.0 and ML models evaluate candidate setups and produce advisory recommendations.
- **Deterministic Python Risk Firewall:** Every candidate trade is evaluated against **12 hard, non-bypassable rules** before any order can reach the broker.
- **Real-Exchange Execution:** Direct integration with Zerodha's Kite Connect API v3 and KiteTicker WebSocket (`MODE_FULL`).
- **Complete Net P&L Accounting:** Every trade deduction is calculated down to the paisa.
- **Immutable SHA-256 Audit Chain:** Every event is cryptographically linked and logged to disk.

```
+----------------------------------------------------------------------------------------------------+
|                                    ZERODHA AI TRADING AGENT                                        |
|                                                                                                    |
|    [ Authentic Ticks ]            [ Quantitative Engine ]              [ AI Reasoning Layer ]       |
|    Zerodha Kite WebSocket  ----->  EMA / RSI / VWAP / ATR     ----->   Gemini 2.0 Flash / XGBoost  |
|                                                                                    │               |
|                                                                                    ▼               |
|                                                                          [ Candidate Signal ]      |
|                                                                                    │               |
|                                                                                    ▼               |
|                                                                     [ Deterministic Risk Firewall ] |
|                                                                     12 Hard Non-Bypassable Checks   |
|                                                                                    │               |
|                                                ┌───────────────────────────────────┴──────────┐    |
|                                                │ Approved Order                               │    |
|                                                ▼                                              ▼    |
|                                    [ Broker Order Dispatch ]                       [ SHA-256 Ledger ]|
|                                    Zerodha Kite Connect v3                         audit.jsonl     |
|                                    (LIVE or DRY_RUN Execution)                     Tamper-Evident  |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Core Principles & Architectural Guarantees

The platform is engineered around **four non-negotiable architectural guarantees**:

### 1. Zero Hallucination at the Broker Layer
Generative AI models and machine learning classifiers are strictly isolated inside an advisory sandbox. They produce structured `CandidateTrade` models specifying proposed symbols, entries, targets, and rationale. **No AI model possesses direct broker execution credentials.** Orders can only reach the broker if they pass through a hardcoded, deterministic Python risk firewall.

### 2. 100% Authentic Market Data (Zero Simulation)
All artificial jitter, random-walk tick generators, and simulated prices have been completely eradicated. Live prices stream directly from Zerodha KiteTicker WebSocket (`MODE_FULL`). When the market is closed or unauthenticated, the system references official exchange daily/minute candles and reports an explicit `ZERODHA_AUTH_REQUIRED` state instead of generating synthetic data.

### 3. Net P&L Accounting
Trading profitability is calculated on a net basis. The engine deducts:
- Zerodha Brokerage ($\min(₹20, 0.03\% \times \text{Turnover})$)
- Securities Transaction Tax (STT: $0.025\%$ on Sell turnover)
- Exchange Turnover Charges ($0.00325\%$)
- GST ($18\%$ on Brokerage + Exchange fees)
- SEBI Turnover Fees (₹10 per Crore / $0.0001\%$)
- State Stamp Duty ($0.003\%$ on Buy turnover)

### 4. Cryptographic Auditability
Every tick event, candidate trade proposal, AI reasoning snapshot, risk check outcome, order fill, and emergency alert is appended to an immutable, append-only **SHA-256 hash-chained audit ledger** (`audit.jsonl`). Any retroactive alteration breaks the hash chain, enabling instant mathematical detection.

---

## 3. System Architecture & End-to-End Pipeline

```
                                  ┌───────────────────────────────┐
                                  │     ZERODHA KITE CONNECT      │
                                  │   REST v3 / KiteTicker WSS    │
                                  └───────────────┬───────────────┘
                                                  │
                                 Real-Time Ticks  │ Order Placement / Fills
                                 (LTP/OHLC/Depth) │ (BUY / SELL / CANCEL)
                                                  ▼
┌─────────────────────────────────────────────────┴─────────────────────────────────────────┐
│ FASTAPI CORE SERVER (app/main.py)                                                         │
│                                                                                           │
│   ┌──────────────────────────┐                   ┌───────────────────────────────┐        │
│   │  ThreadSafePriceCache    │◄──────────────────┤ MarketTicker (Kite / YF)      │        │
│   │  (In-Memory LTP / OHLC)  │                   │ Continuous Sub-Second Poller  │        │
│   └─────────────┬────────────┘                   └───────────────────────────────┘        │
│                 │                                                                         │
│                 ▼                                                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│   │ 10-STEP TRADING PIPELINE (app/trading/pipeline.py)                                 │  │
│   │                                                                                    │  │
│   │   [Step 1] Candle Aggregation (app/broker/candle_aggregator.py)                    │  │
│   │            Aggregates sub-second ticks into synchronized 1m & 5m OHLCV candles      │  │
│   │                                                                                    │  │
│   │   [Step 2] Technical Strategy (app/trading/strategy.py)                            │  │
│   │            EMA(9/21) Cross + RSI(14) Filter + VWAP Alignment + Volume Confirmation │  │
│   │                                                                                    │  │
│   │   [Step 3] AI & Quant Reasoning (app/agent/service.py & ml_engine.py)              │  │
│   │            Gemini 2.0 Flash Multimodal Analysis / XGBoost Statistical Gate         │  │
│   │                                                                                    │  │
│   │   [Step 4] Champion-Challenger Registry (app/trading/model_registry.py)            │  │
│   │            Shadow Candidate Tracking, Rolling Accuracy, Auto-Rollback Gate         │  │
│   │                                                                                    │  │
│   │   [Step 5] Dynamic Position Sizing (app/trading/position_sizer.py)                 │  │
│   │            ATR Volatility Budgeting + Fractional Kelly Criterion                   │  │
│   │                                                                                    │  │
│   │   [Step 6] Deterministic Risk Firewall (app/trading/risk_engine.py)                 │  │
│   │            12 Hard Checks: Margin, Circuit Limits, Max Loss, Sector Concentration  │  │
│   │                                                                                    │  │
│   │   [Step 7] Capability-Based Access Control (app/security/capbac.py)                │  │
│   │            Cryptographic capability token authorization & symbol scope check       │  │
│   │                                                                                    │  │
│   │   [Step 8] Anomaly Detector (app/security/anomaly_detector.py)                     │  │
│   │            Isolation Forest frequency and latency outlier protection               │  │
│   │                                                                                    │  │
│   │   [Step 9] Order Execution State Machine (app/trading/order_manager.py)            │  │
│   │            Idempotency guard, broker dispatch, fill & slippage tracking            │  │
│   │                                                                                    │  │
│   │   [Step 10] Position Management (app/trading/position_manager.py)                  │  │
│   │             Dynamic Trailing Stop-Loss, Take-Profit, Statutory Net P&L             │  │
│   └─────────────────────────────────────────────┬──────────────────────────────────────┘  │
│                                                 │                                         │
│                                                 ▼                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│   │ AUDIT & RECONCILIATION LAYER                                                       │  │
│   │  - SHA-256 Cryptographic Hash Chain (app/security/audit_chain.py)                  │  │
│   │  - Continuous Ledger Reconciliation (app/trading/reconciliation.py)                │  │
│   │  - ML Prediction Drift & Brier Score Monitor (app/trading/ml_monitor.py)           │  │
│   │  - Multi-Day Paper Trading Journal (app/trading/paper_report.py)                   │  │
│   └─────────────────────────────────────────────┬──────────────────────────────────────┘  │
└─────────────────────────────────────────────────┼─────────────────────────────────────────┘
                                                  │
                                                  │ WebSocket Live Push (1 Hz)
                                                  ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER                                                                        │
│  - React 18 + Vite Trading Terminal (`dashboard/`): Glassmorphism, Latency, Live Actions   │
│  - Zero-Build Vanilla Operational UI (`app/static/index.html`): High-Reliability Fallback │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Deep-Dive: Subsystems & Core Modules

### 4.1 Broker Integration Layer (`app/broker/`)

- **`kite_adapter.py` (`BrokerAdapter`):**
  - Official wrapper for the `kiteconnect.KiteConnect` v3 SDK.
  - Generates OAuth login URL (`get_login_url()`) and exchanges `request_token` for a 24-hour `access_token` (`generate_session()`).
  - **Dual Execution Modes:**
    - `LIVE`: Routes real orders to the exchange via `kite.place_order()`.
    - `DRY_RUN`: Simulates live execution against real market ticks, saving portfolio balances and paper orders to `dry_run_state.json`.
  - Decorated with `@broker_retry`: Automatically retries transient network errors (HTTP 502, 503, connection timeouts) with exponential backoff ($1\text{s}, 2\text{s}, 4\text{s}$).
- **`ticker.py` (`MarketTicker`):**
  - Manages persistent WebSocket streaming via `KiteTicker` in `MODE_FULL`.
  - Extracts sub-second Last Traded Price (LTP), Day OHLC, Day Volume, and Level-2 Bid/Ask depth.
  - Automatically reconnects and resubscribes upon connection dropouts.
- **`candle_aggregator.py` (`CandleAggregator`):**
  - Aggregates asynchronous ticks into timestamp-aligned 1-minute and 5-minute OHLCV candles for technical indicator calculation.
- **`instrument_master.py` (`InstrumentMaster`):**
  - Maintains an indexed SQLite cache of Zerodha's complete instrument directory (~150,000 instruments), resolving symbols (e.g. `RELIANCE`, `TCS`, `INFY`) to integer `instrument_token` values in $<1\text{ms}$.
- **`market_status.py` (`MarketStatus`):**
  - Enforces Indian Standard Time (IST, UTC+05:30) trading sessions:
    - Pre-Open: **09:00 to 09:15 IST**
    - Regular Session: **09:15 to 15:30 IST**
    - Market Closed: Outside trading hours, weekends, and NSE official holidays.
  - States: `OPEN`, `CLOSED`, `PRE_OPEN`, `STALE` (when data latency exceeds 300 seconds).

---

### 4.2 Quantitative Strategy Engine (`app/trading/`)

- **`strategy.py` (`EmaRsiVwapStrategy` - v1.1):**
  - **Long Entry (BUY):**
    1. Fast EMA (9) crosses strictly above Slow EMA (21).
    2. Relative Strength Index (RSI 14) in bullish momentum zone: $50.0 \le \text{RSI} < 70.0$.
    3. Price trades strictly above VWAP: $\text{LTP} > \text{VWAP}$.
    4. Volume confirmation: $\text{Volume} \ge 1.2 \times \text{SMA}(\text{Volume}, 20)$.
  - **Short Entry (SELL):**
    1. Fast EMA (9) crosses strictly below Slow EMA (21).
    2. RSI (14) in bearish momentum zone: $30.0 < \text{RSI} \le 50.0$.
    3. Price trades strictly below VWAP: $\text{LTP} < \text{VWAP}$.
    4. Volume confirmation: $\text{Volume} \ge 1.2 \times \text{SMA}(\text{Volume}, 20)$.
  - **Dynamic Stop & Target:**
    - Initial Stop Loss: $1.5 \times \text{ATR}(14)$ from entry.
    - Take Target: $2.0 \times \text{Stop Distance}$ (minimum 1:2 Risk-to-Reward ratio).
- **`quant_engine.py` (`QuantEngine`):**
  - Computes cross-sectional asset metrics:
    - Rate of Change / Momentum ($\text{ROC}_N = \frac{P_t - P_{t-N}}{P_{t-N}}$)
    - Beta ($\beta = \frac{\text{Cov}(R_{\text{asset}}, R_{\text{Nifty}})}{\text{Var}(R_{\text{Nifty}})}$)
    - Annualized Volatility ($\sigma = \text{std}(R_{\text{daily}}) \times \sqrt{252}$)
    - Rolling Maximum Drawdown.
- **`portfolio_optimizer.py` (`PortfolioOptimizer`):**
  - Constrained **Markowitz Mean-Variance Optimization** via `scipy.optimize.minimize`.
  - Maximizes portfolio Sharpe ratio subject to:
    - Individual stock weight cap ($\le 25\%$)
    - Sector concentration cap ($\le 35\%$).

---

### 4.3 Deterministic Risk Firewall (`risk_engine.py`)

Every proposed trade is evaluated against **12 sequential, non-bypassable pre-trade risk checks**. If any check fails, the order is immediately rejected:

| # | Risk Check | Rule & Enforcement Description | Default Production Limit |
|---|---|---|---|
| **1** | **Market Hours Guard** | Rejects orders placed outside active exchange session hours. | 09:15 – 15:30 IST |
| **2** | **Circuit Limit Protection** | Rejects BUY within buffer of Upper Circuit; rejects SELL within buffer of Lower Circuit. | 1.5% Circuit Buffer |
| **3** | **Liquidity Gate** | Rejects orders on thinly traded or illiquid instruments. | 20-Day Avg Volume $\ge 1,000$ shares |
| **4** | **Max Order Value** | Restricts maximum rupee capital deployed on any single order. | ₹100,000 per order |
| **5** | **Max Order Quantity** | Restricts maximum number of shares per order. | 1,000 shares per order |
| **6** | **Single Position Cap** | Single position value cannot exceed a fraction of total account equity. | $\le 20\%$ of Total Equity |
| **7** | **Total Portfolio Exposure** | Total gross exposure across all open positions. | $\le 150\%$ of Total Margin |
| **8** | **Max Open Positions** | Limits maximum concurrent active positions to manage risk. | Max 5 Concurrent Positions |
| **9** | **Sector Concentration** | Restricts capital allocation in any single economic sector. | $\le 35\%$ Sector Allocation |
| **10**| **Daily Loss Killswitch** | Triggers emergency halt if cumulative realized + unrealized daily loss is hit. | $-₹15,000$ Daily Loss Limit |
| **11**| **Available Margin Buffer** | Requires available cash margin plus safety buffer before placement. | Requires $1.05 \times$ Margin |
| **12**| **Idempotency Guard** | Rejects identical symbol + direction orders placed within cooldown period. | 60-Second Cooldown Window |

---

### 4.4 Dynamic Position Sizing (`position_sizer.py`)

The position sizer uses **Volatility-Adjusted Fractional Kelly Budgeting**:
$$\text{Dollar Risk} = \text{Account Equity} \times \min(\text{Max Risk \%}, 0.015) \times \text{Confidence}$$
$$\text{Quantity} = \left\lfloor \frac{\text{Dollar Risk}}{|\text{Entry Price} - \text{Stop Loss}|} \right\rfloor$$
This ensures position size automatically scales down during high-volatility regimes (large ATR) and expands during high-conviction, tight-stop opportunities.

---

### 4.5 Order & Position Lifecycle Management (`order_manager.py` & `position_manager.py`)

- **`order_manager.py` (`OrderManager`):**
  - Manages the strict order state machine matching Zerodha's execution lifecycle:
    $$\text{PENDING} \longrightarrow \text{SUBMITTED} \longrightarrow \begin{cases} \text{OPEN} \longrightarrow \text{COMPLETE} \\ \text{REJECTED} \\ \text{CANCELLED} \end{cases}$$
  - **Idempotency Guard:** Computes an MD5 signature $\text{MD5}(\text{symbol} + \text{action} + \text{timestamp\_minute})$ to prevent accidental duplicate order submissions during network retries.
  - **Slippage Tracking:** Measures variance between proposed entry price and actual broker fill price, logging deviations into the audit trail.
- **`position_manager.py` (`PositionManager`):**
  - Tracks open positions, holding durations, peak favorable excursions, and real-time unrealized PnL.
  - **Dynamic Trailing Stop-Loss:** Continuously ratchets stop-loss upward as price rises (for long positions):
    $$\text{New Stop Loss} = \max(\text{Current Stop Loss}, \text{LTP} \times (1 - \text{Trailing \%}))$$
  - Deducts transaction-level statutory costs on every position close to compute genuine net P&L.

---

### 4.6 Machine Learning & Champion–Challenger Registry

- **`ml_engine.py` (`MLEngine`):**
  - Computes 6 stationary statistical features:
    - 1-bar, 5-bar, and 15-bar percentage returns
    - 15-bar rolling standard deviation (volatility)
    - Moving average ratios: $\frac{\text{SMA}_{10}}{\text{SMA}_{30}}$ and $\frac{\text{Close}}{\text{SMA}_{10}}$
  - Classifiers: `XGBClassifier`, `RandomForestClassifier`, `GradientBoostingClassifier`, `LogisticRegression`.
  - Outputs calibrated probabilities via `predict_proba()` used as a statistical confidence gate.
- **`model_registry.py` (`ModelRegistry`):**
  - Manages production model governance using a **Champion–Challenger Shadow Framework**:
    - **Champion Model (`champ_gemini_quant_v1`):** Active in production, driving live trading capital.
    - **Challenger Model (`test_lstm_v2` / `challenger_xgb_v1_1`):** Evaluates live ticks in shadow mode without risking capital.
    - **Fallback Model (`fallback_rules_v0_9`):** Hardcoded deterministic rule engine.
  - **Auto-Promotion:** If Challenger evaluates $\ge 15$ predictions and exceeds Champion rolling accuracy by $\ge 5\%$, it is automatically promoted to Champion.
  - **Auto-Rollback:** If Champion rolling accuracy drops below $45\%$, the system automatically rolls back to fallback rules.
  - **Emergency Stop:** If Champion accuracy drops below $35\%$, the system trips the emergency stop.
- **`ml_monitor.py` (`MLMonitor`):**
  - **Brier Score Calibration:** Measures probability calibration error: $\text{BS} = \frac{1}{N} \sum_{t=1}^N (p_t - o_t)^2$.
  - **Prediction Drift Detection:** Computes Population Stability Index (PSI) and Kolmogorov-Smirnov statistics across prediction distributions.
  - **Market Regime Classifier:** Classifies active market into `TRENDING_BULL`, `TRENDING_BEAR`, `SIDEWAYS`, or `HIGH_VOLATILITY`.

---

### 4.7 AI Reasoning Layer (`app/agent/`)

- **`service.py` (`AgentService`):**
  - Integrates Google Gemini multimodal models (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-flash-latest`).
  - Synthesizes technical indicators, VWAP alignment, order book depth, and market sentiment into a validated JSON response strictly conforming to `CandidateTrade`:
    ```json
    {
      "symbol": "RELIANCE",
      "action": "BUY",
      "quantity": 25,
      "entry_price": 1208.50,
      "stop_loss": 1195.00,
      "take_target": 1235.00,
      "confidence": 0.78,
      "reasoning": "Bullish EMA crossover above VWAP with rising RSI (58.4) and expanding volume."
    }
    ```
  - **Rate-Limit Circuit Breaker:** When the Gemini API returns a `429 RESOURCE_EXHAUSTED` error, the agent enters an automatic **3-minute backoff** (`_quota_exhausted_until`), immediately falling back to local quantitative technical reasoning without blocking the tick loop or stalling live execution.

---

### 4.8 Security, Governance & Tamper-Evident Auditing (`app/security/`)

- **`audit_chain.py` (`AuditChain`):**
  - Implements an immutable, append-only **SHA-256 blockchain-style audit ledger** in `audit.jsonl`.
  - Block Hash Computation:
    $$\text{Hash}_i = \text{SHA256}(\text{Index}_i + \text{Timestamp}_i + \text{EventType}_i + \text{Payload}_i + \text{Hash}_{i-1})$$
  - Verification endpoint `/api/v1/system/audit/verify` traverses the entire file, recalculating every hash to verify ledger integrity.
- **`capbac.py` (`CapabilityToken`):**
  - **Capability-Based Access Control (CapBAC):** Emits cryptographically signed capability tokens with explicit scopes (allowed symbols, maximum capital per order, expiration TTL). Agents must present a valid, non-expired token to propose trades.
- **`anomaly_detector.py` (`AnomalyDetector`):**
  - Employs an unsupervised **Isolation Forest** to detect execution anomalies: order rate spikes (orders/min), order value ratio anomalies, portfolio concentration spikes, and data latency lag.
  - Automatically trips the emergency stop if an anomalous execution pattern is detected.
- **`sanitizer.py`:**
  - Sanitizes external inputs, news feeds, and user strings, neutralizing prompt injection vectors (`"ignore previous instructions"`, `"bypass rules"`, `"override safety"`).
- **`unified_risk_center.py` (`UnifiedRiskCenter`):**
  - Centralized risk coordination center coordinating the emergency stop killswitch, continuous ledger reconciliation, anomaly detection, and pre-trade risk engine.

---

### 4.9 Self-Healing & Resilience Framework (`app/core/self_healing.py`)

- **`CircuitBreaker`:** Prevents cascading system failures across external API calls:
  - `CLOSED`: Normal operation; all requests pass through.
  - `OPEN`: Halts outbound calls when failure threshold ($\ge 3$ consecutive errors) is reached, entering a 60-second recovery timeout.
  - `HALF-OPEN`: Dispatches a single canary request to test service restoration before fully restoring traffic.
- **`StaleDataMonitor`:** Continuously checks market tick timestamps. If no ticks are received for $\ge 5$ seconds during active market hours, it triggers automatic WebSocket reconnection.

---

### 4.10 Backtesting Engine (`app/backtest/`)

- **`engine.py` (`BacktestEngine`):**
  - Allows multi-asset historical strategy simulation using historical exchange data (`yfinance` or local candles).
  - Simulates the exact `EmaRsiVwapStrategy`, position sizing, and risk firewall rules.
  - Deducts transaction fees (default: 0.1% covering statutory charges and slippage).
  - Outputs performance metrics: equity curve, total return, win rate, profit factor, Sharpe ratio, and maximum drawdown.

---

### 4.11 Database & State Persistence

- **Primary Database (`trading_agent.db` - SQLite / SQLAlchemy):**
  - `orders`: Tracks every order's symbol, side, price, quantity, status, order_id, fill_time, and slippage.
  - `positions`: Tracks open and closed positions, average entry price, current price, stop loss, take target, realized/unrealized PnL.
  - `audit_logs`: Relational audit log entries for rapid indexing and dashboard query filtering.
  - `instruments`: Cached instrument master directory for fast symbol-to-token resolution.
- **Auxiliary State Files:**
  - `dry_run_state.json`: High-fidelity paper trading state (cash, open positions, margin).
  - `model_registry.json`: Champion, challenger, and fallback model metadata and rolling accuracy.
  - `ml_monitor_records.json`: Historical predictions and outcome verification records.
  - `paper_trading_journal.json`: Multi-day forward testing journal documenting daily PnL, win rates, and drawdowns.

---

## 5. Mathematical Formulations & Quantitative Formulas

### 5.1 Technical Indicators
- **Exponential Moving Average (EMA):**
  $$\alpha = \frac{2}{N + 1}, \quad \text{EMA}_t = \alpha \times P_t + (1 - \alpha) \times \text{EMA}_{t-1}$$
- **Relative Strength Index (RSI - Wilder's Smoothing):**
  $$\text{RS} = \frac{\text{Smoothed Gain}(14)}{\text{Smoothed Loss}(14)}, \quad \text{RSI} = 100 - \frac{100}{1 + \text{RS}}$$
- **Average True Range (ATR):**
  $$\text{TR}_t = \max(H_t - L_t, \, |H_t - C_{t-1}|, \, |L_t - C_{t-1}|), \quad \text{ATR}_t = \frac{\text{ATR}_{t-1} \times 13 + \text{TR}_t}{14}$$
- **Volume-Weighted Average Price (VWAP):**
  $$\text{Typical Price}_i = \frac{H_i + L_i + C_i}{3}, \quad \text{VWAP} = \frac{\sum_{i=1}^n (\text{Typical Price}_i \times \text{Volume}_i)}{\sum_{i=1}^n \text{Volume}_i}$$

### 5.2 Quantitative Risk & Performance Metrics
- **Brier Score (Probability Calibration):**
  $$\text{BS} = \frac{1}{N} \sum_{t=1}^N (f_t - o_t)^2$$
- **Sharpe Ratio:**
  $$\text{Sharpe} = \frac{R_p - R_f}{\sigma_p} \times \sqrt{252}$$
- **Maximum Drawdown (MDD):**
  $$\text{MDD} = \max_{t \in [0, T]} \left( \frac{\max_{\tau \in [0, t]} P_\tau - P_t}{\max_{\tau \in [0, t]} P_\tau} \right)$$
- **Asset Beta ($\beta$):**
  $$\beta = \frac{\text{Cov}(R_{\text{asset}}, R_{\text{Nifty}})}{\text{Var}(R_{\text{Nifty}})}$$

---

## 6. Indian Statutory Charges & Net P&L Accounting

The engine implements the exact statutory cost schedule for **NSE Intraday Equity**:

| Statutory Fee Component | Regulatory Rate / Formula | Applicable Leg |
|---|---|---|
| **Zerodha Brokerage** | $\min(₹20, \, 0.03\% \times \text{Turnover})$ | Both Buy & Sell Legs |
| **Securities Transaction Tax (STT)** | $0.025\%$ on Sell Turnover | Sell Leg Only |
| **Exchange Turnover Charges** | $0.00325\%$ of Turnover | Both Buy & Sell Legs |
| **Goods & Services Tax (GST)** | $18\%$ on $(\text{Brokerage} + \text{Exchange Charges})$ | Both Buy & Sell Legs |
| **SEBI Turnover Fees** | ₹10 per Crore ($0.0001\%$) | Both Buy & Sell Legs |
| **State Stamp Duty** | $0.003\%$ of Turnover | Buy Leg Only |

### Worked Example: Intraday Equity Trade
- **Scenario:** Buy 100 shares of Reliance at ₹1,200.00, Sell at ₹1,215.00
  - Buy Turnover: ₹120,000.00 | Sell Turnover: ₹121,500.00 | Total Turnover: ₹241,500.00
  - Gross Realized Profit: $(1,215 - 1,200) \times 100 = \mathbf{₹1,500.00}$
  - **Brokerage:** ₹20.00 (Buy) + ₹20.00 (Sell) = ₹40.00
  - **STT (0.025% on Sell):** ₹30.38
  - **Exchange Turnover Charges (0.00325%):** ₹7.85
  - **GST (18% on ₹47.85):** ₹8.61
  - **SEBI Charges:** ₹0.24
  - **Stamp Duty (0.003% on Buy):** ₹3.60
  - **Total Transaction Friction:** **₹90.68**
  - **Net Realized P&L:** $₹1,500.00 - ₹90.68 = \mathbf{₹1,409.32}$

---

## 7. Real-Time Market Data Engine & Zero-Simulation Guarantee

### 7.1 Elimination of Synthetic / Mock Market Data
In accordance with production standards, **all simulated data generators, hardcoded price tables, and artificial jitter algorithms have been completely eliminated**.
1. **Direct Zerodha Feeds:** All quotes and market depth stream directly from Zerodha Kite Connect API v3 (`broker.get_quote()`) and KiteTicker WebSocket (`MODE_FULL`).
2. **Real Candle Construction:** Indicators are built exclusively from real candles aggregated from live ticks via `CandleAggregator` and Zerodha historical minute feeds.
3. **Official Exchange Previous Close:** Day Change % is calculated exclusively against Zerodha's official OHLC previous close (`quote_data["ohlc"]["close"]`), eliminating delta drift.
4. **Explicit Authentication Gating (`ZERODHA_AUTH_REQUIRED`):** When the daily Zerodha session expires or is unauthenticated, the system halts trade generation and reports `ZERODHA_AUTH_REQUIRED` across REST and WebSocket APIs rather than fabricating mock data.
5. **One-Click Session Activation:** Operators can re-authenticate anytime via `/api/v1/auth/login` or submit their daily token via `POST /api/v1/auth/token` directly from the dashboard modal.

---

## 8. Dual Frontend Interfaces

The platform includes two distinct frontend options:

### 1. Modern React 18 + Vite Trading Terminal (`dashboard/`)
- Accessible at `http://localhost:5173`.
- **Aesthetic:** Dark glassmorphic design system (`bg-slate-900/80`, `backdrop-blur-md`, emerald/cyan accents, JetBrains Mono typography).
- **Features:**
  - Real-time streaming watchlist with LTP, Day Change %, volume, EMA, and RSI badges.
  - Interactive candidate trade modal with AI reasoning, confidence gauges, and manual **Approve** / **Reject** controls.
  - Live active positions table with dynamic unrealized PnL, trailing stop levels, and one-click exit buttons.
  - Always-visible, high-contrast **Emergency Stop** killswitch in the navigation bar.
  - Sub-second connection latency indicator (ping/pong measurement).

### 2. Zero-Build Vanilla Operational UI (`app/static/`)
- Accessible at `http://localhost:8000/dashboard`.
- Single-page vanilla HTML/CSS/JavaScript client connecting to the same WebSocket.
- Designed as a zero-dependency fallback requiring no `npm` build step, ideal for low-overhead VPS hosting.

---

## 9. Complete REST & WebSocket API Reference

### 9.1 REST Endpoints

| Endpoint | Method | Description | Request / Response Summary |
|---|---|---|---|
| `/api/v1/auth/login` | `GET` | Initiates Zerodha OAuth flow. | Redirects to Kite Connect login portal. |
| `/api/v1/auth/callback` | `GET` | Receives Kite `request_token`, exchanges for `access_token`. | Redirects to `/dashboard?auth=success`. |
| `/api/v1/auth/token` | `POST` | Activates session via manual `access_token` or `request_token`. | Body: `{"token": "..."}`. Returns auth status. |
| `/api/v1/portfolio` | `GET` | Returns cash balance, margin, open positions, holdings, and live watchlist. | Response: `PortfolioResponse` schema. |
| `/api/v1/trades/action` | `POST` | Operator manual approval/rejection of a pending candidate trade. | Body: `{"trade_id": "...", "action": "APPROVE"}`. |
| `/api/v1/positions/square-off-all` | `POST` | Emergency manual square-off of all open positions. | Returns count of exited positions. |
| `/api/v1/system/status` | `GET` | Returns system health, trading mode (`LIVE`/`DRY_RUN`), and killswitch state. | Response: `SystemStatus` schema. |
| `/api/v1/system/emergency-stop` | `POST` | Operator manually activates the global emergency killswitch. | Halts all order placement immediately. |
| `/api/v1/system/resume` | `POST` | Operator resets the emergency killswitch and resumes trading. | Resets halt flag. |
| `/api/v1/system/models/status` | `GET` | Returns Champion and Challenger model registry metrics and accuracy. | Returns model registry JSON. |
| `/api/v1/system/risk/sectors` | `GET` | Current portfolio sector allocation vs maximum limits. | Returns sector percentage breakdown. |
| `/api/v1/system/risk/var` | `GET` | Portfolio Value at Risk (VaR 95%) and Conditional VaR (CVaR). | Returns risk metrics. |
| `/api/v1/system/paper-report` | `GET` | Multi-day forward paper trading journal and validation verdict. | Returns Sharpe, Sortino, max drawdown. |
| `/api/v1/system/audit/verify` | `GET` | Verifies mathematical integrity of the SHA-256 audit chain. | Returns `{"status": "VALID", "blocks": N}`. |
| `/api/v1/audit-logs` | `GET` | Retrieves recent audit log entries. | Supports pagination (`limit`, `offset`). |

### 9.2 Real-Time WebSocket Protocol (`/ws/candidate-trades`)
The WebSocket broadcasts live system state at 1 Hz:
```json
{
  "type": "tick_update",
  "data": {
    "system_status": "NORMAL",
    "market_status": "OPEN",
    "emergency_stop": false,
    "trading_mode": "DRY_RUN",
    "watchlist": [
      {
        "symbol": "RELIANCE",
        "ltp": 1208.50,
        "day_change_pct": 0.85,
        "volume": 4512000,
        "vwap": 1202.30,
        "rsi": 58.4,
        "ema_fast": 1206.10,
        "ema_slow": 1201.50
      }
    ],
    "open_positions": [],
    "candidate_trades": [],
    "recent_logs": []
  }
}
```

---

## 10. Directory & File Structure

```text
zerodha-ai-trading-agent/
├── .env                              # Active environment configuration (API keys, trading modes)
├── .env.example                      # Configuration template
├── Dockerfile                        # Production container definition
├── docker-compose.yml                # Multi-service container orchestration
├── model_registry.json               # Champion & Challenger ML model registry
├── ml_monitor_records.json           # Historical predictions, outcomes, and Brier metrics
├── paper_trading_journal.json        # Forward testing daily performance snapshots
├── audit.jsonl                       # Cryptographic SHA-256 hash-chained audit ledger
├── trading_agent.db                  # SQLite database (orders, positions, audit logs)
├── dry_run_state.json                # High-fidelity paper trading portfolio state
├── requirements.txt                  # Production Python dependencies
├── requirements-dev.txt              # Developer testing and linting tools
├── pyrightconfig.json                # Language server type checking configuration
├── ruff.toml                         # Fast Python linter configuration
│
├── app/                              # Core Backend Application
│   ├── main.py                       # FastAPI application entrypoint, WebSocket broker, cron loops
│   ├── agent/                        # AI Reasoning & LLM Agent
│   │   ├── prompts.py                # System prompts, few-shot quant examples, injection defenses
│   │   ├── schemas.py                # Pydantic schemas (CandidateTrade, AgentDecision)
│   │   └── service.py                # AgentService (Gemini API, 3-min backoff circuit breaker)
│   ├── api/                          # Modular API Routers
│   │   ├── auth.py                   # Zerodha OAuth login, callback, token endpoints
│   │   ├── ml.py                     # ML model status, predictions, training triggers
│   │   ├── portfolio.py              # Portfolio balance, positions, holdings endpoints
│   │   ├── risk.py                   # Sector concentration, VaR, risk limits
│   │   ├── system.py                 # Health, emergency stop, audit verification
│   │   └── trades.py                 # Candidate approvals, order placement, trade actions
│   ├── backtest/                     # Backtesting Engine
│   │   └── engine.py                 # Multi-asset historical simulation engine
│   ├── broker/                       # Zerodha Kite Connect Integration
│   │   ├── candle_aggregator.py      # Real-time tick-to-candle (1m/5m) aggregation engine
│   │   ├── instrument_master.py      # SQLite cache for symbol -> instrument_token resolution
│   │   ├── kite_adapter.py           # Kite Connect API adapter (auth, orders, dual-mode runner)
│   │   ├── market_status.py          # NSE/BSE market session hours and holiday calendar
│   │   └── ticker.py                 # KiteTicker WebSocket streaming client (Mode-Full ticks)
│   ├── core/                         # Core Infrastructure
│   │   ├── config.py                 # Pydantic BaseSettings loading .env
│   │   ├── self_healing.py           # CircuitBreaker state machine & StaleDataMonitor
│   │   └── state.py                  # Thread-safe global state and price cache
│   ├── db/                           # Database & ORM
│   │   ├── database.py               # SQLAlchemy database engine and session factory
│   │   └── models.py                 # SQLAlchemy models (Order, Position, AuditLog, Instrument)
│   ├── security/                     # Security, Auditing & Access Control
│   │   ├── anomaly_detector.py       # Scikit-Learn Isolation Forest runtime anomaly detector
│   │   ├── audit_chain.py            # SHA-256 cryptographic hash-chained audit logger
│   │   ├── capbac.py                 # Capability-Based Access Control (CapBAC) tokens
│   │   ├── sanitizer.py              # Input text & numeric sanitizer (Prompt injection filter)
│   │   └── unified_risk_center.py    # Centralized killswitch and risk management coordinator
│   ├── trading/                      # Quantitative Strategy & Execution
│   │   ├── ml_engine.py              # Classical ML (XGBoost, Random Forest, Logistic Regression)
│   │   ├── ml_monitor.py             # Prediction drift, Brier score, market regime classifier
│   │   ├── model_registry.py         # Champion-Challenger evaluation, auto-promotion/rollback
│   │   ├── order_manager.py          # Order state machine, idempotency, slippage tracking
│   │   ├── paper_report.py           # Multi-day paper trading journal & validation verdict
│   │   ├── pipeline.py               # Master TradingPipeline orchestrator
│   │   ├── portfolio_optimizer.py    # Markowitz Mean-Variance optimizer & sector allocator
│   │   ├── position_manager.py       # Position tracker, dynamic trailing SL/TP, statutory fees
│   │   ├── position_sizer.py         # ATR volatility budgeting & fractional Kelly criterion
│   │   ├── quant_engine.py           # Alpha, Beta, Momentum, Sharpe, Drawdown metrics
│   │   ├── reconciliation.py         # Broker vs internal position reconciliation engine
│   │   ├── risk_engine.py            # Deterministic 12-check pre-trade risk firewall
│   │   ├── signals.py                # Signal, SignalDirection, Prediction data structures
│   │   └── strategy.py               # Concrete strategy: EmaRsiVwapStrategy (v1.1)
│   ├── utils/                        # Mathematical & Market Utilities
│   │   ├── indicators.py             # Vectorized technical indicators (EMA, RSI, ATR, VWAP)
│   │   └── market_utils.py           # IST market helpers, lot size, tick size rounders
│   └── static/                       # Zero-Build Vanilla Operational UI
│       ├── index.html                # High-reliability operational console
│       ├── app.js                    # Vanilla JS WebSocket client and DOM updater
│       └── styles.css                # Glassmorphic dark theme stylesheet
│
├── dashboard/                        # Modern React 18 + Vite Trading Console
│   ├── src/
│   │   ├── App.tsx                   # Main trading terminal application component
│   │   ├── index.css                 # Glassmorphic CSS design system and tokens
│   │   └── main.tsx                  # React DOM entrypoint
│   ├── package.json                  # Frontend dependencies
│   ├── tsconfig.json                 # TypeScript compiler configuration
│   └── vite.config.ts                # Vite build and proxy configuration
│
└── tests/                            # Comprehensive Test Suite (189 passing tests across 34 files)
```

---

## 11. Installation & Getting Started

### Prerequisites
- **Python 3.12+**
- **Node.js 18+ & npm** (for the React 18 + Vite dashboard)
- **Zerodha Kite Connect Developer Account** ([Kite Connect Developer Portal](https://developers.kite.trade/))
- **Google Gemini API Key** ([Google AI Studio](https://aistudio.google.com/))

### Step 1: Clone Repository & Create Virtual Environment
```bash
git clone https://github.com/pranavgupta-developer/zerodha-ai-trading-agent.git
cd zerodha-ai-trading-agent

python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 3: Configure Environment Variables
Copy the template configuration and fill in your API credentials:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
KITE_API_KEY=your_actual_kite_api_key
KITE_API_SECRET=your_actual_kite_api_secret
GEMINI_API_KEY=your_actual_gemini_api_key
TRADING_MODE=DRY_RUN              # Keep DRY_RUN for safe testing; set LIVE for real trading
AUTONOMOUS_EXECUTION=False        # False requires manual approval on dashboard; True executes automatically
TRADING_SYMBOLS=RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS
DATABASE_URL=sqlite:///./trading_agent.db
```

### Step 4: Start the FastAPI Backend
```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API Documentation (Swagger UI): `http://localhost:8000/docs`
- Zero-Build Vanilla Operational UI: `http://localhost:8000/dashboard`

### Step 5: Start the React 18 + Vite Trading Terminal
In a separate terminal window:
```bash
cd dashboard
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

### Step 6: Docker / Docker Compose (Alternative Deployment)
To run the entire backend in a Docker container:
```bash
docker-compose up --build
```

### Step 7: Morning OAuth Authentication
1. Open `http://127.0.0.1:8000/api/v1/auth/login` in your browser.
2. Log in using your Zerodha username, password, and TOTP.
3. Zerodha redirects back to `/api/v1/auth/callback` which generates the 24-hour session token and redirects to `/dashboard?auth=success`.
4. The system initializes the `KiteTicker` WebSocket streaming Mode-Full real market ticks.

---

## 12. Configuration & Environment Variables (`.env`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `KITE_API_KEY` | String | *Required* | Zerodha Kite Connect developer API key. |
| `KITE_API_SECRET` | String | *Required* | Zerodha Kite Connect API secret. |
| `KITE_REDIRECT_URL` | String | `http://localhost:8000/api/v1/auth/callback` | OAuth redirect callback URL registered in Kite portal. |
| `GEMINI_API_KEY` | String | *Required* | Google Gemini API key for AI multimodal reasoning. |
| `TRADING_MODE` | String | `DRY_RUN` | `DRY_RUN` (paper trading on real market ticks) or `LIVE` (real broker capital). |
| `AUTONOMOUS_EXECUTION` | Boolean | `False` | `True` = auto-execute approved orders; `False` = require human approval in UI. |
| `TRADING_SYMBOLS` | String | `RELIANCE.NS,TCS.NS,...` | Comma-separated list of NSE equity symbols to monitor. |
| `DATABASE_URL` | String | `sqlite:///./trading_agent.db` | SQLAlchemy database connection string (SQLite for dev; PostgreSQL for prod). |
| `CHECK_MARKET_HOURS` | Boolean | `True` | Enforce Indian exchange trading session hours (09:15 - 15:30 IST). |
| `PROJECT_NAME` | String | `Zerodha AI Trading Agent` | Application display title. |

---

## 13. Operational Runbook & Daily Checklist

### Pre-Market Phase (08:45 – 09:15 IST)
1. **Start Backend Server:** Ensure Uvicorn is running on port 8000.
2. **Start Frontend Console:** Run `npm run dev` inside `dashboard/`.
3. **Daily Zerodha OAuth Login:** Navigate to `http://127.0.0.1:8000/api/v1/auth/login` and authenticate with Zerodha Kite credentials and TOTP.
4. **Health Check:** Confirm system status shows `NORMAL`, killswitch is `INACTIVE`, and market status transitions to `PRE_OPEN` / `OPEN`.
5. **Verify Audit Chain:** Verify audit integrity via `curl http://localhost:8000/api/v1/system/audit/verify`.

### Intraday Trading Phase (09:15 – 15:30 IST)
- Monitor active positions, indicator values, and AI reasoning proposals.
- If `AUTONOMOUS_EXECUTION=False`, review candidate trade modals and click **Approve** or **Reject**.
- Keep terminal or dashboard log window visible to monitor real-time audit entries.

### Post-Market Phase (15:30 – 16:00 IST)
1. **Auto-Square Off:** Ensure all intraday positions are closed.
2. **Reconciliation Check:** Check internal ledger against broker holdings:
   ```bash
   curl http://localhost:8000/api/v1/system/paper-report
   ```
3. **Review Daily Performance:** Inspect realized PnL, statutory deductions, and win rates in `paper_trading_journal.json`.

### Emergency Procedures
- **Immediate Trading Halt:** Click the red **"Emergency Stop"** button in the dashboard or run:
  ```bash
  curl -X POST http://localhost:8000/api/v1/system/emergency-stop
  ```
- **Instant Square-Off All Positions:**
  ```bash
  curl -X POST http://localhost:8000/api/v1/positions/square-off-all
  ```
- **Resume Operations:** After investigating the issue, reset the emergency stop:
  ```bash
  curl -X POST http://localhost:8000/api/v1/system/resume
  ```

---

## 14. Testing & Quality Assurance

The codebase includes an exhaustive test suite of **189 automated unit and integration tests across 34 test modules**.

### Running the Test Suite
```bash
source venv/bin/activate
pytest -v
```

### Key Areas Tested
- **Deterministic Risk Firewall:** Circuit limit boundaries, liquidity thresholds, maximum order value, sector concentration caps, available margin buffer.
- **Broker Adapter:** OAuth exchange, order state transitions, idempotency guards, retry mechanisms with exponential backoff.
- **Model Registry:** Champion–Challenger shadow evaluation, auto-promotion thresholds, auto-rollback rules.
- **Signal Quality Scoring:** 0–100 composite multi-factor evaluation (trend, momentum, volume, ML conviction, regime).
- **Trade Ranking & Selection:** Cross-sectional ranking by risk-adjusted return and available margin budgeting.
- **Multi-Timeframe & Regime Strategy:** 15m/1m trend alignment, regime gating, and dynamic ATR stop-loss and take-profit adaptation.
- **Cryptographic Audit:** SHA-256 hash chaining, block genesis, tampering detection.
- **Indicators & Quant Math:** Mathematical accuracy of EMA, RSI, ATR, VWAP, Sharpe ratio, and drawdowns.
- **Statutory Charges:** Exact deduction of Zerodha brokerage, STT, GST, and exchange fees.

---

## 15. Troubleshooting & Frequently Asked Questions (FAQ)

### Q1: What happens if the Google Gemini API hits a 429 quota exhaustion?
The system includes an automatic **3-minute rate-limit circuit breaker** in `app/agent/service.py`. When a `429 RESOURCE_EXHAUSTED` error occurs, the agent switches to fast local technical reasoning without blocking the tick loop or crashing the application.

### Q2: Why does Zerodha require logging in every morning?
SEBI regulations mandate that broker access tokens expire every 24 hours. A fresh session must be generated each morning before 09:15 IST via the OAuth flow.

### Q3: What is the difference between `LIVE` and `DRY_RUN` mode?
In `DRY_RUN` mode, orders are matched locally against real market quotes without deploying broker capital. In `LIVE` mode, real orders are routed directly to Zerodha. Both modes enforce identical risk checks and statutory fee calculations.

### Q4: Why am I getting SQLite database locked errors?
SQLite is intended for single-process development. If running multiple concurrent processes or background threads, configure PostgreSQL by updating `DATABASE_URL` in `.env`:
```ini
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/trading_agent
```

---

## 16. Supplementary Documentation Links

- **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md):** Complete 760+ line master technical specification, full architecture, mathematical proofs, and exhaustive API reference.
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md):** High-level summary of architecture, design philosophy, and module responsibilities.
- **[RUNBOOK.md](RUNBOOK.md):** Live market operational procedures, manual intervention checklists, and emergency drills.

---

*Authored for the Zerodha AI Trading Agent Platform — Designed for institutional safety, mathematical rigor, and quantitative execution.*
