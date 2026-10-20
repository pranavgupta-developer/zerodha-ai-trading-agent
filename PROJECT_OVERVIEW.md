# Zerodha AI Trading Agent — Comprehensive System Architecture & Documentation

> **Status:** Production-Ready MVP  
> **Target Broker:** Zerodha (Kite Connect API v3)  
> **Markets Supported:** NSE / BSE (Equities & Derivatives)  
> **Environment Modes:** `LIVE` (Real Capital Execution) & `DRY_RUN` (High-Fidelity Paper Trading)  
> **Core Runtime:** Python 3.12+ / FastAPI / WebSockets / SQLite / React 18 + Vite  

---

## 1. Executive Summary

The **Zerodha AI Trading Agent** is a personal, semi-autonomous algorithmic trading and quantitative execution system. It connects directly to a user's Zerodha Kite Connect account, ingests live tick-by-tick market data, computes real-time quantitative and technical indicators, evaluates predictive models, filters signals through a **deterministic risk engine**, and autonomously or semi-autonomously executes and manages trades with real capital.

### Core Design Philosophy
1. **Zero Hallucination at the Broker Layer:** Language models (LLMs) and ML classifiers are strictly confined to generating *candidate suggestions*. No trade reaches the broker without passing through a deterministic, hard-coded Python risk firewall.
2. **Pure Real Market Data:** The platform operates strictly on genuine market feeds (Zerodha Kite WebSocket Mode-Full ticks and real 1-minute exchange candles). No artificial jitter or mock random numbers are introduced.
3. **Net P&L Accounting:** All performance metrics factor in statutory Indian transaction costs: Zerodha brokerage (₹20 or 0.03%), STT (Securities Transaction Tax), Exchange Turnover Charges, GST (18%), SEBI turnover charges, and Stamp Duty.
4. **Institutional Safety Gates:** Features automated Stop-Loss, Take-Profit, Trailing Stops, Anomaly Detection, Circuit Limit guards, Tamper-Evident SHA-256 Audit Chains, and a Champion–Challenger Model Registry.

---

## 2. High-Level Architecture Diagram

