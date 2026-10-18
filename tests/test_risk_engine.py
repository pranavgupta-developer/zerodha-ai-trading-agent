import pytest
from unittest.mock import patch
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.signals import Signal, SignalDirection

@pytest.fixture
def base_signal():
    return Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        confidence=0.9,
        entry_price=100.0,
        stop_loss=90.0,
        take_target=120.0,
        reason="Test"
    )

@pytest.fixture
def base_account():
    return AccountState(
        available_margin=1000000.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions={},
        orders_placed_today=0,
        orders_placed_last_minute=0
    )

@pytest.fixture
def risk_engine():
    config = RiskConfig(
        max_order_value=10000.0,
        max_qty_per_order=100,
        max_orders_per_min=5,
        max_orders_per_day=50,
        max_position_size=50000.0,
        max_total_exposure=200000.0,
        max_daily_loss=1000.0,
        check_market_hours=False # Disabled by default for easier state tests
    )
    return RiskEngine(config)

# 1. Market Hours
@patch('app.trading.risk_engine.is_market_open')
def test_market_hours_pass(mock_is_market_open, risk_engine, base_signal, base_account):
    risk_engine.config.check_market_hours = True
    mock_is_market_open.return_value = True
    approved, _ = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is True

@patch('app.trading.risk_engine.is_market_open')
def test_market_hours_fail(mock_is_market_open, risk_engine, base_signal, base_account):
    risk_engine.config.check_market_hours = True
    mock_is_market_open.return_value = False
    approved, reason = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is False
    assert "Market is closed" in reason

# 2. Daily Loss Limit
def test_daily_loss_pass(risk_engine, base_signal, base_account):
    base_account.realized_pnl = -500.0
    base_account.unrealized_pnl = -499.0
    # Total = -999, which is > -1000 (pass)
    approved, _ = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is True

def test_daily_loss_fail(risk_engine, base_signal, base_account):
    base_account.realized_pnl = -500.0
    base_account.unrealized_pnl = -501.0
    # Total = -1001, which is <= -1000 (fail)
    approved, reason = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is False
    assert "Max daily loss exceeded" in reason

# 3. Order Rate Limits (Min)
def test_orders_per_min_pass(risk_engine, base_signal, base_account):
    base_account.orders_placed_last_minute = 4
    approved, _ = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is True

def test_orders_per_min_fail(risk_engine, base_signal, base_account):
    base_account.orders_placed_last_minute = 5
    approved, reason = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is False
    assert "minute exceeded" in reason

# 4. Order Rate Limits (Day)
def test_orders_per_day_pass(risk_engine, base_signal, base_account):
    base_account.orders_placed_today = 49
    approved, _ = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is True

def test_orders_per_day_fail(risk_engine, base_signal, base_account):
    base_account.orders_placed_today = 50
    approved, reason = risk_engine.validate_signal(base_signal, base_account, 50)
    assert approved is False
    assert "day exceeded" in reason

# 5. Max Quantity
def test_max_qty_pass(risk_engine, base_signal, base_account):
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=100)
    assert approved is True

def test_max_qty_fail(risk_engine, base_signal, base_account):
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=101)
    assert approved is False
    assert "exceeds max" in reason

# 6. Max Order Value
def test_max_order_value_pass(risk_engine, base_signal, base_account):
    # entry=100, qty=100 -> value 10000
    base_signal.entry_price = 100.0
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=100)
    assert approved is True

def test_max_order_value_fail(risk_engine, base_signal, base_account):
    # entry=100.01, qty=100 -> value 10001 (exceeds 10000)
    base_signal.entry_price = 100.01
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=100)
    assert approved is False
    assert "Order value" in reason

# 7. Margin Check
def test_margin_pass(risk_engine, base_signal, base_account):
    # value = 50 * 100 = 5000
    base_account.available_margin = 5000.0
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is True

def test_margin_fail(risk_engine, base_signal, base_account):
    # value = 50 * 100 = 5000
    base_account.available_margin = 4999.99
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is False
    assert "Insufficient margin" in reason

# 8. Max Position Size
def test_position_size_pass(risk_engine, base_signal, base_account):
    # entry=100, qty=50 -> value 5000
    # limit = 50000. existing = 45000. total = 50000.
    base_account.open_positions = {"RELIANCE": 45000.0}
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is True

