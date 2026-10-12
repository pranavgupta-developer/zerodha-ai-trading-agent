import pytest
from app.trading.position_sizer import DynamicPositionSizer, PositionSizerConfig

def test_fixed_fractional_risk_sizing():
    sizer = DynamicPositionSizer(PositionSizerConfig(risk_per_trade_pct=0.01))
    
    # Capital = 500,000 -> 1% Risk Budget = 5,000
    # Entry = 1000, Stop Loss = 980 -> SL Distance = 20
    # Raw Qty = 5,000 / 20 = 250 shares
    # 250 * 1000 = 250,000 > 20% cap (100,000) -> Cap Qty = 100 shares
    res = sizer.calculate_allocation(
        symbol="TEST",
        entry_price=1000.0,
        stop_loss=980.0,
        account_equity=500000.0,
        confidence=1.0
    )
    
    assert res.quantity == 100
    assert res.allocated_capital == 100000.0
    assert res.capital_allocation_pct == 20.0
    assert res.risk_budget == 2000.0 # 100 * 20
    assert res.sl_distance == 20.0

def test_volatility_scaling_tighter_vs_wider_sl():
    sizer = DynamicPositionSizer(PositionSizerConfig(
        risk_per_trade_pct=0.01,
        max_position_capital_pct=0.50 # Higher cap to observe pure volatility sizing
    ))
    
    # Tighter SL: Entry 100, SL 98 (Distance = 2) -> 5,000 / 2 = 2,500 -> capped by max_qty_per_order (500)
    tight_res = sizer.calculate_allocation(
        symbol="TIGHT",
        entry_price=100.0,
        stop_loss=98.0,
        account_equity=500000.0
    )
    
    # Wider SL: Entry 100, SL 80 (Distance = 20) -> 5,000 / 20 = 250
    wide_res = sizer.calculate_allocation(
        symbol="WIDE",
        entry_price=100.0,
        stop_loss=80.0,
        account_equity=500000.0
    )
    
    assert tight_res.quantity > wide_res.quantity
    assert wide_res.quantity == 250

def test_high_price_vs_low_price_normalization():
    sizer = DynamicPositionSizer(PositionSizerConfig(risk_per_trade_pct=0.01))
    
    # Cheap stock (₹150, SL ₹145 -> dist 5)
    cheap_res = sizer.calculate_allocation(
        symbol="CHEAP",
        entry_price=150.0,
        stop_loss=145.0,
        account_equity=500000.0
    )
    
    # Expensive stock (₹3000, SL ₹2900 -> dist 100)
    expensive_res = sizer.calculate_allocation(
        symbol="EXPENSIVE",
        entry_price=3000.0,
        stop_loss=2900.0,
        account_equity=500000.0
    )
    
    # Both respect risk budget and capital caps
    assert cheap_res.quantity > expensive_res.quantity
    assert expensive_res.quantity >= 1
    assert expensive_res.allocated_capital <= 100000.0

def test_margin_and_capital_cap():
    sizer = DynamicPositionSizer(PositionSizerConfig(
        max_position_capital_pct=0.10 # Max 10%
    ))
    
    # Capital = 100,000. Max capital = 10,000.
    # Entry = 500 -> Max qty = 20 shares.
    res = sizer.calculate_allocation(
        symbol="CAP",
        entry_price=500.0,
        stop_loss=499.0, # Tiny SL would give huge raw qty
        account_equity=100000.0
    )
    
    assert res.quantity == 20
    assert res.allocated_capital == 10000.0

def test_minimum_quantity_floor():
    sizer = DynamicPositionSizer()
    
    # Very small equity (e.g. 1000)
    res = sizer.calculate_allocation(
        symbol="MIN",
        entry_price=5000.0,
        stop_loss=4000.0,
        account_equity=1000.0
    )
    
    assert res.quantity == 1

def test_confidence_scaling():
    sizer = DynamicPositionSizer(PositionSizerConfig(confidence_scaling=True, max_position_capital_pct=0.5))
    
    high_conf = sizer.calculate_allocation(
        symbol="HIGH",
        entry_price=100.0,
        stop_loss=90.0,
        account_equity=500000.0,
        confidence=1.0 # 1.0x
    )
    
    low_conf = sizer.calculate_allocation(
        symbol="LOW",
        entry_price=100.0,
        stop_loss=90.0,
        account_equity=500000.0,
        confidence=0.2 # 0.6x
    )
    
    assert high_conf.quantity > low_conf.quantity
    assert high_conf.confidence_multiplier == 1.0
    assert low_conf.confidence_multiplier == 0.6

def test_zero_or_invalid_stop_loss_fallback():
    sizer = DynamicPositionSizer()
    
    # Zero stop loss with ATR provided
    res = sizer.calculate_allocation(
        symbol="NO_SL",
        entry_price=200.0,
        stop_loss=0.0,
        account_equity=100000.0,
        atr=5.0
    )
    
    # Fallback to ATR * 1.5 = 7.5 distance
    assert res.sl_distance == 7.5
    assert res.quantity > 0
