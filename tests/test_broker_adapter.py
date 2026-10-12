import pytest
from unittest.mock import MagicMock, patch
from app.broker.kite_adapter import BrokerAdapter
import kiteconnect.exceptions as kite_exc

@pytest.fixture
def mock_kite():
    with patch("app.broker.kite_adapter.KiteConnect") as mock_kc:
        # Create a mock instance
        mock_instance = MagicMock()
        mock_kc.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def broker(mock_kite):
    return BrokerAdapter()

def test_get_login_url(broker, mock_kite):
    mock_kite.login_url.return_value = "http://kite.test/login"
    url = broker.get_login_url()
    assert url == "http://kite.test/login"
    mock_kite.login_url.assert_called_once()

def test_generate_session_success(broker, mock_kite):
    mock_session_data = {"access_token": "fake_token", "public_token": "fake_public"}
    mock_kite.generate_session.return_value = mock_session_data
    
    session = broker.generate_session("request_token_123")
    
    assert session == mock_session_data
    assert broker._access_token == "fake_token"
    mock_kite.generate_session.assert_called_once_with(
        request_token="request_token_123",
        api_secret=broker.api_secret
    )
    mock_kite.set_access_token.assert_any_call("fake_token")

def test_generate_session_failure(broker, mock_kite):
    mock_kite.generate_session.side_effect = kite_exc.TokenException("Invalid token")
    
    with pytest.raises(kite_exc.TokenException):
        broker.generate_session("bad_token")

def test_get_profile_unauthenticated(broker):
    broker._access_token = None
    with pytest.raises(ValueError, match="Access token is not set"):
        broker.get_profile()

def test_get_profile_success(broker, mock_kite):
    broker.set_access_token("valid_token")
    mock_kite.profile.return_value = {"user_name": "Test User"}
    
    profile = broker.get_profile()
    assert profile["user_name"] == "Test User"
    mock_kite.profile.assert_called_once()

def test_get_margins_success(broker, mock_kite):
    broker.set_access_token("valid_token")
    mock_kite.margins.return_value = {"equity": {"net": 1000}}
    
    margins = broker.get_margins()
    assert margins["equity"]["net"] == 1000
    mock_kite.margins.assert_called_once()