```
                              ┌─────────────────────────────────────────────────────────┐
                              │                 ZERODHA KITE CONNECT                    │
                              │     OAuth 2.0 / WebSocket Ticker / Order Routing        │
                              └─────────────┬─────────────────────────────▲─────────────┘
                                            │ Real-Time Ticks             │ Order Execution
                                            │ (Mode-Full LTP/OHLC)        │ (BUY/SELL/CANCEL)
                                            ▼                             │
┌─────────────────────────────────────────────────────────────────────────┴─────────────┐
│ FASTAPI CORE BACKEND (app/main.py)                                                    │
│                                                                                       │
│  ┌───────────────────────┐         ┌────────────────────────┐                         │
│  │ ThreadSafePriceCache  │◄────────┤ MarketTicker / YF Feed │                         │
│  └──────────┬────────────┘         └────────────────────────┘                         │
│             │                                                                         │
│             ▼                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │ TRADING PIPELINE (app/trading/pipeline.py)                                      │  │
│  │                                                                                 │  │
│  │  1. Strategy Engine (app/trading/strategy.py)                                   │  │
│  │     EMA (9/21) Crossover + RSI (14) + VWAP Anchor + ATR Multiplier              │  │
│  │                                                                                 │  │
│  │  2. AI & Quant Evaluation Layer (app/agent/service.py & ml_engine.py)           │  │
│  │     Gemini Multimodal Reasoning / Local XGBoost Classifier (Circuit Breaker)    │  │
│  │                                                                                 │  │
│  │  3. Dynamic Position Sizer (app/trading/position_sizer.py)                      │  │
│  │     ATR Volatility Budgeting + Fractional Kelly Criterion                       │  │
│  │                                                                                 │  │
│  │  4. Champion–Challenger Shadow Evaluation (app/trading/model_registry.py)       │  │
│  │     Shadow Candidate Tracking + Rolling Accuracy + Auto-Promotion / Rollback    │  │
│  │                                                                                 │  │
│  │  5. Deterministic Risk Engine (app/trading/risk_engine.py)                      │  │
│  │     Margin Check | Max Order | Circuit Limits | Liquidity | Max Drawdown        │  │
│  │                                                                                 │  │
│  │  6. Anomaly Detector (app/security/anomaly_detector.py)                         │  │
│  │     Isolation Forest + Frequency Spike & Lag Detection (Auto-Halt)              │  │
│  │                                                                                 │  │
│  │  7. Order Manager & Position Tracker (order_manager.py & position_manager.py)  │  │
│  │     State Machine + Idempotency Guard + Trailing SL/TP + Brokerage Deductions   │  │
│  └───────────────────────────────────────────────────┬─────────────────────────────┘  │
│                                                      │                                │
│                                                      ▼                                │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │ AUDIT & INTEGRITY LAYER                                                         │  │
│  │  - Tamper-Evident SHA-256 Hash Chain (app/security/audit_chain.py)              │  │
│  │  - Continuous Ledger Reconciliation (app/trading/reconciliation.py)             │  │
│  │  - Statistical ML Drift & Brier Score Monitor (app/trading/ml_monitor.py)       │  │
│  │  - Multi-Day Paper Trading Validation Journal (app/trading/paper_report.py)     │  │
│  └───────────────────────────────────────────────────┬─────────────────────────────┘  │
└──────────────────────────────────────────────────────┼────────────────────────────────┘
                                                       │ Live State (1 Hz WebSocket)
                                                       ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER                                                                    │
│  - React 18 + Vite Dashboard (dashboard/): Glassmorphic UI, JetBrains Mono, Latency   │
│  - Zero-Build Vanilla Web UI (app/static/index.html & app.js)                         │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Directory & File Structure

```text
/Users/pranavgupta/Desktop/Capstone/
├── .env                              # Active environment configuration (API keys, modes)
├── .env.example                      # Template configuration
├── requirements.txt                  # Python dependencies
├── model_registry.json               # Champion/Challenger model registry persistence
├── ml_monitor_records.json           # Historical predictions and outcome metrics
├── paper_trading_journal.json        # Forward testing performance snapshots
├── audit.jsonl                       # Cryptographic SHA-256 hash-chained audit trail
├── trading_agent.db                  # SQLite database for orders, positions, logs
├── app/
│   ├── main.py                       # FastAPI entrypoint, WebSocket broker, background loops
│   ├── agent/
│   │   ├── schemas.py                # CandidateTrade, AgentDecision Pydantic models
│   │   └── service.py                # AgentService (Gemini AI + Quota backoff + technical fallback)
│   ├── broker/
│   │   ├── kite_adapter.py           # Kite Connect adapter (auth, quotes, order placement)
│   │   ├── ticker.py                 # KiteTicker WebSocket client (real-time Mode-Full ticks)
│   │   ├── candle_aggregator.py      # Tick-to-candle (1m/5m) aggregation engine
│   │   ├── instrument_master.py      # SQLite cache for symbol -> instrument_token resolution
│   │   └── market_status.py          # NSE market hours & holiday awareness
│   ├── core/
│   │   └── config.py                 # Pydantic BaseSettings loading .env
│   ├── db/
│   │   ├── database.py               # SQLAlchemy engine & session factory
│   │   └── models.py                 # Order, Position, AuditLog, Instrument tables
│   ├── security/
│   │   ├── audit_chain.py            # SHA-256 cryptographic blockchain-style audit log
│   │   ├── anomaly_detector.py       # Isolation Forest runtime anomaly detector
│   │   └── unified_risk_center.py    # Centralized killswitch and risk management coordinator
│   ├── trading/
│   │   ├── signals.py                # Signal, SignalDirection, Prediction dataclasses
│   │   ├── strategy.py               # EmaRsiVwapStrategy implementation
│   │   ├── pipeline.py               # TradingPipeline orchestrator
│   │   ├── risk_engine.py            # Deterministic RiskEngine & AccountState
│   │   ├── position_sizer.py         # Dynamic ATR & Kelly position sizing
│   │   ├── position_manager.py       # Live position tracker, Trailing SL/TP, statutory charges
│   │   ├── order_manager.py          # Order state machine & idempotency manager
│   │   ├── ml_engine.py              # XGBoost, Random Forest, Logistic Regression training pipeline
│   │   ├── ml_monitor.py             # Prediction drift, rolling accuracy, regime classification
│   │   ├── model_registry.py         # Champion–Challenger shadow evaluation & auto-rollback
│   │   ├── reconciliation.py         # Broker vs internal position reconciliation engine
│   │   ├── paper_report.py           # Multi-day paper journal, Sharpe/Sortino, validation verdict
│   │   └── portfolio_optimizer.py    # Markowitz mean-variance optimization & Sharpe maximizer
│   ├── utils/
│   │   └── indicators.py             # EMA, RSI, ATR, VWAP, MACD math utilities
│   └── static/
│       ├── index.html                # Zero-build operational dashboard
│       ├── app.js                    # Vanilla JS WebSocket client and live UI updater
│       └── styles.css                # Premium dark glassmorphic stylesheet
├── dashboard/                        # Modern React 18 + Vite frontend
│   ├── src/
│   │   ├── App.tsx                   # Main trading console component
│   │   ├── index.css                 # Design system tokens and styling
│   │   └── main.tsx                  # React DOM root
│   ├── package.json
│   └── vite.config.ts
└── tests/                            # Comprehensive Pytest test suite (169 passing tests)
```

---

## 4. Deep-Dive: System Modules & Engines

### 4.1 Broker Integration (`app/broker/`)
* **`kite_adapter.py`**:
  * Wraps the official `kiteconnect.KiteConnect` client.
  * Handles OAuth login via `get_login_url()` and `generate_session(request_token)`.
  * Manages dual modes: `LIVE` (sends real orders to exchange) vs `DRY_RUN` (persists paper orders to `dry_run_state.json` while fetching real market quotes).
  * Implements `broker_retry` decorator with exponential backoff for transient network errors (HTTP 502, 503, connection timeouts).
* **`ticker.py`**:
  * Manages `kiteconnect.KiteTicker` WebSocket streaming at sub-second speeds.
  * Configured in `MODE_FULL`, extracting: Last Traded Price (LTP), Open, High, Low, Close (OHLC), Volume, and Best Bid/Ask depth.
  * Automatically resubscribes upon reconnection.
* **`market_status.py`**:
  * Enforces Indian Standard Time (IST, UTC+05:30) trading hours: **09:15 to 15:30**.
  * Flags `CLOSED`, `PRE_OPEN`, `OPEN`, and `STALE` (when data latency exceeds 300 seconds).

---

### 4.2 Trading Strategy & Quantitative Pipeline (`app/trading/`)

#### 1. Strategy Engine (`strategy.py`)
* **Concrete Strategy:** `EmaRsiVwapStrategy` (Version: `v1.1-EMA-RSI-VWAP`).
* **Buy Rules:**
  1. Fast EMA (9) crosses above Slow EMA (21).
  2. Relative Strength Index (RSI 14) is not overbought ($< 70.0$).
  3. Current Price is trading above Volume Weighted Average Price ($\text{LTP} > \text{VWAP}$).
* **Sell Rules:**
  1. Fast EMA (9) crosses below Slow EMA (21).
  2. RSI (14) is not oversold ($> 30.0$).
  3. Current Price is trading below VWAP ($\text{LTP} < \text{VWAP}$).
* **Dynamic Exits:**
  * Stop-Loss: $\text{ATR}(14) \times 1.5$ distance from entry.
  * Take-Target: Based on Risk-Reward Ratio (default: $2.0 \times \text{Stop Distance}$).

#### 2. Machine Learning Engine (`ml_engine.py`)
* Implements multi-model classification on 6 statistical features:
  * Returns: 1-bar, 5-bar, 15-bar percentage change.
  * Volatility: 15-bar rolling standard deviation.
  * Trend: 10/30 Simple Moving Average ratio ($\text{SMA}_{10} / \text{SMA}_{30}$).
  * Mean Reversion: Price-to-SMA10 ratio.
* Models included: `XGBClassifier`, `RandomForestClassifier`, `GradientBoostingClassifier`, `LogisticRegression`.
* Evaluates out-of-sample test accuracy and provides calibrated probability scores via `predict_proba()`.

#### 3. Model Registry & Champion–Challenger Framework (`model_registry.py`)
* Manages continuous model lifecycle:
  * **Champion (`champ_gemini_quant_v1`):** Active production model routing real capital decisions.
  * **Challenger (`test_lstm_v2` / `challenger_xgb_v1_1`):** Shadow model evaluating parallel paper predictions in real time.
  * **Fallback (`fallback_rules_v0_9`):** Hardened deterministic rule-based safety model.
* **Auto-Promotion Criteria:** Challenger completes $\ge 15$ predictions and outperforms Champion rolling accuracy by $\ge 5\%$.
* **Auto-Rollback / Killswitch:** If Champion rolling accuracy drops below $45\%$, system rolls back to fallback; if it drops below $35\%$, emergency stop halts trading.

#### 4. Deterministic Risk Engine (`risk_engine.py`)
Before any order reaches the broker, it must pass 12 distinct non-bypassable checks:
1. **Market Hours:** Reject orders outside 09:15–15:30 IST.
2. **Circuit Limit Protection:** Reject buy orders within 1.5% of the Upper Circuit limit or sell orders within 1.5% of the Lower Circuit limit.
3. **Liquidity Check:** Reject orders if stock's average candle volume $< 1,000$ shares.
4. **Order Value Cap:** Max order capital (default ₹100,000).
5. **Quantity Cap:** Max shares per order (default 1,000 shares).
6. **Position Size Cap:** Single position value $\le 20\%$ of account equity.
7. **Total Portfolio Exposure:** Total open position value $\le 150\%$ of margin.
8. **Max Open Positions:** Maximum concurrent active positions (default 5).
9. **Sector Concentration Cap:** Max $35\%$ exposure in any single sector (IT, Banking, Energy, FMCG, Auto, Pharma, Metals, Infra).
10. **Daily Loss Limit:** If daily realized + unrealized loss breaches $-₹15,000$, trigger Emergency Killswitch.
11. **Available Margin Check:** Requires $1.05 \times$ required margin buffer.
12. **Idempotency Guard:** Rejects duplicate signals sent within the same minute.

#### 5. Dynamic Position Sizer (`position_sizer.py`)
Calculates order quantity dynamically based on account equity, volatility, and AI confidence:
$$\text{Risk Budget} = \text{Account Equity} \times \min(0.015, \text{Risk Budget \%}) \times \min(\text{Confidence}, 1.0)$$
$$\text{Quantity} = \left\lfloor \frac{\text{Risk Budget}}{\text{Entry Price} - \text{Stop Loss}} \right\rfloor$$

#### 6. Position Manager & Trailing Stop Engine (`position_manager.py`)
* Continuously checks open positions against live market price.
* Automatically triggers exit when Stop-Loss or Take-Profit is breached.
* **Dynamic Trailing Stop-Loss:** Locks in profits as market moves in favorable direction (default: $1.5\%$ trailing distance).
* **Statutory Charge Calculations:** Calculates exact net PnL:
  * Brokerage: $0.03\%$ or ₹20 (whichever is lower).
  * STT: $0.025\%$ on intraday equity sell.
  * Exchange Turnover: $0.00325\%$.
  * GST: $18\%$ on (Brokerage + Exchange Turnover).
  * Stamp Duty: $0.003\%$ on buy value.

---

### 4.3 AI Agent Layer (`app/agent/`)
* **`AgentService`**:
  * Utilizes Google Gemini (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-flash-latest`).
  * Generates structured trade proposals in JSON format: direction, stop loss, take target, quantity, and natural language market reasoning.
  * **Rate-Limit Circuit Breaker:** When Gemini API returns `429 RESOURCE_EXHAUSTED` (daily/minute quota limits), the agent enters an automatic **3-minute backoff**, immediately falling back to fast local technical reasoning without blocking the event loop or stalling WebSocket feeds.

