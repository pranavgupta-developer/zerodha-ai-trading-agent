# AI-Powered Zerodha Trading Agent — Development Brief

> Paste this entire document into Cursor / Windsurf / Trae (or any agentic coding IDE) as your starting prompt.

---

## 1. Problem Statement

I want to build a **personal, semi-autonomous AI trading agent** that connects to my own Zerodha (Kite Connect) account, watches live NSE/BSE market data, evaluates configurable trading strategies using technical indicators, and can propose — and eventually place — trades on my behalf, inside strict, deterministic risk limits that I control.

This is for **my own personal use only** (single user, no multi-tenant concerns), running on a **local machine or a VPS that I manage myself**. There is no need to support other users, billing, or a public-facing product.

This system is being built to place **real, live orders against a real Zerodha account with real capital** — it is not a backtesting or simulation project. Because of that, safety and correctness matter even in a fast MVP: any code path that can place an order must be wrapped in explicit, testable risk checks before it ever talks to the broker. The goal for this first pass is a **fast, working MVP of the core live trading loop** — not the entire enterprise-grade security architecture described below. Advanced hardening (prompt-injection defense, capability-based access control, anomaly detection, tamper-evident audit chains, etc.) is explicitly deferred to later phases and should not block getting a real, working live system running.

**Definition of success for the MVP:** I can authenticate with Zerodha, see my live holdings/positions/funds, get live market data for a watchlist of symbols, run at least one configurable strategy that generates buy/sell signals from technical indicators, have those signals checked against hard-coded risk limits, and — with my explicit confirmation — place a **live order with real capital** that gets tracked through to fill, all visible on a simple local dashboard, with net P&L accounting for real brokerage, STT, and other charges.

---

## 2. Scope for This Build (MVP — build this first)

Build **only** the following in this pass. Everything else in Section 7 ("Full Feature Backlog") is future work — do not attempt it now, but keep the architecture clean enough that it can be added later without a rewrite.

### 2.1 Live Zerodha Integration (core)
- Kite Connect login flow (API key/secret, request token → access token exchange)
- Store the access token securely (encrypted at rest or in a local secrets file, never in plaintext in git)
- Fetch funds/margins, holdings, positions, order book
- Place, modify, and cancel orders
- Basic broker error handling (auth expiry, invalid order, network errors) with clear error surfacing
- Track order status transitions: `CREATED → SUBMITTED → OPEN/PARTIALLY_FILLED → COMPLETE/REJECTED/CANCELLED`

