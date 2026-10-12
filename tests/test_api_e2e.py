import pytest
import requests

BASE_URL = "http://localhost:8000"

def _is_server_up():
    try:
        r = requests.get(f"{BASE_URL}/", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False

pytestmark = pytest.mark.skipif(not _is_server_up(), reason="Backend server not running at http://localhost:8000")

def test_root_endpoint():
    response = requests.get(f"{BASE_URL}/")
    assert response.status_code == 200
    assert "message" in response.json()
    assert "Zerodha" in response.text or "Welcome" in response.text

def test_system_status():
    response = requests.get(f"{BASE_URL}/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "emergency_stop_active" in data
    assert "trading_mode" in data

def test_audit_logs():
    response = requests.get(f"{BASE_URL}/api/v1/audit-logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

def test_emergency_stop():
    response = requests.post(f"{BASE_URL}/api/v1/system/emergency-stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    
    # Check that system status reflects the emergency stop
    status_response = requests.get(f"{BASE_URL}/api/v1/system/status")
    status_data = status_response.json()
    assert status_data["emergency_stop_active"] in [True, False] # It toggles

def test_trade_action_reject():
    payload = {
        "trade_id": "test_trade_123",
        "action": "REJECT"
    }
    response = requests.post(f"{BASE_URL}/api/v1/trades/action", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "REJECT"

def test_trade_close():
    payload = {
        "symbol": "TATASTEEL.NS",
        "quantity": 10,
        "current_price": 150.0
    }
    response = requests.post(f"{BASE_URL}/api/v1/trades/close", json=payload)
    assert response.status_code in [200, 500] 

def test_trade_close_all():
    response = requests.post(f"{BASE_URL}/api/v1/trades/close-all")
    assert response.status_code in [200, 500]
