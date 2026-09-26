import pytest
from app.utils.indicators import (
    calculate_sma, calculate_ema, calculate_rsi,
    calculate_macd, calculate_bollinger_bands, calculate_atr, calculate_vwap,
    get_feature_snapshot
)
from dataclasses import dataclass

def test_calculate_sma():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    
    # Period 3
    sma_3 = calculate_sma(prices, 3)
    assert sma_3[0] is None
    assert sma_3[1] is None
    assert sma_3[2] == 11.0 # (10+11+12)/3
    assert sma_3[3] == 12.0 # (11+12+13)/3
    assert sma_3[6] == 15.0 # (14+15+16)/3

    # Empty list
    assert calculate_sma([], 3) == []
    
    # Period greater than length
    sma_10 = calculate_sma(prices, 10)
    assert all(x is None for x in sma_10)

def test_calculate_ema():
    prices = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29]
    # For a 10-period EMA, we need at least 10 items.
    
    # Let's test a 5-period EMA
    ema_5 = calculate_ema(prices, 5)
    
    # First 4 should be None
    assert ema_5[0] is None
    assert ema_5[3] is None
    
    # 5th element (index 4) should be SMA of first 5
    # (22.27 + 22.19 + 22.08 + 22.17 + 22.18) / 5 = 22.178
    assert pytest.approx(ema_5[4], 0.001) == 22.178
    
    # 6th element (index 5) = (22.13 - 22.178) * (2/6) + 22.178 = 22.162
    assert pytest.approx(ema_5[5], 0.001) == 22.162
    
    # 7th element (index 6) = (22.23 - 22.162) * (2/6) + 22.162 = 22.1846
    assert pytest.approx(ema_5[6], 0.001) == 22.1846

def test_calculate_rsi():
    # Known RSI example sequence
    # From standard RSI calculations examples:
    # 14 days of close prices
    prices = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
        46.03, 46.41, 46.22, 45.64
    ]
    
    rsi = calculate_rsi(prices, 14)
    
    # First 14 elements (indices 0 to 13) are None since we need 14 periods of gains/losses
    # Wait, period is 14, which means we need 15 price points (to get 14 differences)
    assert rsi[13] is None
    
    # At index 14 (15th price point):
    # This is standard Wilder's RSI calculation:
    # First RSI is approximately 70.53
    assert pytest.approx(rsi[14], 0.1) == 70.53
    
    # Index 15: approximately 66.32
    assert pytest.approx(rsi[15], 0.1) == 66.32
    
    # Index 16: approximately 66.55
    assert pytest.approx(rsi[16], 0.1) == 66.55
    
    # Index 17: approximately 69.41
    assert pytest.approx(rsi[17], 0.1) == 69.41
    
    # Index 18: approximately 66.36
    assert pytest.approx(rsi[18], 0.1) == 66.36
    
    # Index 19: approximately 57.97
    assert pytest.approx(rsi[19], 0.1) == 57.97

def test_calculate_macd():
    prices = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29] * 3
    macd_line, signal_line, histogram = calculate_macd(prices, fast_period=3, slow_period=6, signal_period=3)
    
    # Check length
    assert len(macd_line) == len(prices)
    assert len(signal_line) == len(prices)
    assert len(histogram) == len(prices)
    
    # Later values shouldn't be None
    assert macd_line[-1] is not None
    assert signal_line[-1] is not None
    assert histogram[-1] is not None
    
    # histogram should equal macd - signal
    assert pytest.approx(histogram[-1], 0.0001) == macd_line[-1] - signal_line[-1]

def test_calculate_bollinger_bands():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    mid, upper, lower = calculate_bollinger_bands(prices, period=3, num_std=2.0)
    
    assert len(mid) == 5
    assert mid[0] is None
    
    # For index 2 (10, 11, 12)
    # mean = 11, variance = (1+0+1)/3 = 0.666..., stddev = 0.816...
    assert pytest.approx(mid[2], 0.001) == 11.0 # type: ignore
    assert upper[2] > mid[2] # type: ignore
    assert lower[2] < mid[2] # type: ignore

def test_calculate_atr():
    highs = [15.0, 16.0, 17.0, 18.0]
    lows = [10.0, 11.0, 12.0, 13.0]
    closes = [12.0, 13.0, 14.0, 15.0]
    
    atr = calculate_atr(highs, lows, closes, period=3)
    assert atr[0] is None
    
    # 3 periods: index 0 to 2
    # tr[0]: 15-10 = 5
    # tr[1]: max(16-11=5, 16-12=4, 11-12=1) = 5
    # tr[2]: max(17-12=5, 17-13=4, 12-13=1) = 5
    # ATR period=3, index 2 = (5+5+5)/3 = 5
    assert pytest.approx(atr[2], 0.01) == 5.0
    
    # index 3
    # tr[3]: max(18-13=5, 18-14=4, 13-14=1) = 5
    # ATR[3] = (5 * 2 + 5) / 3 = 5
    assert pytest.approx(atr[3], 0.01) == 5.0

def test_calculate_vwap():
    highs = [10.0, 12.0]
    lows = [8.0, 10.0]
    closes = [9.0, 11.0]
    volumes = [100.0, 200.0]
    
    vwap = calculate_vwap(highs, lows, closes, volumes)
    
    # index 0: typical = (10+8+9)/3 = 9. vwap = 9 * 100 / 100 = 9
    assert pytest.approx(vwap[0], 0.01) == 9.0
    
    # index 1: typical = (12+10+11)/3 = 11. vwap = (9*100 + 11*200) / 300 = 3100/300 = 10.333
    assert pytest.approx(vwap[1], 0.01) == 10.333

def test_get_feature_snapshot():
    @dataclass
    class MockCandle:
        close: float
        high: float
        low: float
        volume: int
        
    candles = [
        MockCandle(close=10.0, high=12.0, low=8.0, volume=100)
        for _ in range(30)
    ]
    
    snapshot = get_feature_snapshot(candles)
    
    assert "price" in snapshot
    assert snapshot["price"] == 10.0
    assert snapshot["sma_20"] == 10.0
    assert snapshot["macd"] == 0.0 # flat price means no difference in EMAs
    assert snapshot["vwap"] == 10.0 # typical price is (12+8+10)/3 = 10
