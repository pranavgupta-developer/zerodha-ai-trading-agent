import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.broker.candle_aggregator import CandleAggregator

IST = ZoneInfo("Asia/Kolkata")

@pytest.fixture
def aggregator():
    return CandleAggregator()

@patch("app.broker.candle_aggregator.datetime")
@patch("app.broker.candle_aggregator.SessionLocal")
def test_process_ticks_same_minute(mock_session_local, mock_datetime, aggregator):
    # Setup mock datetime
    mock_now = datetime(2026, 1, 1, 9, 15, 10, tzinfo=IST)
    mock_datetime.now.return_value = mock_now
    
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    # First tick
    ticks = [{"instrument_token": 123, "last_price": 100.0, "last_traded_quantity": 10}]
    aggregator.process_ticks(ticks)

    assert 123 in aggregator.current_candles
    candle = aggregator.current_candles[123]
    assert candle["open"] == 100.0
    assert candle["high"] == 100.0
    assert candle["low"] == 100.0
    assert candle["close"] == 100.0
    assert candle["volume"] == 10

    # Second tick in same minute
    mock_now = datetime(2026, 1, 1, 9, 15, 45, tzinfo=IST)
    mock_datetime.now.return_value = mock_now

    ticks = [{"instrument_token": 123, "last_price": 105.0, "last_traded_quantity": 20}]
    aggregator.process_ticks(ticks)

    candle = aggregator.current_candles[123]
    assert candle["open"] == 100.0
    assert candle["high"] == 105.0
    assert candle["low"] == 100.0
    assert candle["close"] == 105.0
    assert candle["volume"] == 30
    
    # Ensure no candles were persisted yet
    mock_db.bulk_save_objects.assert_not_called()

@patch("app.broker.candle_aggregator.datetime")
@patch("app.broker.candle_aggregator.SessionLocal")
def test_process_ticks_minute_rollover(mock_session_local, mock_datetime, aggregator):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    # Tick at 9:15:50
    mock_datetime.now.return_value = datetime(2026, 1, 1, 9, 15, 50, tzinfo=IST)
    aggregator.process_ticks([{"instrument_token": 123, "last_price": 100.0, "last_traded_quantity": 10}])
    
    # Tick at 9:16:10
    mock_datetime.now.return_value = datetime(2026, 1, 1, 9, 16, 10, tzinfo=IST)
    aggregator.process_ticks([{"instrument_token": 123, "last_price": 95.0, "last_traded_quantity": 15}])

    # 9:15 candle should have been flushed
    assert mock_db.bulk_save_objects.call_count == 1
    
    # Inspect saved objects
    saved_candles = mock_db.bulk_save_objects.call_args[0][0]
    assert len(saved_candles) == 1
    saved = saved_candles[0]
    
    assert saved.instrument_token == 123
    assert saved.open == 100.0
    assert saved.high == 100.0
    assert saved.low == 100.0
    assert saved.close == 100.0
    assert saved.volume == 10
    
    # The new 9:16 candle is currently building
    candle = aggregator.current_candles[123]
    assert candle["open"] == 95.0
    assert candle["close"] == 95.0
    assert candle["volume"] == 15
