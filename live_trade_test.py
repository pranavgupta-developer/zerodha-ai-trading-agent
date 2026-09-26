import os
import sys
import time
import logging
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from app.broker.kite_adapter import BrokerAdapter
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main(request_token):
    settings.TRADING_MODE = "LIVE"
    broker = BrokerAdapter()
    
    if request_token:
        try:
            session = broker.generate_session(request_token)
            logger.info("Successfully authenticated with Kite.")
        except Exception as e:
            logger.error(f"Failed to authenticate: {e}")
            return
    else:
        logger.error("A valid request_token is required for LIVE trading.")
        return

    symbol = "RELIANCE"
    qty = 1
    
    # Place Trade
    logger.info(f"Placing LIVE MARKET BUY for {qty} share of {symbol}...")
    try:
        order_id = broker.place_order(
            symbol=symbol,
            transaction_type="BUY",
            quantity=qty,
            price=0.0,
            order_type="MARKET",
            product="MIS"
        )
        logger.info(f"Order placed successfully: {order_id}")
    except Exception as e:
        logger.error(f"Order failed: {e}")
        return
        
    # Track Trade
    logger.info("Tracking order status...")
    while True:
        try:
            history = broker.get_order_history(order_id)
            if not history:
                continue
            status = history[-1]["status"]
            logger.info(f"Order Status: {status}")
            if status == "COMPLETE":
                break
            elif status in ["REJECTED", "CANCELLED"]:
                logger.error(f"Order didn't complete: {history[-1].get('status_message')}")
                return
        except Exception as e:
            logger.error(f"Failed to track order: {e}")
        time.sleep(1)
        
    logger.info("Trade successfully executed!")
    
    # Manual close prompt
    input("Press Enter to manually close this trade (SELL 1 share of RELIANCE)...")
    
    logger.info(f"Placing LIVE MARKET SELL for {qty} share of {symbol}...")
    try:
        sell_order_id = broker.place_order(
            symbol=symbol,
            transaction_type="SELL",
            quantity=qty,
            price=0.0,
            order_type="MARKET",
            product="MIS"
        )
        logger.info(f"Sell Order placed successfully: {sell_order_id}")
    except Exception as e:
        logger.error(f"Sell Order failed: {e}")
        return
        
    # Track Sell
    logger.info("Tracking sell order status...")
    while True:
        try:
            history = broker.get_order_history(sell_order_id)
            if not history:
                continue
            status = history[-1]["status"]
            logger.info(f"Sell Order Status: {status}")
            if status == "COMPLETE":
                break
            elif status in ["REJECTED", "CANCELLED"]:
                logger.error(f"Sell Order didn't complete: {history[-1].get('status_message')}")
                return
        except Exception as e:
            logger.error(f"Failed to track order: {e}")
        time.sleep(1)
        
    logger.info("Trade closed successfully. End-to-end LIVE test complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request_token", type=str, required=True, help="Kite request_token")
    args = parser.parse_args()
    main(args.request_token)
