# Live Trading Runbook

This runbook outlines operational procedures for managing the Zerodha AI Trading Agent in a live environment. **Always exercise caution when interacting with the LIVE trading mode.**

## 1. Start the Live System
1. **Verify Environment Configuration:** Ensure `.env` contains `TRADING_MODE=LIVE`.
2. **Start the Application:**
   ```bash
   source venv/bin/activate
   uvicorn app.main:app --port 8000
   ```
3. **Authenticate:**
   Navigate to `http://127.0.0.1:8000/api/v1/auth/login`. Proceed through the Kite Connect login flow. *Do not use `localhost` if Docker is running on your system, as it may cause port conflicts.*
4. **Monitor Start:** Access the dashboard at `http://127.0.0.1:8000/dashboard` and verify the system status indicator shows "Online".

## 2. Stop the Live System (Normal Shutdown)
1. Ensure there are no critical active trades that require immediate monitoring.
2. In the terminal running Uvicorn, press `Ctrl+C` to gracefully terminate the server.
3. *Note: Shutting down the application does not automatically square off open positions in your Kite account.*

## 3. Emergency Stop (Kill Switch)
If the system begins behaving erratically (e.g., executing unintended orders) or if you need to immediately halt all algorithmic activity:
1. **Trigger Emergency Stop:** Click the "Emergency Stop" button on the web dashboard (or send a `POST` request to `http://127.0.0.1:8000/api/v1/system/emergency-stop`). 
2. **Effect:** This immediately sets the global `EMERGENCY_STOP` flag to `True`, preventing any new orders from being placed.
3. **Manual Intervention:** After an emergency stop, log in to the official [Kite Web UI](https://kite.zerodha.com) immediately to review and manually close any open positions. The algorithmic engine must be restarted to clear the emergency state.

## 4. Log Checking and Monitoring
- **Console Logs:** Active trades, background tasks, and critical errors are logged directly to standard output (the terminal where Uvicorn is running). Keep this terminal visible.
- **Audit Dashboard:** The web dashboard provides a live-updating "Recent Audit Logs" table capturing key events (e.g., risk engine rejections, order placements, auth events).
- **API Access:** You can query historical logs via `GET /api/v1/audit-logs`.

## 5. Handling Reconciliation Mismatches
The application maintains a local database of executed trades. If the local state diverges from the actual Kite broker positions, the reconciliation mechanism will flag a mismatch.

**Symptoms:**
- The dashboard displays positions that don't match your actual Kite portfolio.
- Logs show continuous warnings regarding position discrepancies.

**Action Plan:**
1. **Halt Automated Trading:** Trigger the Emergency Stop immediately to prevent further trades based on bad state.
2. **Verify on Kite:** Log in to [Kite Web UI](https://kite.zerodha.com) and navigate to your "Positions" and "Orders" pages. This is the ultimate source of truth.
3. **Square Off Manually:** If there are unintended open positions, exit them directly through the Kite Web UI.
4. **Reset Local State:** 
   If the local database (`trading_agent.db`) is completely out of sync and cannot recover, you can stop the server, back up the database, and clear the state:
   ```bash
   mv trading_agent.db trading_agent.db.bak
   # The application will recreate the database on next startup
   ```
5. **Restart and Re-authenticate:** Start the server again and authenticate to begin with a clean slate.
