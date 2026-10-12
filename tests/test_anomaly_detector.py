import pytest
from app.security.anomaly_detector import AnomalyDetector

def test_anomaly_detector_normal_behavior():
    detector = AnomalyDetector()
    
    # 2 orders/min, 5% of portfolio, 15% concentration, 85% confidence, 200ms lag
    result = detector.evaluate(
        orders_per_minute=2,
        order_value_pct=0.05,
        concentration_pct=0.15,
        ai_confidence=0.85,
        data_lag_ms=200
    )
    
    assert not result["is_anomaly"]
    assert not result["halt_trading"]
    
def test_anomaly_detector_abnormal_frequency():
    detector = AnomalyDetector()
    
    # Multiple abnormal vectors
    result = detector.evaluate(
        orders_per_minute=50,
        order_value_pct=0.50,
        concentration_pct=0.95,
        ai_confidence=0.10,
        data_lag_ms=5000
    )
    
    assert result["is_anomaly"]
    assert result["halt_trading"]

def test_anomaly_detector_abnormal_size_and_lag():
    detector = AnomalyDetector()
    
    # Order value is 80% of portfolio (fat finger error), lag is 10 seconds (10000ms)
    result = detector.evaluate(
        orders_per_minute=1,
        order_value_pct=0.80,
        concentration_pct=0.15,
        ai_confidence=0.85,
        data_lag_ms=10000
    )
    
    assert result["is_anomaly"]
    assert result["halt_trading"]
