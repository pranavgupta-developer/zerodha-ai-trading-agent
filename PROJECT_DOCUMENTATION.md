# Zerodha AI Trading Agent — Complete Technical Architecture & System Documentation

> **Document Type:** Master System Manual & Technical Specification  
> **Repository:** `zerodha-ai-trading-agent`  
> **Platform Version:** 1.2.0-PROD  
> **Target Broker:** Zerodha (Kite Connect API v3 & KiteTicker WebSocket)  
> **Primary Exchanges:** National Stock Exchange of India (NSE) / Bombay Stock Exchange (BSE)  
> **Execution Environments:** `LIVE` (Real Broker Capital) & `DRY_RUN` (High-Fidelity Paper Trading)  
> **Core Stack:** Python 3.12+ | FastAPI | SQLite / SQLAlchemy | Scikit-Learn / XGBoost | Google Gemini AI | React 18 + Vite | TailwindCSS  
> **Audit & Compliance:** Cryptographic SHA-256 Hash-Chained Audit Ledger (`audit.jsonl`) | Real Indian Statutory Charge Accounting  

---

## Table of Contents

1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [Core Principles & Architectural Guarantees](#2-core-principles--architectural-guarantees)
3. [System Architecture & End-to-End Data Flow](#3-system-architecture--end-to-end-data-flow)
4. [Complete Directory & File Structure](#4-complete-directory--file-structure)
5. [Deep-Dive: Core Subsystems & Components](#5-deep-dive-core-subsystems--components)
   - 5.1 [Broker Integration Layer (`app/broker/`)](#51-broker-integration-layer-appbroker)
   - 5.2 [Strategy & Quantitative Analysis Engine (`app/trading/`)](#52-strategy--quantitative-analysis-engine-apptrading)
   - 5.3 [Deterministic Risk Engine & Position Sizing (`risk_engine.py` & `position_sizer.py`)](#53-deterministic-risk-engine--position-sizing)
   - 5.4 [Order & Position Lifecycle Management (`order_manager.py` & `position_manager.py`)](#54-order--position-lifecycle-management)
   - 5.5 [Machine Learning & Model Registry (`ml_engine.py`, `model_registry.py`, `ml_monitor.py`)](#55-machine-learning--model-registry)
   - 5.6 [AI Agent Reasoning Layer (`app/agent/`)](#56-ai-agent-reasoning-layer-appagent)
   - 5.7 [Security, Governance & Cryptographic Auditing (`app/security/`)](#57-security-governance--cryptographic-auditing-appsecurity)
   - 5.8 [Self-Healing & Resilience Framework (`app/core/self_healing.py`)](#58-self-healing--resilience-framework)
   - 5.9 [Database & State Persistence (`app/db/`)](#59-database--state-persistence)
6. [Mathematical Formulations & Quantitative Formulas](#6-mathematical-formulations--quantitative-formulas)
7. [Indian Statutory Charges & Net P&L Accounting](#7-indian-statutory-charges--net-pl-accounting)
8. [Real-Time Market Data Engine & Zero-Simulation Guarantee](#8-real-time-market-data-engine--zero-simulation-guarantee)
9. [Complete REST & WebSocket API Specification](#9-complete-rest--websocket-api-specification)
10. [Frontend User Interfaces](#10-frontend-user-interfaces)
11. [Configuration & Environment Variables Reference (`.env`)](#11-configuration--environment-variables-reference-env)
12. [Operational Runbook & Production Deployment](#12-operational-runbook--production-deployment)
13. [Test Suite & Verification](#13-test-suite--verification)
14. [Troubleshooting & Frequently Asked Questions](#14-troubleshooting--frequently-asked-questions)

---

## 1. Executive Summary & Problem Statement

### 1.1 The Problem
Retail algorithmic traders in India face significant challenges when deploying quantitative strategies:
1. **The "Simulation Gap":** Backtested and paper-trading systems often look profitable but fail in live markets because they ignore real-world execution frictions—specifically slippage, order queues, circuit limits, and Indian statutory transaction charges (STT, GST, stamp duty, exchange turnover charges).
2. **LLM Hallucination Risk:** Generative AI models (like Anthropic Claude or Google Gemini) offer exceptional contextual reasoning across market narratives, news, and technical setups, but they cannot be trusted with direct API keys to broker order routing due to potential hallucinations, prompt injections, or stochastic errors.
3. **Black-Swan Blowup Risk:** Algorithmic trading bots without deterministic, non-bypassable risk controls can enter runaway execution loops, exhausting margins or violating exchange circuit bands during flash crashes.
4. **Data Tampering & Unaudited Execution:** Traditional algorithmic bots lack cryptographic audit trails, making forensic analysis of trade disputes, execution anomalies, and regulatory compliance difficult.

### 1.2 The Solution
The **Zerodha AI Trading Agent** is a personal, semi-autonomous algorithmic trading and quantitative execution system built for Indian equity markets (NSE/BSE). It directly integrates with the **Zerodha Kite Connect API v3** and **KiteTicker WebSocket**, ingesting authentic sub-second market ticks, running quantitative indicator pipelines, synthesizing AI market reasoning, enforcing strict deterministic risk checks, and managing real positions with high-precision net P&L accounting.

```
+---------------------------------------------------------------------------------------+
|                               ZERODHA AI TRADING AGENT                                 |
|                                                                                       |
|   [ Authentic Ticks ]       [ Quantitative Engine ]      [ AI Reasoning Layer ]       |
|   Zerodha Kite WebSocket -> EMA / RSI / VWAP / ATR    -> Gemini / Quant ML           |
|                                                                                       |
|                                         │ Candidate Signal                            |
|                                         ▼                                             |
|                        [ Deterministic Risk Firewall ]                                |
|                        12 Hard Non-Bypassable Checks                                  |
|                                         │ Approved Order                              |
|                                         ▼                                             |
|   [ Kite Connect Broker ]  <-  [ Position Manager ]   -> [ Cryptographic SHA-256 ]    |
|   Real Capital Execution        Trailing SL/TP + Costs    Immutable Audit Ledger      |
+---------------------------------------------------------------------------------------+
```

---

## 2. Core Principles & Architectural Guarantees

The entire platform is engineered around **four non-negotiable architectural guarantees**:

### 1. Zero Hallucination at the Broker Layer
Large Language Models (Google Gemini) and Machine Learning classifiers are strictly isolated inside an advisory sandbox. They can only output a structured `CandidateTrade` object containing advisory signals, proposed stops, targets, and rationale. **No LLM or ML model has direct access to the broker adapter or order placement endpoints.** Every single order must pass through a hardcoded, deterministic Python risk firewall before dispatch.

### 2. 100% Authentic Market Data (Zero Simulation)
The platform operates exclusively on real exchange quotes. In accordance with strict production guidelines, **all artificial jitter, random walk ticks, and simulated prices have been completely eliminated**. Live watchlist prices stream directly from the Zerodha KiteTicker WebSocket (`MODE_FULL`). When the market is closed or unauthenticated, historical daily and 1-minute exchange candles from official exchange feeds are referenced.

### 3. Comprehensive Net P&L Accounting
A strategy that appears profitable on gross returns can easily lose capital in Indian markets due to multi-layered transaction friction. The system computes exact, transaction-level net P&L deductions for every trade fill:
- Zerodha Brokerage (₹20 or 0.03% per executed order)
- Securities Transaction Tax (STT)
- Exchange Turnover Fees (NSE/BSE)
- Goods and Services Tax (GST @ 18%)
- SEBI Turnover Charges
- State Stamp Duty

### 4. Cryptographic Auditability & Tamper-Evidence
Every system event—incoming tick, candidate trade proposal, AI reasoning snapshot, risk check outcome (pass/fail), order submission, fill execution, and anomaly alert—is appended to an immutable, cryptographically linked **SHA-256 hash chain** (`audit.jsonl`). Any retroactive alteration of order history breaks the hash chain, enabling immediate mathematical verification.

---

## 3. System Architecture & End-to-End Data Flow

The system operates as an asynchronous, event-driven architecture powered by Python's `asyncio` and FastAPI.

```
                                  ┌───────────────────────────────┐
                                  │    ZERODHA KITE CONNECT       │
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
│   │  (In-Memory LTP / OHLC)  │                   │ 10-Second Continuous Poller   │        │
│   └─────────────┬────────────┘                   └───────────────────────────────┘        │
│                 │                                                                         │
│                 ▼                                                                         │
│   ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│   │ TRADING PIPELINE (app/trading/pipeline.py)                                         │  │
│   │                                                                                    │  │
│   │   [Step 1] Candle Aggregation (app/broker/candle_aggregator.py)                    │  │
│   │            Ticks aggregated into 1-minute and 5-minute OHLCV candles               │  │
│   │                                                                                    │  │
│   │   [Step 2] Technical Strategy (app/trading/strategy.py)                            │  │
│   │            EMA(9,21) Cross + RSI(14) Filter + VWAP Alignment + ATR Multiplier      │  │
│   │                                                                                    │  │
│   │   [Step 3] AI & Quant Reasoning (app/agent/service.py & ml_engine.py)              │  │
│   │            Gemini 2.0 Flash Multimodal Analysis / XGBoost Statistical Gate         │  │
│   │                                                                                    │  │
│   │   [Step 4] Champion-Challenger Registry (app/trading/model_registry.py)            │  │
│   │            Shadow Candidate Evaluation, Rolling Accuracy, Auto-Rollback Gate       │  │
│   │                                                                                    │  │
│   │   [Step 5] Dynamic Position Sizing (app/trading/position_sizer.py)                 │  │
│   │            ATR Volatility Budgeting + Fractional Kelly Criterion                   │  │
│   │                                                                                    │  │
│   │   [Step 6] Deterministic Risk Firewall (app/trading/risk_engine.py)                 │  │
│   │            12 Hard Checks: Margin, Circuit Limits, Max Loss, Sector Caps           │  │
│   │                                                                                    │  │
│   │   [Step 7] Capability-Based Access Control (app/security/capbac.py)                │  │
│   │            Cryptographic capability token authorization                            │  │
│   │                                                                                    │  │
│   │   [Step 8] Anomaly Detector (app/security/anomaly_detector.py)                     │  │
│   │            Isolation Forest frequency and latency outlier protection               │  │
│   │                                                                                    │  │
│   │   [Step 9] Order Execution State Machine (app/trading/order_manager.py)            │  │
│   │            Idempotency guard, broker dispatch, slippage tracking                   │  │
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
│   │  - Paper Trading Performance Journal (app/trading/paper_report.py)                 │  │
│   └─────────────────────────────────────────────┬──────────────────────────────────────┘  │
└─────────────────────────────────────────────────┼─────────────────────────────────────────┘
                                                  │
                                                  │ WebSocket Live Push (1 Hz)
                                                  ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER                                                                        │
│  - React 18 + Vite Trading Terminal (`dashboard/`): Glassmorphic UI, TradingView Charts  │
│  - Zero-Build Vanilla Operational UI (`app/static/index.html`): High-reliability backup   │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Complete Directory & File Structure

The workspace follows a clean, modular, and domain-driven design:

```text
/Users/pranavgupta/Desktop/Capstone/
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
├── requirements.txt                  # Python dependencies
├── pyrightconfig.json                # Language server type checking configuration
│
├── app/                              # Core Backend Application
│   ├── main.py                       # FastAPI application entrypoint, WebSocket manager, cron loops
│   ├── agent/                        # AI Reasoning & LLM Agent
│   │   ├── prompts.py                # System prompts, few-shot quant examples, injection defenses
│   │   ├── schemas.py                # Pydantic schemas (CandidateTrade, AgentDecision)
│   │   └── service.py                # AgentService (Gemini API, 3-min backoff circuit breaker)
│   ├── broker/                       # Zerodha Kite Connect Integration
│   │   ├── candle_aggregator.py      # Real-time tick-to-candle (1m/5m) aggregation engine
│   │   ├── instrument_master.py      # SQLite cache for symbol -> instrument_token resolution
│   │   ├── kite_adapter.py           # Kite Connect API adapter (auth, orders, dual-mode runner)
│   │   ├── market_status.py          # NSE/BSE market session hours and holiday calendar
│   │   └── ticker.py                 # KiteTicker WebSocket streaming client (Mode-Full ticks)
│   ├── core/                         # Core Infrastructure
│   │   ├── config.py                 # Pydantic BaseSettings loading .env
│   │   └── self_healing.py           # CircuitBreaker state machine & StaleDataMonitor
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
└── tests/                            # Comprehensive Pytest Test Suite (169 passing tests)
    ├── test_agent_schemas.py         # Pydantic schema validation tests
    ├── test_ai_agent.py              # AI agent proposal and reasoning tests
    ├── test_anomaly_detector.py      # Isolation forest anomaly detection tests
    ├── test_api_e2e.py               # End-to-end FastAPI endpoint tests
    ├── test_audit_chain.py           # SHA-256 hash chaining & tamper detection tests
    ├── test_broker_adapter.py        # KiteConnect adapter and mock broker tests
    ├── test_candle_aggregator.py     # Tick-to-candle aggregation tests
    ├── test_indicators.py            # Technical indicator mathematical accuracy tests
    ├── test_kill_switch.py           # Emergency stop and killswitch tests
    ├── test_liquidity_checks.py      # Liquidity gate and circuit band tests
    ├── test_market_data.py           # Market data ingestion and caching tests
    ├── test_ml_monitor.py            # ML drift, Brier score, regime classification tests
    ├── test_model_registry.py        # Champion-Challenger promotion and rollback tests
    ├── test_order_manager.py         # Order state transitions and idempotency tests
    ├── test_order_manager_advanced.py# Advanced order lifecycle tests
    ├── test_paper_report.py          # Paper journal and Sharpe calculation tests
    ├── test_pipeline.py              # Full trading pipeline integration tests
    ├── test_portfolio_optimizer.py   # Markowitz portfolio optimization tests
    ├── test_position_manager.py      # Position tracking, trailing stop, statutory fee tests
    ├── test_position_sizer.py        # ATR and Kelly position sizing tests
    ├── test_quant_engine.py          # Beta, Alpha, Drawdown quantitative tests
    ├── test_reconciliation.py        # Ledger reconciliation and break detection tests
    ├── test_risk_engine.py           # Deterministic pre-trade risk rules tests
    ├── test_risk_engine_extra.py     # Circuit band and margin edge case tests
    ├── test_security.py              # CapBAC capability token and sanitization tests
    ├── test_self_healing.py          # Circuit breaker and stale data monitor tests
    ├── test_strategy.py              # EMA/RSI/VWAP strategy signal generation tests
    └── test_unified_risk_center.py   # Centralized risk center tests
```

---

## 5. Deep-Dive: Core Subsystems & Components

### 5.1 Broker Integration Layer (`app/broker/`)

#### [`kite_adapter.py`](file:///Users/pranavgupta/Desktop/Capstone/app/broker/kite_adapter.py)
Acts as the unified gateway between the application and Zerodha:
- **Authentication Flow:** Initiates the OAuth login URL via `get_login_url()` and exchanges the single-use `request_token` for a 24-hour `access_token` via `generate_session()`. Access tokens are encrypted and cached in memory.
- **Dual Execution Modes:**
  - `LIVE`: Directly dispatches orders to Zerodha's order management system via `kite.place_order()`.
  - `DRY_RUN`: Simulates live execution against genuine market quotes, writing paper orders and balances to `dry_run_state.json`.
- **Fault-Tolerant Exponential Backoff:** Decorated with `@broker_retry`, automatically retrying transient network errors (HTTP 502, 503, connection resets) up to 3 times with exponential backoff ($1\text{s}, 2\text{s}, 4\text{s}$).

#### [`ticker.py`](file:///Users/pranavgupta/Desktop/Capstone/app/broker/ticker.py)
Manages the sub-second WebSocket streaming connection:
- Establishes a persistent WebSocket connection to `wss://ws.kite.trade` via `KiteTicker`.
- Configured in `MODE_FULL` (extracting Last Traded Price, Day OHLC, Day Volume, and Level-2 Bid/Ask Depth).
- Handles auto-reconnection and resubscription upon network disconnects.

#### [`candle_aggregator.py`](file:///Users/pranavgupta/Desktop/Capstone/app/broker/candle_aggregator.py)
Aggregates asynchronous tick streams into synchronized 1-minute and 5-minute OHLCV candles, maintaining timestamp alignment for quantitative indicator calculation.

#### [`instrument_master.py`](file:///Users/pranavgupta/Desktop/Capstone/app/broker/instrument_master.py)
Maintains an indexed SQLite cache of Zerodha's complete instrument master (~150,000 instruments), resolving trading symbols (e.g., `RELIANCE`, `TCS`, `INFY`) to integer `instrument_token` values in $<1\text{ms}$.

#### [`market_status.py`](file:///Users/pranavgupta/Desktop/Capstone/app/broker/market_status.py)
Enforces Indian Standard Time (IST, UTC+05:30) equity trading rules:
- Trading Session: **09:15 to 15:30 IST**, Monday through Friday.
- Pre-Open Session: **09:00 to 09:15 IST**.
- Market Status States: `OPEN`, `CLOSED`, `PRE_OPEN`, `STALE` (when data feed latency exceeds 300 seconds).

---

### 5.2 Strategy & Quantitative Analysis Engine (`app/trading/`)

#### [`strategy.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/strategy.py)
Implements the core technical strategy: `EmaRsiVwapStrategy` (Version `v1.1-EMA-RSI-VWAP`).
- **Long Entry (BUY) Rules:**
  1. Fast EMA (9) crosses strictly above Slow EMA (21).
  2. Relative Strength Index (RSI 14) is in the bullish momentum zone: $50.0 \le \text{RSI} < 70.0$.
  3. Current Price trades above Volume Weighted Average Price: $\text{LTP} > \text{VWAP}$.
  4. Volume Confirmation: Current candle volume $\ge 1.2 \times \text{SMA}(\text{Volume}, 20)$.
- **Short Entry (SELL) Rules:**
  1. Fast EMA (9) crosses strictly below Slow EMA (21).
  2. RSI (14) is in the bearish momentum zone: $30.0 < \text{RSI} \le 50.0$.
  3. Current Price trades below VWAP: $\text{LTP} < \text{VWAP}$.
  4. Volume Confirmation: Current candle volume $\ge 1.2 \times \text{SMA}(\text{Volume}, 20)$.
- **Initial Stop-Loss & Take-Profit:**
  - Stop Distance: $1.5 \times \text{ATR}(14)$.
  - Target Distance: $2.0 \times \text{Stop Distance}$ (minimum 1:2 Risk-to-Reward ratio).

#### [`quant_engine.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/quant_engine.py)
Computes rigorous quantitative performance metrics across portfolio assets:
- **Momentum (Rate of Change):** $\text{ROC}_N = \frac{P_t - P_{t-N}}{P_{t-N}}$.
- **Beta ($\beta$):** $\beta = \frac{\text{Cov}(R_{\text{asset}}, R_{\text{Nifty}})}{\text{Var}(R_{\text{Nifty}})}$.
- **Annualized Volatility ($\sigma$):** $\sigma = \text{std}(R_{\text{daily}}) \times \sqrt{252}$.
- **Rolling Max Drawdown:** Tracks peak equity and peak-to-trough drawdowns.

#### [`portfolio_optimizer.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/portfolio_optimizer.py)
Implements constrained **Markowitz Mean-Variance Optimization** via `scipy.optimize.minimize`:
- Maximizes portfolio Sharpe ratio while respecting individual stock weight limits ($\le 25\%$) and sector concentration limits ($\le 35\%$).

---

### 5.3 Deterministic Risk Engine & Position Sizing

#### [`risk_engine.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/risk_engine.py)
The deterministic risk firewall evaluates **12 sequential checks** on every trade proposal. If a single check fails, the order is immediately rejected:

| # | Check Name | Rule Description | Default Limit |
|---|---|---|---|
| 1 | **Market Hours Guard** | Rejects orders outside active market hours. | 09:15 – 15:30 IST |
| 2 | **Circuit Limit Protection** | Rejects BUY within buffer of Upper Circuit; rejects SELL within buffer of Lower Circuit. | 1.5% Buffer |
| 3 | **Liquidity Gate** | Rejects trades on illiquid instruments. | Avg Volume $\ge 1,000$ shares |
| 4 | **Max Order Value** | Restricts capital deployed on any single order. | ₹100,000 |
| 5 | **Max Order Quantity** | Restricts share volume per order. | 1,000 shares |
| 6 | **Single Position Cap** | Single position value cannot exceed a fraction of total equity. | $\le 20\%$ of Total Equity |
| 7 | **Total Portfolio Exposure** | Total gross exposure across all positions. | $\le 150\%$ of Total Margin |
| 8 | **Max Open Positions** | Restricts maximum concurrent active positions. | Max 5 Positions |
| 9 | **Sector Concentration** | Max capital allowed in any single sector (IT, Banking, Auto, etc.). | $\le 35\%$ Sector Allocation |
| 10| **Daily Loss Killswitch** | Cumulative realized + unrealized daily loss limit. | $-₹15,000$ (Halts Trading) |
| 11| **Available Margin Buffer**| Verifies account has required margin plus safety buffer. | Requires $1.05 \times$ Margin |
| 12| **Idempotency Guard** | Rejects identical symbol + direction orders within cooldown. | 60-Second Cooldown |

#### [`position_sizer.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/position_sizer.py)
Calculates exact share quantities using **Volatility-Adjusted Fractional Kelly Budgeting**:
$$\text{Dollar Risk} = \text{Account Equity} \times \min(\text{Max Risk \%}, 0.015) \times \text{Confidence}$$
$$\text{Quantity} = \left\lfloor \frac{\text{Dollar Risk}}{|\text{Entry Price} - \text{Stop Loss}|} \right\rfloor$$

---

### 5.4 Order & Position Lifecycle Management

#### [`order_manager.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/order_manager.py)
Maintains the strict order state machine matching Zerodha's lifecycle:
$$\text{PENDING} \longrightarrow \text{SUBMITTED} \longrightarrow \begin{cases} \text{OPEN} \longrightarrow \text{COMPLETE} \\ \text{REJECTED} \\ \text{CANCELLED} \end{cases}$$
- **Idempotency Enforcement:** Computes a unique hash key $\text{MD5}(\text{symbol} + \text{action} + \text{timestamp\_minute})$ to prevent duplicate order submission during network retries.
- **Slippage Monitoring:** Compares expected execution price against actual fill price, logging deviations into the audit ledger.

#### [`position_manager.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/position_manager.py)
- **Active Position Tracking:** Continuously computes unrealized PnL, realized PnL, holding duration, and peak favorable excursion.
- **Dynamic Trailing Stop-Loss:** Automatically advances the stop-loss upward as price rises (for long positions):
  $$\text{New Stop Loss} = \max(\text{Current Stop Loss}, \text{LTP} \times (1 - \text{Trailing \%}))$$
- **Net P&L Engine:** Computes net returns after subtracting exact Indian statutory costs on every fill.

---

### 5.5 Machine Learning & Model Registry

#### [`ml_engine.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/ml_engine.py)
Constructs stationary statistical features from price history and trains classical classifiers:
- **Features Extracted:**
  - Return horizons: 1-bar, 5-bar, 15-bar percentage returns
  - Volatility: 15-bar rolling standard deviation
  - Moving Average Ratios: $\frac{\text{SMA}_{10}}{\text{SMA}_{30}}$ and $\frac{\text{Close}}{\text{SMA}_{10}}$
- **Classifiers Supported:** XGBoost (`XGBClassifier`), Random Forest (`RandomForestClassifier`), Gradient Boosting, Logistic Regression.
- Generates calibrated probabilities via `predict_proba()` used for signal gating.

#### [`model_registry.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/model_registry.py)
Implements an institutional **Champion–Challenger Shadow Framework**:
- **Champion Model (`champ_gemini_quant_v1`):** Active in production, driving live trading decisions.
- **Challenger Model (`test_lstm_v2` / `challenger_xgb_v1_1`):** Evaluates parallel predictions in shadow mode on live ticks without risking capital.
- **Safety Standby Model (`fallback_rules_v0_9`):** Hardcoded deterministic rule engine.
- **Automated Lifecycle Governance:**
  - *Promotion:* Challenger is automatically promoted to Champion if it achieves $\ge 15$ predictions and exceeds Champion rolling accuracy by $\ge 5\%$.
  - *Rollback:* If Champion rolling accuracy drops below $45\%$, system automatically rolls back to fallback rules.
  - *Emergency Halt:* If Champion accuracy drops below $35\%$, the system trips the emergency stop.

#### [`ml_monitor.py`](file:///Users/pranavgupta/Desktop/Capstone/app/trading/ml_monitor.py)
Continuously evaluates model health:
- **Brier Score Calibration:** Measures probability calibration: $\text{BS} = \frac{1}{N} \sum_{t=1}^N (p_t - o_t)^2$.
- **Prediction Drift Detection:** Computes Population Stability Index (PSI) and Kolmogorov-Smirnov statistics across prediction distributions.
- **Market Regime Classifier:** Classifies current market state into `TRENDING_BULL`, `TRENDING_BEAR`, `SIDEWAYS`, or `HIGH_VOLATILITY`.

---

### 5.6 AI Agent Reasoning Layer (`app/agent/`)

#### [`service.py`](file:///Users/pranavgupta/Desktop/Capstone/app/agent/service.py)
Integrates Google Gemini multimodal models (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-flash-latest`):
- Ingests market state, technical indicators, portfolio positions, and active signals.
- Generates structured JSON output strictly conforming to `CandidateTrade`:
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
- **Rate-Limit Circuit Breaker:** When the Gemini API returns `429 RESOURCE_EXHAUSTED`, the agent enters an automatic **3-minute backoff** (`_quota_exhausted_until`), immediately falling back to fast local technical reasoning without stalling the live trading loop.

---

### 5.7 Security, Governance & Cryptographic Auditing (`app/security/`)

#### [`audit_chain.py`](file:///Users/pranavgupta/Desktop/Capstone/app/security/audit_chain.py)
Constructs an immutable, append-only SHA-256 blockchain-style audit ledger in `audit.jsonl`:
- Every block contains: `index`, `timestamp`, `event_type`, `payload`, `previous_hash`, and `hash`.
- Block Hash Computation:
  $$\text{Hash}_i = \text{SHA256}(\text{Index}_i + \text{Timestamp}_i + \text{EventType}_i + \text{Payload}_i + \text{Hash}_{i-1})$$
- Verification Endpoint `/api/v1/system/audit/verify` traverses the entire file, recomputing every hash to detect any unauthorized data manipulation.

#### [`capbac.py`](file:///Users/pranavgupta/Desktop/Capstone/app/security/capbac.py)
Implements **Capability-Based Access Control (CapBAC)**:
- Emits cryptographically signed capability tokens with explicit scopes (allowed symbols, maximum capital per order, expiration TTL).
- Agents must present a valid, non-expired capability token to propose orders.

#### [`anomaly_detector.py`](file:///Users/pranavgupta/Desktop/Capstone/app/security/anomaly_detector.py)
Uses an unsupervised **Isolation Forest** to monitor execution behavior in real time:
- Features Monitored: Order rate (orders/min), order value ratio, portfolio concentration, AI confidence variance, and data lag.
- Automatically triggers emergency halt if an anomalous execution pattern is detected.

#### [`sanitizer.py`](file:///Users/pranavgupta/Desktop/Capstone/app/security/sanitizer.py)
Sanitizes external news feeds and user text inputs, neutralizing prompt injection vectors (`"ignore previous instructions"`, `"bypass rules"`, `"override safety"`).

---

### 5.8 Self-Healing & Resilience Framework

#### [`app/core/self_healing.py`](file:///Users/pranavgupta/Desktop/Capstone/app/core/self_healing.py)
- **`CircuitBreaker`:** Prevents cascading infrastructure failures. Operates in three states:
  - `CLOSED`: Normal operation; all requests pass through.
  - `OPEN`: Halts requests when failure threshold ($\ge 3$ consecutive errors) is reached, waiting for a 60-second recovery timeout.
  - `HALF-OPEN`: Allows a single probe request to verify service restoration before fully closing.
- **`StaleDataMonitor`:** Continuously checks market tick timestamps. If no ticks are received for $\ge 5$ seconds during active market hours, triggers automatic WebSocket reconnection.

---

### 5.9 Database & State Persistence

#### [`trading_agent.db`](file:///Users/pranavgupta/Desktop/Capstone/trading_agent.db) (SQLite / SQLAlchemy)
- `orders`: Tracks every order's symbol, side, price, quantity, status, order_id, fill_time, and slippage.
- `positions`: Tracks open positions, average entry price, current price, stop loss, take target, realized/unrealized PnL.
- `audit_logs`: Local relational copy of audit events for high-speed indexing and dashboard filtering.
- `instruments`: Cached instrument directory for token-to-symbol resolution.

#### Auxiliary State Files:
- `dry_run_state.json`: High-fidelity paper trading state (cash, holdings, margins).
- `model_registry.json`: Champion, challenger, and fallback model metadata and rolling accuracy.
- `ml_monitor_records.json`: Historical predictions and outcome verification records.
- `paper_trading_journal.json`: Forward testing journal documenting daily PnL, win rates, and drawdowns.

---

## 6. Mathematical Formulations & Quantitative Formulas

### 6.1 Technical Indicators

#### 1. Exponential Moving Average (EMA)
$$\alpha = \frac{2}{N + 1}$$
$$\text{EMA}_t = \alpha \times P_t + (1 - \alpha) \times \text{EMA}_{t-1}$$

#### 2. Relative Strength Index (RSI - Wilder's Smoothing)
$$\text{RS} = \frac{\text{Smoothed Gain}(14)}{\text{Smoothed Loss}(14)}$$
$$\text{RSI} = 100 - \frac{100}{1 + \text{RS}}$$

#### 3. Average True Range (ATR)
$$\text{TR}_t = \max(H_t - L_t, \, |H_t - C_{t-1}|, \, |L_t - C_{t-1}|)$$
$$\text{ATR}_t = \frac{\text{ATR}_{t-1} \times 13 + \text{TR}_t}{14}$$

#### 4. Volume-Weighted Average Price (VWAP)
$$\text{Typical Price}_i = \frac{H_i + L_i + C_i}{3}$$
$$\text{VWAP} = \frac{\sum_{i=1}^n (\text{Typical Price}_i \times \text{Volume}_i)}{\sum_{i=1}^n \text{Volume}_i}$$

### 6.2 Quantitative Risk & Performance Metrics

#### 1. Brier Score (Probability Calibration)
$$\text{BS} = \frac{1}{N} \sum_{t=1}^N (f_t - o_t)^2$$
Where $f_t \in [0, 1]$ is predicted probability, and $o_t \in \{0, 1\}$ is actual outcome.

#### 2. Sharpe Ratio
$$\text{Sharpe} = \frac{R_p - R_f}{\sigma_p} \times \sqrt{252}$$

#### 3. Maximum Drawdown (MDD)
$$\text{MDD} = \max_{t \in [0, T]} \left( \frac{\max_{\tau \in [0, t]} P_\tau - P_t}{\max_{\tau \in [0, t]} P_\tau} \right)$$

---

## 7. Indian Statutory Charges & Net P&L Accounting

Trading profitability in Indian markets requires rigorous transaction cost deductions. The platform implements the exact statutory cost schedule for NSE Intraday Equity:

| Fee Component | Statutory Rate / Formula | Applicable Leg |
|---|---|---|
| **Zerodha Brokerage** | $\min(₹20, \, 0.03\% \times \text{Turnover})$ | Both Buy & Sell Legs |
| **Securities Transaction Tax (STT)** | $0.025\%$ on Sell Turnover | Sell Leg Only |
| **Exchange Turnover Charges** | $0.00325\%$ of Turnover | Both Buy & Sell Legs |
| **Goods & Services Tax (GST)** | $18\%$ on $(\text{Brokerage} + \text{Exchange Charges})$ | Both Buy & Sell Legs |
| **SEBI Turnover Fees** | ₹10 per Crore ($0.0001\%$) | Both Buy & Sell Legs |
| **State Stamp Duty** | $0.003\%$ of Turnover | Buy Leg Only |

### Real-World Example Calculation
- **Trade:** Buy 100 shares of Reliance at ₹1,200, Sell at ₹1,215 (Gross Profit: ₹1,500).
  - Buy Turnover: ₹120,000 | Sell Turnover: ₹121,500 | Total Turnover: ₹241,500
  - Brokerage: ₹20 + ₹20 = ₹40.00
  - STT ($0.025\%$ on Sell): ₹30.38
  - Exchange Turnover ($0.00325\%$): ₹7.85
  - GST ($18\%$ on ₹47.85): ₹8.61
  - SEBI Charges: ₹0.24
  - Stamp Duty ($0.003\%$ on Buy): ₹3.60
  - **Total Statutory Deductions:** **₹90.68**
  - **Net Realized P&L:** $₹1,500.00 - ₹90.68 = \mathbf{₹1,409.32}$

---

## 8. Real-Time Market Data Engine & Zero-Simulation Guarantee

### 8.1 Elimination of Synthetic / Mock Ticks
In earlier iterations, background market feeds included synthetic random walk jitter for offline testing. In version 1.2.0, **all simulated data generators have been completely removed**. The system enforces:
1. When authenticated with Zerodha, all live quotes stream directly from the **KiteTicker WebSocket** in `MODE_FULL`.
2. When Zerodha credentials are in `DRY_RUN` mode, live market quotes are continuously polled from genuine exchange feeds (10-second intervals).
3. **Daily Previous Close Resolution:** The previous close calculation references yesterday's official daily closing price (`daily_prev_closes`), calculating authentic Day Change % instead of 1-minute delta shifts.

### 8.2 Top 50 Liquid Indian Equities Watchlist
The active market cache tracks 50 of India's most liquid stocks with updated post-split baseline prices:
- `RELIANCE` (~₹1,208), `TCS` (~₹2,459), `INFY` (~₹1,385), `HDFCBANK` (~₹1,675), `ICICIBANK` (~₹1,215), `TATASTEEL` (~₹174), `SBIN` (~₹785), `ITC` (~₹415), `BHARTIARTL` (~₹1,685), `LT` (~₹3,450), and 40 additional liquid constituents.

---

## 9. Complete REST & WebSocket API Specification

### 9.1 REST Endpoints

| Endpoint | Method | Description | Request / Response Summary |
|---|---|---|---|
| `/api/v1/auth/login` | `GET` | Initiates Zerodha OAuth flow. | Redirects to Kite Connect login portal. |
| `/api/v1/auth/callback` | `GET` | Receives Kite `request_token`, exchanges for `access_token`. | Redirects to `/dashboard?auth=success`. |
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

## 10. Frontend User Interfaces

The platform includes two distinct frontend options:

### 1. Modern React 18 + Vite Trading Console (`dashboard/`)
- Located in `dashboard/`, accessible at `http://localhost:5173`.
- **Aesthetic:** Dark glassmorphic design system (`bg-slate-900/80`, `backdrop-blur-md`, subtle cyan/emerald borders).
- **Features:**
  - Live watchlist with price, day change %, EMA/RSI indicators, and status badges.
  - Interactive modal for candidate trades with AI reasoning and manual **Approve** / **Reject** buttons.
  - Active positions table with dynamic unrealized PnL, trailing stop levels, and one-click exit buttons.
  - Always-visible, high-contrast **Emergency Stop** killswitch button in the top navigation bar.
  - Real-time connection latency indicator (ping/pong measurement).

### 2. Zero-Build Vanilla Operational UI (`app/static/`)
- Located in `app/static/`, accessible at `http://localhost:8000/dashboard`.
- Single-page vanilla HTML/CSS/JavaScript client connecting to the same WebSocket.
- Designed as a zero-dependency fallback requiring no `npm` build step, ideal for low-overhead VPS hosting.

---

## 11. Configuration & Environment Variables Reference (`.env`)

```ini
# ==============================================================================
# ZERODHA KITE CONNECT API CONFIGURATION
# ==============================================================================
KITE_API_KEY=your_kite_api_key_here
KITE_API_SECRET=your_kite_api_secret_here
KITE_REDIRECT_URL=http://localhost:8000/api/v1/auth/callback

# ==============================================================================
# TRADING SYSTEM MODE & EXECUTION AUTONOMY
# ==============================================================================
# TRADING_MODE: 'DRY_RUN' (Paper Trading on Real Quotes) or 'LIVE' (Real Broker Capital)
TRADING_MODE=DRY_RUN

# AUTONOMOUS_EXECUTION: True = Auto-execute approved trades; False = Require manual UI click
AUTONOMOUS_EXECUTION=True

# ==============================================================================
# ARTIFICIAL INTELLIGENCE (GOOGLE GEMINI) CONFIGURATION
# ==============================================================================
GEMINI_API_KEY=your_gemini_api_key_here

# ==============================================================================
# ACTIVE WATCHLIST (Comma-separated symbols)
# ==============================================================================
TRADING_SYMBOLS=RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS,ITC.NS,SBIN.NS,BHARTIARTL.NS,KOTAKBANK.NS,LT.NS

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================
DATABASE_URL=sqlite:///./trading_agent.db
```

---

## 12. Operational Runbook & Production Deployment

### 12.1 Daily Operational Checklist

#### Pre-Market Phase (08:45 – 09:15 IST)
1. **Start System Backend:**
   ```bash
   cd /Users/pranavgupta/Desktop/Capstone
   source venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **Launch Frontend Console:**
   ```bash
   cd dashboard
   npm run dev
   ```
3. **Daily Zerodha OAuth Authentication:**
   - Open browser to `http://127.0.0.1:8000/api/v1/auth/login`.
   - Log in using Zerodha Kite credentials and TOTP.
   - Upon successful login, the browser redirects to `/dashboard?auth=success`, initializing KiteTicker WebSocket.
4. **Verify Health:**
   - Confirm System Status is `NORMAL` and Emergency Stop is `INACTIVE`.
   - Verify Audit Chain integrity: `curl http://localhost:8000/api/v1/system/audit/verify`.

#### Intraday Trading Phase (09:15 – 15:30 IST)
- Monitor active positions, indicator values, and AI reasoning proposals.
- If `AUTONOMOUS_EXECUTION=False`, review candidate trade modals and click **Approve** or **Reject**.

#### Post-Market Phase (15:30 – 16:00 IST)
1. **Intraday Auto-Square Off:** Ensure all intraday positions are closed.
2. **Reconciliation Check:** Verify that internal position state matches broker holdings:
   ```bash
   curl http://localhost:8000/api/v1/system/paper-report
   ```

### 12.2 Emergency Procedures
- **Immediate Trading Halt:** Click the red **"Emergency Stop"** button in the dashboard or run:
  ```bash
  curl -X POST http://localhost:8000/api/v1/system/emergency-stop
  ```
- **Instant Square-Off All Positions:**
  ```bash
  curl -X POST http://localhost:8000/api/v1/positions/square-off-all
  ```
- **Resume Operations:** After investigating the issue, resume normal execution:
  ```bash
  curl -X POST http://localhost:8000/api/v1/system/resume
  ```

---

## 13. Test Suite & Verification

The project includes **169 comprehensive automated unit and integration tests** verifying all critical paths across 31 test files.

### Running the Test Suite
```bash
source venv/bin/activate
pytest -v
```

### Key Areas Tested
- **Risk Firewall:** Circuit limit boundaries, liquidity thresholds, maximum order value, sector concentration caps.
- **Broker Adapter:** OAuth exchange, order state transitions, idempotency guards, retry mechanisms.
- **Model Registry:** Champion–Challenger shadow evaluation, auto-promotion thresholds, auto-rollback rules.
- **Cryptographic Audit:** SHA-256 hash chaining, block genesis, tampering detection.
- **Indicators & Quant Math:** Exact mathematical verification of EMA, RSI, ATR, VWAP, Sharpe ratio, and drawdowns.
- **Statutory Costs:** Accurate deduction of Zerodha brokerage, STT, GST, and turnover charges.

---

## 14. Troubleshooting & Frequently Asked Questions

### Q1: What happens if the Google Gemini API hits a 429 rate limit?
The system includes an automatic **3-minute rate-limit circuit breaker** in `app/agent/service.py`. When a `429 RESOURCE_EXHAUSTED` error occurs, the agent switches to fast local technical reasoning without blocking the tick loop or crashing the application.

### Q2: Why does Zerodha require logging in every morning?
SEBI regulations mandate that broker access tokens expire every 24 hours. A fresh session must be generated each morning before 09:15 IST via the OAuth flow.

### Q3: What is the difference between `LIVE` and `DRY_RUN` mode?
In `DRY_RUN` mode, orders are matched locally against real market quotes without deploying broker capital. In `LIVE` mode, real orders are routed directly to Zerodha. Both modes enforce identical risk checks and statutory fee calculations.

---

*Authored for the Zerodha AI Trading Agent Platform — Designed for institutional safety, mathematical rigor, and quantitative execution.*