---

### 4.4 Security & Governance (`app/security/`)
* **`AuditChain` (`audit_chain.py`)**:
  * Cryptographically links every system action (`ORDER_EVENT`, `SIGNAL`, `RISK_REJECTION`, `ANOMALY_HALT`) into an immutable SHA-256 hash chain persisted in `audit.jsonl`.
  * Allows mathematical verification of log integrity via `/api/v1/system/audit/verify`.
* **`AnomalyDetector` (`anomaly_detector.py`)**:
  * Machine learning anomaly detection evaluating order rate, order value %, concentration %, AI confidence, and data lag.
  * Automatically trips emergency stop if anomaly score drops below critical threshold.
* **`UnifiedRiskCenter` (`unified_risk_center.py`)**:
  * Single source of truth coordinating reconciliation alerts, sector caps, audit chain integrity, and emergency halt state.

---

## 5. REST & WebSocket API Specification

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/v1/auth/login` | `GET` | Initiates Zerodha OAuth flow (returns login URL). |
| `/api/v1/auth/callback` | `GET` | Exchanges request token for session access token and redirects to dashboard. |
| `/api/v1/portfolio` | `GET` | Returns live holdings, open positions, account margin, and real-time watchlist. |
| `/api/v1/audit-logs` | `GET` | Retrieves recent audit logs. |
| `/api/v1/trades/action` | `POST` | Operator approves (`APPROVE`) or rejects (`REJECT`) a pending candidate trade. |
| `/api/v1/positions/square-off-all` | `POST` | Emergency manual action to instantly exit all open positions. |
| `/api/v1/system/status` | `GET` | System operational status, trading mode (`LIVE`/`DRY_RUN`), and killswitch state. |
| `/api/v1/system/emergency-stop` | `POST` | Manually triggers the global emergency killswitch. |
| `/api/v1/system/resume` | `POST` | Operator resets the emergency killswitch and resumes trading. |
| `/api/v1/system/models/status` | `GET` | Current Champion and Challenger performance and rolling accuracy. |
| `/api/v1/system/risk/sectors` | `GET` | Current sector allocation vs max limits. |
| `/api/v1/system/risk/var` | `GET` | Historical Value at Risk (VaR) and Conditional VaR (CVaR). |
| `/api/v1/system/paper-report` | `GET` | Multi-day paper trading validation metrics and verdict. |
| `/api/v1/system/audit/verify` | `GET` | Validates the mathematical integrity of the SHA-256 audit chain. |
| `/ws/candidate-trades` | `WebSocket` | Real-time 1 Hz stream of market updates, live ticks, positions, and AI proposals. |

---

## 6. Configuration Guide (`.env`)

```ini
# Zerodha Kite Connect Credentials
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
KITE_REDIRECT_URL=http://localhost:8000/api/v1/auth/callback

