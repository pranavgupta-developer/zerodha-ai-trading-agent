import logging
from typing import List, Dict, Any, Callable
from kiteconnect import KiteTicker
from app.broker.candle_aggregator import aggregator

logger = logging.getLogger(__name__)

# Hardcoded instrument tokens for testing (e.g., RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)
# In reality, these should be resolved from the instrument master.
DEFAULT_WATCHLIST = [738561, 2953217, 408065, 341249, 1270529]

class MarketTicker:
    """
    Manages the KiteTicker WebSocket connection for real-time market data.
    """
    def __init__(self, api_key: str, access_token: str):
        self.ticker = KiteTicker(api_key, access_token)
        self.watchlist = DEFAULT_WATCHLIST
        
        # Optional external callback to push ticks into the Market Data Cache / Aggregator
        self.on_ticks_callback: Callable[[List[Dict[str, Any]]], None] | None = aggregator.process_ticks
        
        # Bind callbacks
        self.ticker.on_ticks = self._on_ticks # type: ignore
        self.ticker.on_connect = self._on_connect # type: ignore
        self.ticker.on_close = self._on_close # type: ignore
        self.ticker.on_error = self._on_error # type: ignore
        self.ticker.on_reconnect = self._on_reconnect # type: ignore
        self.ticker.on_noreconnect = self._on_noreconnect # type: ignore

    def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
        """
        Callback to receive market ticks.
        """
        logger.debug(f"Received ticks for {len(ticks)} instruments")
        
        if self.on_ticks_callback:
            self.on_ticks_callback(ticks)
        else:
            # Fallback logging if no aggregator is attached
            for tick in ticks:
                token = tick.get('instrument_token')
                ltp = tick.get('last_price')
                logger.info(f"Tick received: Token={token}, LTP={ltp}")

    def _on_connect(self, ws, response):
        """
        Callback on successful connection.
        """
        logger.info("KiteTicker connected successfully. Subscribing to watchlist...")
        ws.subscribe(self.watchlist)
        # Set to MODE_FULL to get OHLC, volume, best bid/ask
        ws.set_mode(ws.MODE_FULL, self.watchlist)

    def _on_close(self, ws, code, reason):
        logger.warning(f"KiteTicker connection closed: Code={code}, Reason={reason}")

    def _on_error(self, ws, code, reason):
        logger.error(f"KiteTicker connection error: Code={code}, Reason={reason}")

    def _on_reconnect(self, ws, attempts_count):
        logger.info(f"KiteTicker reconnecting... Attempt: {attempts_count}")

    def _on_noreconnect(self, ws):
        logger.error("KiteTicker reconnection failed. Max attempts reached. System must halt trading.")

    def start(self, threaded: bool = True):
        """
        Connect to the WebSocket. 
        Runs in a background thread by default so it doesn't block the FastAPI event loop.
        """
        logger.info("Starting KiteTicker connection...")
        self.ticker.connect(threaded=threaded)
        
    def stop(self):
        """
        Close the WebSocket connection safely.
        """
        logger.info("Stopping KiteTicker...")
        if self.ticker:
            self.ticker.close()
