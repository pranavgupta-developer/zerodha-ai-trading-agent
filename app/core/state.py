import threading
import time
import logging
from typing import Dict, List, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ThreadSafePriceCache:
    """
    Thread-safe price cache storing live market tick prices and tokens.
    Resolves symbols dynamically via InstrumentMaster rather than static dictionaries.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._token_cache: Dict[int, Dict[str, Any]] = {}
        self._symbol_cache: Dict[str, float] = {}
        self._token_to_symbol: Dict[int, str] = {}
        
        # Pre-seed top instruments dynamically from InstrumentMaster
        try:
            from app.broker.instrument_master import instrument_master
            for sym in [
                "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", 
                "TATASTEEL", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", 
                "LT", "AXISBANK", "MARUTI", "BAJFINANCE", "WIPRO", 
                "HCLTECH", "ASIANPAINT", "SUNPHARMA", "TITAN", "ADANIENT"
            ]:
                tok = instrument_master.resolve_token(sym)
                if tok:
                    self._token_to_symbol[tok] = sym
        except Exception as e:
            logger.debug(f"Failed to pre-seed instruments in price cache: {e}")

    def register_token_symbol(self, token: Any, symbol: str):
        try:
            token_int = int(token)
            clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "").strip()
            with self._lock:
                self._token_to_symbol[token_int] = clean_sym
        except (ValueError, TypeError):
            pass

    def update(self, token: Any, ltp: float):
        try:
            token_int = int(token)
        except (ValueError, TypeError):
            token_int = None
            
        with self._lock:
            if token_int is not None:
                self._token_cache[token_int] = {
                    "ltp": float(ltp),
                    "timestamp": time.time()
                }
                sym = self._token_to_symbol.get(token_int)
                if sym:
                    self._symbol_cache[sym] = float(ltp)

    def update_symbol(self, symbol: str, ltp: float):
        clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "").strip()
        with self._lock:
            self._symbol_cache[clean_sym] = float(ltp)

    def get(self, token: Any, default_ltp: float = 0.0) -> float:
        try:
            token_int = int(token)
        except (ValueError, TypeError):
            token_int = None
            
        with self._lock:
            if token_int is not None and token_int in self._token_cache:
                return self._token_cache[token_int]["ltp"]
            return default_ltp

    def get_by_symbol(self, symbol: str, default_ltp: float = 0.0) -> float:
        clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "").strip()
        with self._lock:
            return self._symbol_cache.get(clean_sym, default_ltp)


class TradingStateManager:
    """
    Centralized, synchronized state container for runtime trading operations.
    Replaces unsafe global mutable variables with thread-safe accessors.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.price_cache = ThreadSafePriceCache()
        self.active_connections: List[WebSocket] = []
        self.candidate_cache: Dict[str, Any] = {}
        self.autonomous_trades_history: List[Dict[str, Any]] = []
        self.emergency_stop_active: bool = False
        self.global_candles_cache: Dict[str, list] = {}
        self.global_holdings: list = []
        self.global_positions: list = []
        self.global_available_margin: float = 0.0
        self.recent_order_timestamps: list = []
        self.daily_prev_closes: Dict[str, float] = {}

    def set_emergency_stop(self, active: bool, reason: str = ""):
        with self._lock:
            self.emergency_stop_active = active
            logger.warning(f"Trading state emergency stop updated: active={active}, reason={reason}")

    def is_emergency_stop_active(self) -> bool:
        with self._lock:
            return self.emergency_stop_active

    def add_connection(self, ws: WebSocket):
        with self._lock:
            if ws not in self.active_connections:
                self.active_connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        with self._lock:
            if ws in self.active_connections:
                self.active_connections.remove(ws)

    def get_active_connections(self) -> List[WebSocket]:
        with self._lock:
            return list(self.active_connections)


# Global singleton
state_manager = TradingStateManager()
