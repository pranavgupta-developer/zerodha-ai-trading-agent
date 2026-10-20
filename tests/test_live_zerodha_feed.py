import pytest
from unittest.mock import MagicMock, patch
import app.main as main_module
from app.broker.kite_adapter import BrokerAdapter

def test_no_mock_default_base_prices():
    """Verify DEFAULT_BASE_PRICES and DEFAULT_PREV_CLOSES have been eliminated."""
    assert not hasattr(main_module, "DEFAULT_BASE_PRICES"), "DEFAULT_BASE_PRICES mock dictionary should not exist"
    assert not hasattr(main_module, "DEFAULT_PREV_CLOSES"), "DEFAULT_PREV_CLOSES mock dictionary should not exist"

def test_watchlist_initial_state_not_simulated():
    """Ensure watchlist items start awaiting real live feed without simulated numbers."""
    watchlist = main_module.current_watchlist_payload
    assert len(watchlist) > 0
    for item in watchlist:
        assert "symbol" in item
        assert item["status"] in ["WAITING_FOR_ZERODHA_FEED", "ZERODHA_LIVE", "ZERODHA_AUTH_REQUIRED"]
        assert item["signal"] == "HOLD"

def test_broker_authentication_ttl_cache():
    """Verify is_authenticated uses TTL caching to prevent rate-limit spam."""
    with patch("app.broker.kite_adapter.KiteConnect") as mock_kc:
        mock_instance = MagicMock()
        mock_kc.return_value = mock_instance
        broker = BrokerAdapter()
        
        # Unauthenticated initially without token
        broker._access_token = None
        assert not broker.is_authenticated()
        
        # Set token and verify profile is called
        broker.set_access_token("real_test_token")
        mock_instance.profile.return_value = {"user_name": "Trader"}
        
        # First call hits profile
        assert broker.is_authenticated(force_check=True) is True
        assert mock_instance.profile.call_count == 1
        
        # Second call within 60s uses cache
        assert broker.is_authenticated() is True
        assert mock_instance.profile.call_count == 1

def test_broker_get_quote_returns_real_dict():
    """Verify get_quote calls Kite API when authenticated."""
    with patch("app.broker.kite_adapter.KiteConnect") as mock_kc:
        mock_instance = MagicMock()
        mock_kc.return_value = mock_instance
        broker = BrokerAdapter()
        broker.set_access_token("real_test_token")
        
        mock_quotes = {
            "NSE:RELIANCE": {"last_price": 2850.5, "instrument_token": 738561, "ohlc": {"close": 2840.0}}
        }
        mock_instance.quote.return_value = mock_quotes
        
        res = broker.get_quote(["NSE:RELIANCE"])
        assert res == mock_quotes
        mock_instance.quote.assert_called_once_with(["NSE:RELIANCE"])

def test_portfolio_payload_no_hardcoded_prices():
    """Verify build_portfolio_payload runs cleanly without hardcoded base prices."""
    payload = main_module.build_portfolio_payload()
    assert payload["type"] == "market_update"
    assert "watchlist" in payload
    assert "positions" in payload
    assert "account_stats" in payload