### 2.2 Real-Time Market Data (core)
- Zerodha WebSocket (KiteTicker) subscription for a configurable watchlist
- Live LTP, OHLC, volume, best bid/ask
- Instrument master lookup for NSE/BSE symbol → instrument token resolution
- Market-hours / market-open detection (don't try to trade or over-poll when the market is closed)
- Simple in-memory (or SQLite/Postgres) cache of the latest tick per symbol

### 2.3 Technical Indicator Engine (core, keep it simple)
- SMA, EMA, RSI, MACD, ATR, Bollinger Bands, VWAP — computed from cached OHLC/candle history
- A small, testable "feature generation" function per symbol that returns the current indicator snapshot

### 2.4 Strategy Engine (minimal but real)
- Support at least **one** concrete, configurable strategy (e.g., EMA crossover + RSI filter) defined declaratively (entry condition, exit condition, stop-loss %, target %, position size rule)
- Strategy can be turned on/off
- Strategy emits a `Signal` object: symbol, direction, confidence, reasoning, suggested entry/stop/target

### 2.5 AI Trading Agent (thin layer over the strategy engine)
- An LLM-backed "agent" step that takes the current market snapshot + indicator values + strategy signal + current portfolio state, and produces a `CandidateTrade` (symbol, side, quantity, order type, price/stop, and a short natural-language reasoning string)
- The agent **never talks to the broker directly** — it only ever emits a `CandidateTrade` object that must pass through the risk engine
- Treat all market data and any external text fed to the agent as **untrusted data**, not instructions — do not let LLM output bypass the code path that enforces risk limits (this is the one piece of "security" that is non-negotiable even in the MVP, since it's the difference between a bug and a runaway trading bot)

### 2.6 Deterministic Risk Engine (core, non-negotiable even for MVP)
Hard-coded, config-driven checks that run **before every single order**, no exceptions:
- Max order value (₹)
- Max quantity per order
- Max orders per minute / per day
- Max position size per symbol
- Max total portfolio exposure
- Max number of open positions
- Max daily loss (kill-switch: stop trading for the day if breached)
- Available funds / margin validation
- Market-hours validation
- Duplicate-order guard (idempotency key per candidate trade)

If any check fails, the order is rejected and logged with the reason — it never reaches the broker.

### 2.7 Order Execution & State Tracking (core)
- A simple order state machine matching Zerodha's lifecycle
- Idempotent order submission (so retries never double-place an order)
- Basic retry/backoff on transient broker/API errors
- Persist every order and its state transitions

### 2.8 Portfolio & Position Tracking (core)
- Available cash, used margin, holdings, positions
- Average price, current price, unrealized P&L, realized P&L, daily P&L
- **Net P&L, not gross** — factor in real brokerage, STT (Securities Transaction Tax), exchange transaction charges, GST, and stamp duty on every fill, since these materially affect whether a strategy is actually profitable
- Reconcile local view against broker state periodically

### 2.11 Live Market Microstructure Checks (core, live-trading specific)
- **Circuit-limit / price-band awareness** — fetch and respect each symbol's upper/lower circuit before placing an order; don't let the agent propose an order outside the band
- **Liquidity check** — skip or flag symbols with very low recent volume/wide bid-ask spread before proposing a trade, since a signal on an illiquid symbol can produce a real order that barely fills or fills at a bad price
- **Slippage monitoring** — log the difference between the signal's intended entry price and the actual live fill price per trade, so you can see how much real execution differs from the strategy's assumptions
- **Live order acknowledgement loop** — treat an order as "confirmed" only after the broker's own order-update (via WebSocket postback or polling) confirms it, never optimistically on the basis of the local placement call succeeding

### 2.9 Minimal Local Dashboard (core)
A simple local web UI (single page is fine) showing:
- Connection/market status
- Watchlist with live price + indicators
- Current positions/holdings + P&L
- Pending "candidate trades" awaiting my approval, with the AI's reasoning shown
- **Approve / Reject** buttons for each candidate trade (manual-in-the-loop for the MVP — full autonomy is a later phase)
- Order history/log
- A visible, always-available **"Emergency Stop"** button that immediately halts new order submission

### 2.10 Basic Audit Logging (core, simplified)
- Every candidate trade, risk decision (pass/fail + reason), and order event written to an append-only local log (JSON lines file or a simple Postgres/SQLite table is enough — skip hash-chaining for now)

---

## 3. Explicitly Out of Scope for MVP (do not build yet)
- Capability-Based Access Control (CapBAC) — multi-agent/multi-user permission graph
- Formal prompt-injection detection subsystem with confidence scoring
- Anomaly detection engine (behavioral pattern monitoring)
- Tamper-evident hash-chained audit log
- Multi-strategy portfolio orchestration / strategy versioning
- Full self-healing / circuit-breaker infrastructure
- Multi-user auth, RBAC, SaaS billing
- Distributed tracing, metrics dashboards, production observability stack

Keep the code modular (clear boundaries between: broker adapter, market data, indicators, strategy, agent, risk engine, execution, portfolio, audit) so these can be layered in later without rearchitecting.

---

## 4. Tech Stack (with reasoning)

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.11+ with FastAPI** | Zerodha's official `kiteconnect` SDK is Python; FastAPI gives you async WebSocket handling for KiteTicker and a simple REST API for the dashboard with minimal boilerplate. |
| Broker SDK | **`kiteconnect` (official pykiteconnect)** | Officially maintained, handles auth flow and REST + WebSocket ticker. |
| Task/loop runner | **Python `asyncio` + a simple scheduler (APScheduler)** | You need a background loop polling/streaming ticks, running strategies, and checking risk — asyncio is enough at this scale, no need for Celery/Kafka yet. |
| Database | **SQLite for MVP, with a clean path to Postgres later** | SQLite needs zero setup for a single-user local system; use SQLAlchemy so swapping to Postgres later is a one-line config change. |
| Frontend/dashboard | **A single React (Vite) page, or plain HTML+HTMX if you want to move even faster** | You just need live-updating tables and two buttons (approve/reject) — no need for a heavy frontend stack. |
| Live updates to dashboard | **WebSocket (FastAPI's built-in support) or Server-Sent Events** | Simplest way to push live ticks/positions/candidate trades to the browser without polling. |
| LLM for the "AI agent" step | **Anthropic Claude API (Sonnet-class model), called with structured/JSON output** | Good at reasoning over indicator data + producing structured `CandidateTrade` JSON with an explanation; keep the system prompt strict about "you may only output a CandidateTrade object, you cannot call the broker." |
| Secrets | **`.env` file (local) or OS keychain, never committed to git** | Simple and sufficient for a single local/VPS deployment. |
| Deployment | **Docker + docker-compose** | Even for a "local machine or VPS I manage" setup, Docker makes it trivial to restart cleanly, pin dependency versions, and eventually move to a bigger box. |

---

## 5. Architecture Overview

```
                     ┌─────────────────────────┐
                     │   Zerodha (Kite Connect) │
                     │  REST API + WebSocket    │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │   Broker Adapter Layer   │  (auth, orders, funds, reconnection)
                     └───────────┬─────────────┘
                                 │
      ┌──────────────────────────┼───────────────────────────┐
      │                          │                           │
┌─────▼──────┐          ┌────────▼────────┐          ┌───────▼────────┐
│ Market Data │          │ Portfolio Store  │          │  Order Manager │
│  + Cache    │          │ (positions, P&L) │          │ (state machine)│
└─────┬──────┘          └────────┬────────┘          └───────┬────────┘
      │                          │                           │
┌─────▼──────┐                  │                           │
│ Indicator   │                  │                           │
│ Engine      │                  │                           │
└─────┬──────┘                  │                           │
      │                          │                           │
┌─────▼──────┐                  │                           │
│ Strategy    │                  │                           │
│ Engine      │                  │                           │
└─────┬──────┘                  │                           │
      │  Signal                 │                           │
┌─────▼──────┐                  │                           │
│ AI Agent    │                  │                           │
│ (Claude)    │                  │                           │
└─────┬──────┘                  │                           │
      │  CandidateTrade          │                           │
┌─────▼──────┐                  │                           │
│ Risk Engine │──── reject ──────┤   (logged, never sent)    │
│ (deterministic)                │                           │
└─────┬──────┘                  │                           │
      │ approved                │                           │
      └──────────────────────────┴─────────► Order Manager ──► Broker Adapter
                                 │
                     ┌───────────▼─────────────┐
                     │   Dashboard (FastAPI +   │
                     │   WebSocket/HTMX/React)  │
                     │  approve/reject/E-STOP   │
                     └──────────────────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │      Audit Log (DB)      │
                     └──────────────────────────┘
```

Key rule baked into the architecture: **the only path from "AI decision" to "real order" runs through the deterministic Risk Engine.** The AI agent's output is just data (a `CandidateTrade`), never a command that executes directly.

---

## 6. Development Roadmap — Phase-by-Phase, Week-by-Week

This expands Section 2's MVP into day-level tasks (Phase 1), then lays out Phases 2–4 at week granularity so the later hardening work (Section 7's backlog) has a concrete home once the MVP is live and trading in paper mode.

### PHASE 1 — Core Trading Loop (Weeks 1–4) — build this now

**Week 1 — Broker & Data Foundations**
- *Day 1–2:* Project scaffold (FastAPI app, SQLAlchemy + SQLite, Docker + docker-compose, `.env`/secrets handling, `.gitignore`). Kite Connect app registration; implement the login/request-token/access-token exchange flow end-to-end.
- *Day 3:* REST integration: fetch funds/margins, holdings, positions, order book. Wrap all broker calls in a single `BrokerAdapter` class so nothing else in the codebase calls `kiteconnect` directly.
- *Day 4:* KiteTicker WebSocket integration — subscribe to a hard-coded watchlist (5–10 symbols), handle tick callbacks, log basic connect/disconnect events.
- *Day 5:* Persist ticks into 1-min candles in SQLite; instrument-master lookup for NSE/BSE symbol → token resolution; market-hours/holiday check helper.
- *Day 6–7:* Buffer/catch-up day — write unit tests for the broker adapter (mocked API) and the candle aggregator; fix whatever broke.

**Week 2 — Indicators, Strategy, Risk Engine**
- *Day 1:* Implement SMA, EMA, RSI against candle history with unit tests against known reference values.
- *Day 2:* Implement MACD, ATR, Bollinger Bands, VWAP; assemble a single "feature snapshot" function per symbol.
- *Day 3:* Implement one concrete strategy (e.g., EMA crossover + RSI filter) as a config-driven object producing `Signal` (symbol, direction, confidence, suggested entry/stop/target).
- *Day 4:* Build the deterministic Risk Engine skeleton + config schema (max order value, max qty, max orders/min/day, max position size, max exposure, max daily loss, funds/margin check, market-hours check).
- *Day 5:* Unit-test the Risk Engine exhaustively — one test per rule, both pass and fail cases; this is the most important test suite in the whole project.
- *Day 6–7:* Implement idempotent order placement (idempotency key per candidate trade), the order state machine (`CREATED→SUBMITTED→OPEN/PARTIALLY_FILLED→COMPLETE/REJECTED/CANCELLED`), and basic retry/backoff on transient errors.

**Week 3 — AI Agent + Dashboard + Human-in-the-Loop**
- *Day 1:* Define the `CandidateTrade` schema and write the Claude API prompt that turns (market snapshot + indicators + signal + portfolio state) into a `CandidateTrade` + reasoning, forcing strict JSON output.
- *Day 2:* Wire the agent step into the pipeline: Strategy Signal → AI Agent → `CandidateTrade` → Risk Engine (log-only for now, don't execute yet).
- *Day 3:* Build the dashboard skeleton (single page): live watchlist table, positions/P&L table, connection/market-status indicator.
- *Day 4:* Add the candidate-trades panel with AI reasoning shown, plus **Approve / Reject** buttons; push updates over WebSocket/SSE.
- *Day 5:* Wire Approve → Risk Engine → Order Manager → Broker Adapter (Reject just logs and discards). Add the always-visible **Emergency Stop** button that flips a global "no new orders" flag.
- *Day 6–7:* Basic audit logging: every signal, every risk decision (with reason), every order event written to an append-only table; add an order-history view to the dashboard.

**Week 4 — Hardening for Live Trading**
- *Day 1:* Add a `TRADING_MODE=DRY_RUN|LIVE` config flag; in `DRY_RUN`, run the entire pipeline against **live real-time market data** but stop just short of the broker's order-placement call (log what *would* have been sent). This validates the whole live data path without risking capital, in hours rather than days.
- *Day 2:* Run one full live market session in `DRY_RUN`, watching real signals and candidate trades against real live prices; fix bugs in signal timing, indicator lag, or dashboard refresh using real data.
- *Day 3:* Add WebSocket reconnection logic and broker-API retry/backoff; kill the process mid-live-session and verify it recovers cleanly without losing track of any open live position.
- *Day 4:* Implement and explicitly test the daily-loss kill-switch against your real account's actual available margin figures.
- *Day 5:* Implement the circuit-limit, liquidity, and slippage checks from Section 2.11 and verify them against real live quotes.
- *Day 6:* Switch to `LIVE` mode with the smallest possible real order size (e.g., 1 share of a liquid large-cap) on a single symbol; place, track, and manually close a real trade end-to-end.
- *Day 7:* Write the live-trading runbook (start/stop/emergency-stop/log-checking/what to do if reconciliation flags a mismatch) and a short README; tag this as `v0.1-live-mvp`.

---

### PHASE 2 — Verification & Reliability (Weeks 5–8)
Only start once Phase 1 has run safely in **live mode with real capital** for at least a week or two.

**Week 5 — Verification Engine**
- *Day 1:* Design the reconciliation job: pull broker positions/holdings/orders on a schedule (e.g., every 60s during market hours) and diff against local state.
- *Day 2:* Implement schema validation on every broker API response (reject/quarantine malformed responses instead of trusting them blindly).
- *Day 3:* Implement mismatch alerting — log + a red banner on the dashboard the moment local and broker state disagree.
- *Day 4:* Add a "reconcile now" manual trigger button on the dashboard for use right after any live incident.
- *Day 5:* Run the reconciliation job through a full live trading day and tune the polling interval against real API rate limits.

**Week 6 — Expanded Risk Engine for Live Markets**
- *Day 1:* Price-deviation validation — reject a candidate trade if its price is more than X% away from the live LTP (guards against stale-signal or bad-quote orders).
- *Day 2:* Max-strategy-loss and max-drawdown limits, tracked per strategy against real realized P&L.
- *Day 3:* Per-symbol exposure limits (cap how much capital can sit in one name at once).
- *Day 4:* Harden duplicate-order validation using broker order IDs + your idempotency keys together, checked against real (not simulated) broker responses.
- *Day 5:* Live-fire test each new rule with real (tiny) orders during market hours to confirm it behaves as designed against the live order book.

**Week 7 — Self-Healing Basics**
- *Day 1:* Circuit breaker around the broker adapter (trip after N consecutive failures, auto-halt new orders while tripped).
- *Day 2:* Tune exponential backoff parameters using real failure/latency data captured from live trading, not assumptions.
- *Day 3:* Stale-tick detection — flag and pause a symbol if no tick arrives within N seconds during market hours (common with illiquid names).
- *Day 4:* WebSocket auto-reconnect hardening — simulate a live mid-session disconnect and confirm the system resubscribes and catches up cleanly.
- *Day 5:* Live-day soak test: let it run a full session with self-healing active and review the incident log afterward.

**Week 8 — Strategy Expansion**
- *Day 1–2:* Add a second concurrent strategy running against live data alongside the first.
- *Day 3:* Strategy activation/deactivation controls on the dashboard, effective immediately on live signals.
- *Day 4:* Per-strategy live P&L tracking and per-strategy loss limits wired into the Risk Engine.
- *Day 5:* Run both strategies live for a full session; confirm they don't double-trade the same symbol or exceed combined exposure limits.

### PHASE 3 — Security Hardening (Weeks 9–12)
This is where the "AI safety" parts of the original spec come in, once you trust the core loop against real, live order flow.

**Week 9 — Untrusted-Data Isolation**
- *Day 1–2:* Formalize the boundary between "market data / any text the agent sees" and "instructions" in the agent's prompt/context construction.
- *Day 3–4:* Add basic prompt-injection pattern detection on any text fed into the agent's context (e.g., news headlines, broker messages).
- *Day 5:* Adversarial test: feed the live agent a deliberately manipulated data field and confirm it cannot influence order size/direction outside Risk Engine bounds.

**Week 10 — Capability-Based Access Control (CapBAC) v1**
- *Day 1–2:* Design and issue a scoped, expiring capability token per live trading session (symbols it may trade, max value it may propose).
- *Day 3:* Wire the Risk Engine to check the capability before it checks numeric limits — no capability, no order, regardless of what the agent proposes.
- *Day 4:* Capability revocation flow, testable live from the dashboard.
- *Day 5:* Run a full live session under CapBAC and confirm normal trading is unaffected while an expired/invalid capability is correctly rejected.

**Week 11 — Anomaly Detection v1**
- *Day 1:* Orders-per-minute and order-size monitors against live order flow.
- *Day 2:* Trading-frequency and symbol-frequency monitors.
- *Day 3:* Wire anomaly triggers to auto-fire Emergency Stop and generate a security event.
- *Day 4–5:* Live-fire test by intentionally driving each monitored metric past its threshold in a controlled way (small size) and confirming auto-stop fires correctly.

**Week 12 — Tamper-Evident Audit Log**
- *Day 1–2:* Add hash-chaining (each audit entry stores the hash of the previous entry) to the existing live audit log without disrupting logging throughput.
- *Day 3:* Build a chain-integrity verification job.
- *Day 4:* Run it against the real log accumulated from Phases 1–2's live sessions to confirm no gaps.
- *Day 5:* Document the audit trail format for future reference (useful if you ever need to reconstruct a live trading day).

### PHASE 4 — Production Polish (Weeks 13–16)

**Week 13 — Observability**
- *Day 1–2:* Structured logging across all modules with consistent fields (session ID, symbol, order ID).
- *Day 3:* Basic metrics: API/broker/agent/risk-engine latency, captured from real live traffic.
- *Day 4:* Health/readiness endpoints.
- *Day 5:* Build a small metrics view into the dashboard so you can see live-system health at a glance during market hours.

**Week 14 — Full Self-Healing**
- *Day 1:* Dead-letter handling for order events that fail all retries during live trading.
- *Day 2–3:* Queue recovery after a crash — restart mid-session and confirm no live order state is lost or duplicated.
- *Day 4:* Graceful shutdown that finishes in-flight order state transitions before exiting.
- *Day 5:* Live chaos test: kill the process at a few different points during a live session and verify recovery each time.

**Week 15 — Security Attack Testing**
- *Day 1:* Prompt-injection attempt suite.
- *Day 2:* Malformed trade request / invalid symbol / invalid quantity / invalid price suite.
- *Day 3:* Excessive-order and excessive-position attack suite.
- *Day 4:* Expired/invalid/escalated capability use suite.
- *Day 5:* Run the full attack suite against a live (small-size) session and confirm every attack is rejected and logged with a security event.

**Week 16 — Research/Benchmarking**
- *Day 1–2:* Measure detection rates and false-positive rates from Phase 3's live-fire tests.
- *Day 3:* Measure end-to-end latency (signal → agent → risk engine → live order ack) under real market conditions.
- *Day 4:* Compare a "secured" live session against a hypothetical unsecured baseline (which checks would have let a bad order through).
- *Day 5:* Decide, with real live-trading data in hand, what (if anything) from Section 7's remaining backlog is still worth building for a single-user system.

---

## 7. Full Feature Backlog (Phase 2+, for later — do not build now)

Keep this list for context on where the system is headed, so the MVP's module boundaries stay compatible with it:

- **Security hardening**: Prompt-injection detection with confidence scoring, instruction-hierarchy enforcement, untrusted-data isolation, tool-input validation
- **Capability-Based Access Control (CapBAC)**: capability issuance/validation/expiration/scoping/delegation/revocation, capability graph, least-privilege enforcement
- **Verification Engine**: independent fill/position/portfolio reconciliation against broker state, schema validation on all broker responses
- **Anomaly Detection**: orders-per-minute, order-size, trading-frequency, position-concentration, buy/sell-ratio, loss-pattern, strategy-deviation monitoring
- **Self-Healing**: exponential backoff everywhere, circuit breakers, queue recovery, stale-data detection, automated agent recovery with human-intervention escalation
- **Tamper-Evident Audit Logging**: hash-chained log entries with integrity verification
- **Multi-strategy orchestration**: strategy versioning, multiple concurrent strategies, per-strategy performance tracking and loss limits
- **Full Emergency Stop System**: automatic capability revocation, pending-order handling, controlled capability reissuance on resume
- **Observability**: structured logging, metrics, distributed tracing across broker/order/agent/risk-engine latency
- **Reliability**: health/readiness/liveness checks, dead-letter queues, graceful shutdown, crash recovery
- **Security attack testing**: red-team suite for prompt injection, capability escalation, excessive-order/position attacks, malformed requests
- **Research/benchmarking**: secured-vs-unsecured agent comparison, detection rates, latency benchmarks

---

## 8. Important Considerations

### General
- **This system trades with real money from day one.** There is a brief `DRY_RUN` validation step (Week 4, Day 1–2) to sanity-check the live data path, but the target is a genuinely live system, not a permanent paper-trading simulator — don't over-invest in simulation infrastructure that live trading won't actually use.
- **Human-in-the-loop for the MVP.** Do not let the AI agent submit live orders autonomously yet — require manual Approve on the dashboard for every trade until you've watched it behave correctly across several real live sessions.
- **Rate limits.** Zerodha's API has rate limits on order placement and REST calls — implement basic client-side throttling so you don't get your API key throttled or banned mid-session.
- **Market hours.** NSE trading hours are 9:15 AM–3:30 PM IST on trading days — don't try to fetch live ticks or place orders outside this window; handle holidays too (a static NSE holiday list is fine for MVP).
- **Secrets management.** Never commit your Kite API key/secret or access token to git. Use a `.env` file, add it to `.gitignore` immediately — this matters even more once the key can place real orders.
- **Idempotency matters more than it seems.** A network retry that double-places a live order is the single most likely way to lose real money by accident — make every order submission idempotent from day one, not as a later hardening pass.
- **Test with tiny position sizes first.** Start with the smallest possible quantity/value the risk engine allows on a single, highly liquid symbol, and only scale up after you've verified the whole pipeline behaves as expected across several real live trading days.
- **Keep the risk engine dumb and deterministic on purpose.** It should be simple enough that you could review every check in five minutes and know exactly why any given live order would pass or fail — no AI, no fuzzy logic, just hard-coded thresholds from config.

### Live-Trading-Specific Operational Notes
- **Circuit limits and price bands.** NSE/BSE symbols have daily upper/lower circuit limits; a live order priced outside the band will simply be rejected by the exchange — check this client-side before submitting so you get a clean internal rejection instead of a confusing broker error.
- **Liquidity before signal, not after.** Filter your watchlist to reasonably liquid symbols; a technically "correct" signal on an illiquid stock can produce a live order that fills badly or not at all, which the backtested strategy logic never accounts for.
- **Slippage is real money.** Log intended vs. actual live fill price on every trade — over time this tells you whether your strategy's edge survives real execution costs, which paper/backtested numbers will not show you.
- **Costs eat into edge.** Zerodha's brokerage on equity delivery may be zero but intraday/F&O has per-order charges, plus STT, exchange charges, GST, SEBI charges, and stamp duty apply to every live fill — compute net P&L including these, not just raw price movement, or you'll overestimate your strategy's real profitability.
- **Contract notes / fund settlement.** Live equity trades settle on a T+1 basis in India — don't assume funds from a same-day sale are immediately available for a new buy; check actual available margin from the broker, not an assumed instantly-updated local balance.
- **Partial fills happen in live markets far more than in simulation.** Make sure the order state machine and P&L calculations correctly handle a live order that fills 60% now and the rest (or none) later, including if it's cancelled mid-fill.
- **Live network/API hiccups will happen during market hours.** Build reconnection and reconciliation (Section 2.11 / Phase 2) with the assumption that your connection to Zerodha *will* drop at least once during a live session — the system should never "lose track" of a real open position because of it.
- **Start small, verify, then scale.** After each phase's live-fire tests, review the audit log for that session before increasing position size or symbol count — real market conditions will surface issues no amount of dry-run testing will.
