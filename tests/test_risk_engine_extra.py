import pytest
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.signals import Signal, SignalDirection

def test_max_open_positions():
    config = RiskConfig(max_open_positions=2)
    engine = RiskEngine(config)
    
    account = AccountState(
        available_margin=1000000,
        open_positions={"RELIANCE": 1000, "INFY": 1000}
    )
    
    # Trying to buy a new stock
    sig = Signal(symbol="TCS", direction=SignalDirection.BUY, entry_price=100, timestamp="2023")
    approved, reason = engine.validate_signal(sig, account, 10)
    assert not approved
    assert "Max open positions (2) reached" in reason
    
    # Trying to buy more of an existing stock
    sig_exist = Signal(symbol="RELIANCE", direction=SignalDirection.BUY, entry_price=100, timestamp="2023")
    approved, reason = engine.validate_signal(sig_exist, account, 10)
    assert approved
    
def test_max_drawdown():
    config = RiskConfig(max_drawdown_pct=0.05)
    engine = RiskEngine(config)
    
    # Peak margin was 100,000. Current equity is 90,000 (10% drawdown)
    account = AccountState(
        available_margin=90000,
        peak_margin=100000,
        realized_pnl=0,
        unrealized_pnl=0
    )
    
    sig = Signal(symbol="TCS", direction=SignalDirection.BUY, entry_price=100, timestamp="2023")
    approved, reason = engine.validate_signal(sig, account, 10)
    assert not approved
    assert "Max drawdown exceeded" in reason
