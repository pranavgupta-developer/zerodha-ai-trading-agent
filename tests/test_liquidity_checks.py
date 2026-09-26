import logging
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.broker.kite_adapter import BrokerAdapter
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.signals import Signal, SignalDirection
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from typing import Optional

def test_liquidity_and_circuit_checks(request_token: Optional[str] = None):
    logger.info("--- Testing Circuit-Limit, Liquidity, and Slippage Checks ---")
    
    # We force LIVE mode to skip local JSON mocking if we have a token
    original_mode = settings.TRADING_MODE
    settings.TRADING_MODE = "LIVE"
    
    broker = BrokerAdapter()
    
    if request_token:
        try:
            session = broker.generate_session(request_token)
            broker.set_access_token(session["access_token"])
            logger.info("Successfully authenticated with Kite.")
        except Exception as e:
            logger.error(f"Failed to authenticate: {e}")
            settings.TRADING_MODE = original_mode
            return
            
    symbol = "NSE:RELIANCE"
    try:
        quotes = broker.get_quote([symbol])
        quote_data = quotes.get(symbol) if quotes else None
        if not quote_data:
            logger.error("No quote data returned from broker.")
            return
    except Exception as e:
        logger.warning(f"Failed to fetch live quote ({e}). Simulating a real quote for test purposes...")
        quote_data = {
            "last_price": 3000.0,
            "volume": 1000000,
            "lower_circuit_limit": 2700.0,
            "upper_circuit_limit": 3300.0,
            "depth": {
                "buy": [{"price": 2999.0, "quantity": 100}],
                "sell": [{"price": 3001.0, "quantity": 100}]
            }
        }
    finally:
        settings.TRADING_MODE = original_mode

    logger.info(f"\n--- Live Quote Data for {symbol} ---")
    last_price = float(quote_data.get("last_price", 0))
    lower_circuit = float(quote_data.get("lower_circuit_limit", 0))
    upper_circuit = float(quote_data.get("upper_circuit_limit", 0))
    volume = int(quote_data.get("volume", 0))
    
    depth = quote_data.get("depth", {})
    if not isinstance(depth, dict):
        depth = {}
        
    buy_depth = depth.get("buy", [])
    sell_depth = depth.get("sell", [])
    
    best_bid = float(buy_depth[0].get("price", 0)) if buy_depth and isinstance(buy_depth[0], dict) else 0.0
    best_ask = float(sell_depth[0].get("price", 0)) if sell_depth and isinstance(sell_depth[0], dict) else 0.0
    
    logger.info(f"Last Price: {last_price}")
    logger.info(f"Lower Circuit: {lower_circuit}")
    logger.info(f"Upper Circuit: {upper_circuit}")
    logger.info(f"Volume: {volume}")
    logger.info(f"Top of Book -> Bid: {best_bid}, Ask: {best_ask}")
    
    config = RiskConfig(
        max_daily_loss=100000.0,
        circuit_buffer_pct=0.01, # 1% away from circuit
        min_volume=50000,
        max_slippage_pct=0.005, # Max 0.5% bid/ask spread
        check_market_hours=False
    )
    engine = RiskEngine(config=config)
    
    account = AccountState(available_margin=1000000.0)
    
    # Base safe signal
    test_signal = Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        entry_price=last_price, # Safe entry price (mid price)
        stop_loss=last_price * 0.95,
        take_target=last_price * 1.05,
        confidence=0.85
    )

    # TEST 1: Ideal conditions
    logger.info("\nTest 1: Normal Live Market Conditions")
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1, quote_data=quote_data)
    logger.info(f"-> {'APPROVED' if approved else 'REJECTED: ' + reason}")

    # TEST 2: Lower Circuit Limit Breach
    logger.info("\nTest 2: Signal price within 1% of lower circuit limit")
    test_signal.entry_price = lower_circuit * 1.005 # Only 0.5% away
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1, quote_data=quote_data)
    logger.info(f"-> {'APPROVED' if approved else 'REJECTED: ' + reason}")

    # TEST 3: Upper Circuit Limit Breach
    logger.info("\nTest 3: Signal price within 1% of upper circuit limit")
    test_signal.entry_price = upper_circuit * 0.995 # Only 0.5% away
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1, quote_data=quote_data)
    logger.info(f"-> {'APPROVED' if approved else 'REJECTED: ' + reason}")
    
    # Restore safe entry price
    test_signal.entry_price = last_price

    # TEST 4: Low Liquidity
    logger.info("\nTest 4: Low Volume (Mocking quote_data['volume'] = 1000)")
    mock_quote_liquidity = dict(quote_data)
    mock_quote_liquidity["volume"] = 1000
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1, quote_data=mock_quote_liquidity)
    logger.info(f"-> {'APPROVED' if approved else 'REJECTED: ' + reason}")

    # TEST 5: High Slippage (Spread > 0.5%)
    logger.info(f"\nTest 5: High Slippage (Mocking bid/ask spread > {config.max_slippage_pct*100}%)")
    mock_quote_slippage = dict(quote_data)
    mock_quote_slippage["depth"] = {
        "buy": [{"price": last_price * 0.99}],   # Bid 1% lower
        "sell": [{"price": last_price * 1.01}]   # Ask 1% higher
    }
    approved, reason = engine.validate_signal(test_signal, account, requested_qty=1, quote_data=mock_quote_slippage)
    logger.info(f"-> {'APPROVED' if approved else 'REJECTED: ' + reason}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request_token", type=str, help="Kite request_token for live quote fetching", default=None)
    args = parser.parse_args()
    
    test_liquidity_and_circuit_checks(args.request_token)