# Environment Setting: DRY_RUN (Paper Trading) or LIVE (Real Broker Capital)
TRADING_MODE=DRY_RUN

# Execution Autonomy: True = fully autonomous order placement; False = requires operator approval
AUTONOMOUS_EXECUTION=True

# Google Gemini API Key for AI Market Reasoning
GEMINI_API_KEY=your_gemini_api_key

# Active Watchlist (Comma-separated Yahoo Finance / NSE symbols)
TRADING_SYMBOLS=RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS,ITC.NS,SBIN.NS,BHARTIARTL.NS,KOTAKBANK.NS,LT.NS

# SQLite Database Location
DATABASE_URL=sqlite:///./trading_agent.db
```

---

## 7. Operational Runbook

### 7.1 Daily Startup Sequence
1. **Activate Environment & Start Backend:**
   ```bash
   cd /Users/pranavgupta/Desktop/Capstone
   source venv/bin/activate
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. **Start Vite Dashboard (Optional):**
   ```bash
   cd dashboard
   npm run dev
   ```
3. **Daily Authentication (Required once per market session):**
   * Open: `http://127.0.0.1:8000/api/v1/auth/login`
   * Log in to Zerodha with your 2FA credentials.
   * Zerodha redirects to `/dashboard?auth=success`, and `MarketTicker` connects to `wss://ws.kite.trade` streaming live exchange ticks.
