# Zerodha AI Trading Agent

A Python/FastAPI automated trading agent using the Zerodha Kite Connect API. The system evaluates trading signals, enforces risk management rules (like liquidity and time-of-day checks), and executes trades. It features a modern web dashboard for monitoring positions, audit logs, and system health in real-time.

## Features
- **Trading Pipeline:** Automated orchestration of signal generation, risk evaluation, and order execution.
- **Dry Run & Live Modes:** Toggle between paper trading and real execution seamlessly via `.env`.
- **Live Dashboard:** WebSocket-powered dashboard to view candidate trades, active positions, and recent audit logs.
- **Risk Engine:** Enforces market hours constraints, maximum trade limits, and liquidity requirements before order placement.
- **Order Management:** Tracks order history and performs reconciliation against live broker positions.

## Setup Instructions

1. **Environment Setup:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configuration (`.env`):**
   Create a `.env` file at the project root containing your Kite Connect API credentials:
   ```env
   KITE_API_KEY=your_api_key
   KITE_API_SECRET=your_api_secret
   TRADING_MODE=DRY_RUN  # Change to LIVE for real trading
   PROJECT_NAME="Zerodha AI Trading Agent"
   ```

3. **Running the Application:**
   Start the FastAPI server:
   ```bash
   source venv/bin/activate
   uvicorn app.main:app --reload --port 8000
   ```

4. **Authentication:**
   - Navigate to `http://127.0.0.1:8000/api/v1/auth/login` to begin the OAuth flow.
   - You will be redirected to the Zerodha login page.
   - Upon successful login, Zerodha redirects to the callback endpoint to generate an active session token.

5. **Access the Dashboard:**
   Open `http://127.0.0.1:8000/dashboard` in your browser to monitor trading activity and manage positions.

## Operational Procedures
For detailed procedures on starting, stopping, and handling emergencies in a live environment, refer to the [RUNBOOK.md](RUNBOOK.md).
