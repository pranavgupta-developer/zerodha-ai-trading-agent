import math
from typing import List, Optional, Tuple, Dict, Any

def calculate_sma(prices: List[float], period: int) -> List[Optional[float]]:
    """
    Calculates Simple Moving Average (SMA).
    Returns a list of the same length as `prices`.
    Values before `period` are None.
    """
    if not prices or period <= 0:
        return [None] * len(prices)
        
    result: List[Optional[float]] = [None] * len(prices)
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        result[i] = sum(window) / period
        
    return result

def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
    """
    Calculates Exponential Moving Average (EMA) using Wilder's smoothing.
    The first EMA value is initialized using the SMA of the first `period` elements.
    """
    if not prices or period <= 0 or len(prices) < period:
        return [None] * len(prices)
        
    result: List[Optional[float]] = [None] * len(prices)
    
    # Initialize first EMA with SMA
    initial_sma = sum(prices[:period]) / period
    result[period - 1] = initial_sma
    
    multiplier = 2 / (period + 1)
    
    for i in range(period, len(prices)):
        if result[i - 1] is not None:
            result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1] # type: ignore
        
    return result

def calculate_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    """
    Calculates the Relative Strength Index (RSI).
    Uses Wilder's smoothing method.
    """
    if not prices or period <= 0 or len(prices) <= period:
        return [None] * len(prices)
        
    result: List[Optional[float]] = [None] * len(prices)
    
    # Calculate initial changes
    gains = []
    losses = []
    
    for i in range(1, period + 1):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
            
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        rs = float('inf')
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
        
    for i in range(period + 1, len(prices)):
        change = prices[i] - prices[i - 1]
        gain = change if change > 0 else 0
        loss = abs(change) if change < 0 else 0
        
        # Wilder's smoothing
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
            
    return result

def calculate_macd(prices: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Calculates MACD Line, Signal Line, and Histogram."""
    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)
    
    macd_line: List[Optional[float]] = [None] * len(prices)
    for i in range(len(prices)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i] # type: ignore
            
    valid_macd = [x for x in macd_line if x is not None]
    if len(valid_macd) < signal_period:
        return macd_line, [None]*len(prices), [None]*len(prices)
        
    signal_line_valid = calculate_ema(valid_macd, signal_period)
    none_count = len(prices) - len(valid_macd)
    signal_line: List[Optional[float]] = [None] * none_count + signal_line_valid
    
    histogram: List[Optional[float]] = [None] * len(prices)
    for i in range(len(prices)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i] # type: ignore
            
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Calculates Bollinger Bands (Mid, Upper, Lower)."""
    sma = calculate_sma(prices, period)
    upper: List[Optional[float]] = [None] * len(prices)
    lower: List[Optional[float]] = [None] * len(prices)
    
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        mean = sma[i]
        if mean is not None:
            variance = sum((x - mean) ** 2 for x in window) / period
            std_dev = math.sqrt(variance)
            upper[i] = mean + (num_std * std_dev)
            lower[i] = mean - (num_std * std_dev)
        
    return sma, upper, lower

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculates Average True Range (ATR)."""
    if not highs or len(highs) <= period:
        return [None] * len(highs)
        
    true_ranges = [0.0] * len(highs)
    true_ranges[0] = highs[0] - lows[0]
    
    for i in range(1, len(highs)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i-1])
        tr3 = abs(lows[i] - closes[i-1])
        true_ranges[i] = max(tr1, tr2, tr3)
        
    result: List[Optional[float]] = [None] * len(highs)
    
    initial_atr = sum(true_ranges[:period]) / period
    result[period - 1] = initial_atr
    
    for i in range(period, len(highs)):
        if result[i-1] is not None:
            result[i] = (result[i-1] * (period - 1) + true_ranges[i]) / period # type: ignore
        
    return result

def calculate_vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> List[Optional[float]]:
    """Calculates cumulative VWAP."""
    result: List[Optional[float]] = [None] * len(highs)
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    
    for i in range(len(highs)):
        typical_price = (highs[i] + lows[i] + closes[i]) / 3
        vol = volumes[i]
        
        cumulative_pv += (typical_price * vol)
        cumulative_vol += vol
        
        if cumulative_vol > 0:
            result[i] = cumulative_pv / cumulative_vol
            
    return result

def get_feature_snapshot(candles: List[Any]) -> Dict[str, Optional[float]]:
    """
    Given a list of recent Candle objects, calculates indicators and returns latest values.
    Assumes candles have: close, high, low, volume attributes.
    """
    if not candles:
        return {}
        
    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    volumes = [float(c.volume) for c in candles]
    
    sma_20 = calculate_sma(closes, 20)
    ema_20 = calculate_ema(closes, 20)
    rsi_14 = calculate_rsi(closes, 14)
    macd_line, macd_signal, macd_hist = calculate_macd(closes)
    bb_mid, bb_upper, bb_lower = calculate_bollinger_bands(closes)
    atr_14 = calculate_atr(highs, lows, closes)
    vwap = calculate_vwap(highs, lows, closes, volumes)
    
    return {
        "price": closes[-1],
        "sma_20": sma_20[-1] if sma_20 else None,
        "ema_20": ema_20[-1] if ema_20 else None,
        "rsi_14": rsi_14[-1] if rsi_14 else None,
        "macd": macd_line[-1] if macd_line else None,
        "macd_signal": macd_signal[-1] if macd_signal else None,
        "macd_hist": macd_hist[-1] if macd_hist else None,
        "bb_upper": bb_upper[-1] if bb_upper else None,
        "bb_lower": bb_lower[-1] if bb_lower else None,
        "bb_mid": bb_mid[-1] if bb_mid else None,
        "atr_14": atr_14[-1] if atr_14 else None,
        "vwap": vwap[-1] if vwap else None,
    }
