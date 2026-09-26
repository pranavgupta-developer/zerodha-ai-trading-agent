import logging
import sys
import os

# Ensure the app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.broker.kite_adapter import BrokerAdapter
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.signals import Signal, SignalDirection
from app.core.config import settings
import kiteconnect.exceptions as kite_exc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_daily_loss_kill_switch():
    logger.info("--- Testing Daily Loss Kill-Switch Against Real Margin ---")
    
    # Force LIVE mode briefly to attempt fetching real margin
    original_mode = settings.TRADING_MODE
    settings.TRADING_MODE = "LIVE"
    
    broker = BrokerAdapter()
    real_margin = 0.0
    try:
        margin_data = broker.get_margins()
        real_margin = margin_data.get("equity", {}).get("available", {}).get("live_balance", 0.0) if margin_data else 0.0
        logger.info(f"Successfully fetched real account margin: ₹{real_margin}")
    except kite_exc.TokenException:
        logger.warning("No valid access token found. Falling back to a simulated real margin of ₹1,000,000 for the test.")
        real_margin = 1000000.0
    except ValueError:
        logger.warning("Access token is not set. Falling back to a simulated real margin of ₹1,000,000 for the test.")
        real_margin = 1000000.0
    except Exception as e:
        logger.error(f"Failed to fetch margin: {e}")
        real_margin = 1000000.0
    finally:
        # Restore mode
        settings.TRADING_MODE = original_mode

    # Configure RiskEngine
    # E.g., max 10k hard limit, or 2% of margin, whichever is lower.
    config = RiskConfig(
        max_daily_loss=10000.0,
        max_daily_loss_pct=0.02,
        check_market_hours=False  # Disable market hours check for test
    )
    engine = RiskEngine(config=config)
    
    # Create an AccountState with the "real" margin
    account = AccountState(
        available_margin=real_margin,
        unrealized_pnl=0.0,
        realized_pnl=0.0
    )
    
    # Calculate the expected dynamic limit
    dynamic_limit = min(config.max_daily_loss, real_margin * config.max_daily_loss_pct)
    logger.info(f"Calculated Dynamic Kill-Switch Limit: -₹{dynamic_limit}")
    
    # Create a mock signal with a tiny order value to bypass the 'Insufficient margin' check
    test_signal = Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        entry_price=1.0,
        stop_loss=0.9,
        take_target=1.2,
        confidence=0.85
    )
    
    # 1. Normal State (PnL = 0)
    logger.info("Test 1: Normal State (0 PnL)")
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1)
    assert approved, f"Expected approval, got rejected: {reason}"
    logger.info("-> APPROVED (Expected)")

    # 2. Moderate Loss (Not exceeding limit)
    account.realized_pnl = -(dynamic_limit * 0.5)
    logger.info(f"Test 2: Moderate Loss (PnL = -₹{dynamic_limit * 0.5})")
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1)
    assert approved, f"Expected approval, got rejected: {reason}"
    logger.info("-> APPROVED (Expected)")

    # 3. Kill-Switch Triggered (Exceeding limit)
    account.unrealized_pnl = -(dynamic_limit * 0.5 + 100) # Total PnL is now below -dynamic_limit
    total_loss = abs(account.realized_pnl + account.unrealized_pnl)
    logger.info(f"Test 3: Kill-Switch Triggered (Total Loss = ₹{total_loss})")
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1)
    assert not approved, "Expected rejection due to kill-switch, but got approved!"
    logger.info(f"-> REJECTED (Expected). Reason: {reason}")
    
    logger.info("--- Kill-Switch Test Passed ---")

if __name__ == "__main__":
    test_daily_loss_kill_switch()
