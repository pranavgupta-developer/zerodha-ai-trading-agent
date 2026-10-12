import pytest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from app.broker.market_status import get_market_status, is_market_holiday
from app.broker.candle_aggregator import CandleAggregator

IST = ZoneInfo("Asia/Kolkata")

def test_market_holidays():
    assert is_market_holiday(date(2026, 1, 26)) == True
    assert is_market_holiday(date(2026, 1, 27)) == False

def test_market_status_weekends():
    # 2026-09-26 is a Saturday
    saturday = datetime(2026, 9, 26, 10, 0, tzinfo=IST)
    with patch('app.broker.market_status.datetime') as mock_dt:
        mock_dt.now.return_value = saturday
        assert get_market_status() == "CLOSED"

def test_market_status_hours():
    # Thursday, 9:00 AM (Before open)
    before_open = datetime(2026, 9, 24, 9, 0, tzinfo=IST)
    with patch('app.broker.market_status.datetime') as mock_dt:
        mock_dt.now.return_value = before_open
        assert get_market_status() == "CLOSED"
        
    # Thursday, 9:20 AM (Open)
    during_open = datetime(2026, 9, 24, 9, 20, tzinfo=IST)
    with patch('app.broker.market_status.datetime') as mock_dt:
        mock_dt.now.return_value = during_open
        assert get_market_status() == "OPEN"
        
    # Thursday, 4:00 PM (After close)
    after_close = datetime(2026, 9, 24, 16, 0, tzinfo=IST)
    with patch('app.broker.market_status.datetime') as mock_dt:
        mock_dt.now.return_value = after_close
        assert get_market_status() == "CLOSED"

def test_market_status_stale():
    # Thursday, 9:20 AM (Open)
    now_time = datetime(2026, 9, 24, 9, 20, tzinfo=IST)
    with patch('app.broker.market_status.datetime') as mock_dt:
        mock_dt.now.return_value = now_time
        
        # 10 minutes ago
        stale_tick = now_time - timedelta(minutes=10)
        assert get_market_status(latest_tick_time=stale_tick) == "STALE"
        
        # 1 minute ago
        fresh_tick = now_time - timedelta(minutes=1)
        assert get_market_status(latest_tick_time=fresh_tick) == "HEALTHY"

@patch('app.broker.candle_aggregator.SessionLocal')
def test_candle_aggregator(mock_session):
    
    agg = CandleAggregator()
    ticks = [
        {'instrument_token': 123, 'last_price': 100.0, 'last_traded_quantity': 5},
        {'instrument_token': 123, 'last_price': 102.0, 'last_traded_quantity': 10}
    ]
    
    agg.process_ticks(ticks)
    
    # Check 1m, 5m, 15m initialization
    assert 123 in agg.current_candles['1m']
    assert 123 in agg.current_candles['5m']
    assert 123 in agg.current_candles['15m']
    
    # Volume accumulation should be 15
    assert agg.current_candles['1m'][123]['volume'] == 15
    assert agg.current_candles['1m'][123]['high'] == 102.0