4. **Monitor Console:**
   * Open `http://127.0.0.1:8000/dashboard` or `http://localhost:5173`.
   * Confirm Watchlist LTPs are active, Market Status reads `OPEN`, and Emergency Stop is `INACTIVE`.

### 7.2 Emergency Procedures
* **Immediate Halt:** Click **"Emergency Stop"** on the dashboard or run:
  ```bash
  curl -X POST http://localhost:8000/api/v1/system/emergency-stop
  ```
* **Square-Off All Open Positions:**
  ```bash
  curl -X POST http://localhost:8000/api/v1/positions/square-off-all
  ```
* **Verify Audit Chain:**
  ```bash
  curl http://localhost:8000/api/v1/system/audit/verify
  ```

---

## 8. Test Suite & Verification

The system includes **180 comprehensive unit and integration tests** verifying all critical paths across 34 test files:
* Circuit limits, liquidity gates, and pre-trade statutory fee hurdle calculations.
* Model registry auto-promotion, rollback, and Brier score evaluation.
* Signal Quality Scoring (0–100) and Cross-Sectional Trade Ranking.
* Multi-Timeframe trend alignment and dynamic regime-based Stop-Loss/Take-Profit.
* Continuous expected-return regression and rolling walk-forward retraining.
* Tamper-evident audit chain hashing and tampering detection.
* Broker adapter state recovery, idempotency, and reconciliation.

Run all tests via:
```bash
venv/bin/pytest
```
*Output: 180 passed in ~9.04s.*
