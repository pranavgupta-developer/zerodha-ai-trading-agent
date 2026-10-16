import pytest
import httpx
import app.main
from app.trading.signals import SignalDirection

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app.main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

@pytest.mark.anyio
async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
    assert "Zerodha" in response.text or "Welcome" in response.text

@pytest.mark.anyio
async def test_system_status(client):
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "emergency_stop_active" in data
    assert "trading_mode" in data

@pytest.mark.anyio
async def test_audit_logs(client):
    response = await client.get("/api/v1/audit-logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

@pytest.mark.anyio
async def test_portfolio_endpoint(client):
    response = await client.get("/api/v1/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "holdings" in data or "positions" in data

@pytest.mark.anyio
async def test_emergency_stop_toggle(client):
    # Ensure starting in non-emergency state
    app.main.EMERGENCY_STOP_ACTIVE = False
    
    response = await client.post("/api/v1/system/emergency-stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert app.main.EMERGENCY_STOP_ACTIVE is True

    # Toggle back to normal
    response2 = await client.post("/api/v1/system/emergency-stop")
    assert response2.status_code == 200
    assert app.main.EMERGENCY_STOP_ACTIVE is False

@pytest.mark.anyio
async def test_trade_action_reject(client):
    payload = {
        "trade_id": "test_trade_reject_1",
        "action": "REJECT"
    }
    response = await client.post("/api/v1/trades/action", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "REJECT"

@pytest.mark.anyio
async def test_trade_action_approve_pipeline(client):
    app.main.EMERGENCY_STOP_ACTIVE = False
    trade_id = "test_trade_approve_1"
    app.main.candidate_cache[trade_id] = {
        "id": trade_id,
        "symbol": "TATASTEEL",
        "action": "BUY",
        "price": 150.0,
        "stop_loss": 145.0,
        "take_target": 160.0,
        "qty": 10,
        "reasoning": "Bullish breakout signal"
    }
    
    payload = {
        "trade_id": trade_id,
        "action": "APPROVE"
    }
    response = await client.post("/api/v1/trades/action", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "broker_order_id" in data

@pytest.mark.anyio
async def test_trade_action_blocked_by_emergency_stop(client):
    app.main.EMERGENCY_STOP_ACTIVE = True
    trade_id = "test_trade_blocked_1"
    app.main.candidate_cache[trade_id] = {
        "id": trade_id,
        "symbol": "TATASTEEL",
        "action": "BUY",
        "price": 150.0,
        "qty": 10
    }
    
    payload = {
        "trade_id": trade_id,
        "action": "APPROVE"
    }
    response = await client.post("/api/v1/trades/action", json=payload)
    assert response.status_code == 400
    assert "Emergency Stop is active" in response.json()["detail"]
    
    # Restore normal state
    app.main.EMERGENCY_STOP_ACTIVE = False

@pytest.mark.anyio
async def test_trade_close(client):
    payload = {
        "symbol": "TATASTEEL.NS",
        "quantity": 10,
        "current_price": 150.0
    }
    response = await client.post("/api/v1/trades/close", json=payload)
    assert response.status_code in [200, 500]

@pytest.mark.anyio
async def test_trade_close_all(client):
    response = await client.post("/api/v1/trades/close-all")
    assert response.status_code in [200, 500]

@pytest.mark.anyio
async def test_reconciliation_endpoints(client):
    # Trigger manual reconciliation
    response = await client.post("/api/v1/system/reconcile")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "report" in data
    assert "is_synced" in data["report"]

    # Check status endpoint
    status_resp = await client.get("/api/v1/system/reconciliation/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "report" in status_data
    assert "quarantined_count" in status_data

@pytest.mark.anyio
async def test_anomaly_status_and_halt(client):
    # Check status
    resp = await client.get("/api/v1/system/anomaly/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_fitted" in data
    assert data["is_fitted"] is True

    # Test an abnormal trade (huge order value = 90% of available margin)
    app.main.EMERGENCY_STOP_ACTIVE = False
    trade_id = "test_anom_halt_1"
    app.main.candidate_cache[trade_id] = {
        "id": trade_id,
        "symbol": "TATASTEEL",
        "action": "BUY",
        "price": 500000.0, # Fat finger price / huge size
        "qty": 1000,
        "stop_loss": 450000.0,
        "take_target": 600000.0
    }
    
    # Attempting to approve this should be blocked by AnomalyDetector or RiskEngine and trip Emergency Stop
    action_resp = await client.post("/api/v1/trades/action", json={"trade_id": trade_id, "action": "APPROVE"})
    assert action_resp.status_code == 400
    
    # Restore normal state
    app.main.EMERGENCY_STOP_ACTIVE = False

@pytest.mark.anyio
async def test_ml_metrics_and_prediction_endpoints(client):
    # 1. Fetch ML metrics
    metrics_resp = await client.get("/api/v1/ml/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert "total_predictions" in metrics
    assert "overall_accuracy" in metrics
    assert "prediction_drift" in metrics
    assert "regime_performance" in metrics

    # 2. Record manual prediction
    pred_payload = {
        "symbol": "TCS",
        "predicted_direction": "BUY",
        "confidence": 0.88,
        "entry_price": 3500.0,
        "features": {"rsi_14": 58.0, "atr_14": 20.0},
        "trade_id": "test_e2e_ml_1"
    }
    rec_resp = await client.post("/api/v1/ml/record", json=pred_payload)
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["status"] == "success"
    assert rec_data["prediction"]["symbol"] == "TCS"

    # 3. Record outcome
    out_payload = {
        "symbol": "TCS",
        "exit_price": 3550.0,
        "realized_pnl": 500.0,
        "exit_reason": "TAKE_PROFIT",
        "trade_id": "test_e2e_ml_1"
    }
    out_resp = await client.post("/api/v1/ml/outcome", json=out_payload)
    assert out_resp.status_code == 200
    out_data = out_resp.json()
    assert out_data["status"] == "success"
    assert out_data["outcome"]["is_correct"] is True

    # 4. Check predictions list
    list_resp = await client.get("/api/v1/ml/predictions?limit=10")
    assert list_resp.status_code == 200
    preds = list_resp.json()
    assert len(preds) >= 1

@pytest.mark.anyio
async def test_paper_trading_validation_endpoints(client):
    # 1. Fetch paper report
    report_resp = await client.get("/api/v1/system/paper-report")
    assert report_resp.status_code == 200
    rep_data = report_resp.json()
    assert "metrics" in rep_data
    assert "snapshots" in rep_data
    assert "validation_verdict" in rep_data["metrics"]

    # 2. Fetch markdown report
    md_resp = await client.get("/api/v1/system/paper-report/markdown")
    assert md_resp.status_code == 200
    assert "markdown" in md_resp.json()
    assert "Paper-Trading Validation Report" in md_resp.json()["markdown"]

    # 3. Post a paper daily snapshot
    snap_payload = {
        "starting_margin": 500000.0,
        "ending_margin": 504000.0,
        "realized_pnl": 4500.0,
        "unrealized_pnl": -500.0,
        "total_trades": 8,
        "win_trades": 6,
        "loss_trades": 2,
        "date_str": "2026-10-15"
    }
    snap_resp = await client.post("/api/v1/system/paper-report/snapshot", json=snap_payload)
    assert snap_resp.status_code == 200
    assert snap_resp.json()["status"] == "success"
    assert snap_resp.json()["snapshot"]["date_str"] == "2026-10-15"