def test_position_size_fail(risk_engine, base_signal, base_account):
    # limit = 50000. existing = 45001. total = 50001.
    base_account.open_positions = {"RELIANCE": 45001.0}
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is False
    assert "Max position size" in reason

# 9. Max Total Exposure
def test_total_exposure_pass(risk_engine, base_signal, base_account):
    # entry=100, qty=50 -> value 5000
    # limit = 200000. existing = 195000. total = 200000.
    base_account.open_positions = {"HDFC": 150000.0, "TCS": 45000.0}
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is True

def test_total_exposure_fail(risk_engine, base_signal, base_account):
    # limit = 200000. existing = 195001. total = 200001.
    base_account.open_positions = {"HDFC": 150000.0, "TCS": 45001.0}
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is False
    assert "Max total exposure" in reason

# 10. HOLD Signal handling
def test_hold_signal_fail(risk_engine, base_signal, base_account):
    base_signal.direction = SignalDirection.HOLD
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is False
    assert "HOLD" in reason

# 11. Sector Mapping & Concentration
def test_sector_mapping(risk_engine):
    assert risk_engine.get_sector("HDFCBANK") == "BANKING_FINANCIAL"
    assert risk_engine.get_sector("NSE:TCS") == "IT"
    assert risk_engine.get_sector("RELIANCE") == "ENERGY"
    assert risk_engine.get_sector("UNKNOWN_CORP") == "OTHER"

def test_sector_concentration_pass(risk_engine, base_signal, base_account):
    # RELIANCE is ENERGY. Max exposure = 200,000, 35% cap = 70,000.
    # Existing in ENERGY = 30,000. New order = 100 * 50 = 5,000. Total = 35,000 (17.5% <= 35%)
    base_account.open_positions = {"ONGC": 30000.0}
    approved, _ = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is True

def test_sector_concentration_breach(risk_engine, base_signal, base_account):
    # RELIANCE is ENERGY. Max exposure = 200,000, 35% cap = 70,000.
    # Existing in ENERGY = 68,000. New order = 100 * 50 = 5,000. Total = 73,000 (36.5% > 35%)
    base_account.open_positions = {"ONGC": 68000.0}
    approved, reason = risk_engine.validate_signal(base_signal, base_account, requested_qty=50)
    assert approved is False
    assert "SECTOR_CONCENTRATION_BREACH" in reason
    assert "ENERGY" in reason

def test_sector_breakdown(risk_engine, base_account):
    base_account.open_positions = {
        "HDFCBANK": 40000.0,
        "SBIN": 20000.0,
        "TCS": 30000.0,
        "RELIANCE": 25000.0
    }
    breakdown = risk_engine.get_sector_breakdown(base_account)
    assert breakdown["total_exposure"] == 115000.0
    assert "BANKING_FINANCIAL" in breakdown["sectors"]
    assert breakdown["sectors"]["BANKING_FINANCIAL"]["exposure"] == 60000.0
    assert "IT" in breakdown["sectors"]
    assert "ENERGY" in breakdown["sectors"]

# 12. Portfolio VaR / CVaR Enforcement
def test_portfolio_var_cvar_enforcement_pass(risk_engine, base_signal, base_account):
    import pandas as pd
    import numpy as np
    
    risk_engine.config.enforce_var_limits = True
    risk_engine.config.max_portfolio_var_pct = 0.10  # generous 10% limit
    
    # Mild volatility
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100)
    returns_df = pd.DataFrame({
        'RELIANCE': np.random.normal(0.0005, 0.005, 100)
    }, index=dates)
    
    approved, reason = risk_engine.validate_signal(
        base_signal, base_account, requested_qty=50, returns_data=returns_df
    )
    assert approved is True

def test_portfolio_var_cvar_enforcement_fail(risk_engine, base_signal, base_account):
    import pandas as pd
    import numpy as np
    
    risk_engine.config.enforce_var_limits = True
    risk_engine.config.max_portfolio_var_pct = 0.01  # very strict 1% limit
    
    # High volatility asset
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100)
    returns_df = pd.DataFrame({
        'RELIANCE': np.random.normal(-0.002, 0.04, 100)
    }, index=dates)
    
    approved, reason = risk_engine.validate_signal(
        base_signal, base_account, requested_qty=50, returns_data=returns_df
    )
    assert approved is False
    assert "VAR_LIMIT_BREACH" in reason

