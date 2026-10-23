import logging
import json
import os
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from kiteconnect import KiteConnect
import kiteconnect.exceptions as kite_exc
from app.core.config import settings

def broker_retry(retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    is_transient = any(word in error_msg for word in ["timeout", "connection", "502", "503", "unavailable", "network"])
                    if is_transient and attempt < retries:
                        logger.warning(f"Transient error in {func.__name__} (attempt {attempt}/{retries}): {e}. Retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise
        return wrapper
    return decorator

logger = logging.getLogger(__name__)

class BrokerAdapter:
    """
    Adapter for KiteConnect API.
    Provides methods for authentication, fetching access token, and executing API calls safely.
    """
    
    def __init__(self):
        self.api_key: str = settings.KITE_API_KEY
        self.api_secret: str = settings.KITE_API_SECRET
        self.kite: KiteConnect = KiteConnect(api_key=self.api_key)
        self._access_token: Optional[str] = None
        self._dry_run_file = "dry_run_state.json"
        
        # Recover dev session from settings or disk
        try:
            if getattr(settings, "KITE_ACCESS_TOKEN", None) and settings.KITE_ACCESS_TOKEN != "fake_token":
                self.set_access_token(settings.KITE_ACCESS_TOKEN)
            elif os.path.exists(".kite_session"):
                with open(".kite_session", "r") as f:
                    token = f.read().strip()
                    if token and token != "fake_token":
                        self.set_access_token(token)
        except Exception:
            pass

    _auth_cached_at: float = 0.0
    _is_auth_cached: bool = False

    def is_authenticated(self, force_check: bool = False) -> bool:
        """
        Verifies if a valid Zerodha Kite Connect access token is active.
        Caches verification for 60 seconds to avoid spamming the profile endpoint.
        """
        if not self._access_token or self._access_token.startswith("fake_"):
            return False
            
        now = time.time()
        if not force_check and (now - self._auth_cached_at < 60.0):
            return self._is_auth_cached

        try:
            self.kite.profile()
            self._is_auth_cached = True
            self._auth_cached_at = now
            return True
        except Exception:
            self._is_auth_cached = False
            self._auth_cached_at = now
            return False

    def _load_dry_run_state(self) -> Dict[str, Any]:
        if os.path.exists(self._dry_run_file):
            with open(self._dry_run_file, "r") as f:
                state = json.load(f)
                return state if isinstance(state, dict) else {"orders": [], "positions": {"net": [], "day": []}}
        return {"orders": [], "positions": {"net": [], "day": []}}

    def _save_dry_run_state(self, state: Dict[str, Any]) -> None:
        with open(self._dry_run_file, "w") as f:
            json.dump(state, f)

    @broker_retry(retries=3, delay=1.0)
    def get_login_url(self) -> str:
        """
        Generates the Kite Connect login URL.
        """
        return self.kite.login_url()

    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """
        Exchanges the request_token for an access_token.
        Sets the access_token in the kite instance upon success.
        
        Args:
            request_token (str): The token received after a successful login redirect.
            
        Returns:
            Dict[str, Any]: The user session data including the access_token.
        """
        try:
            session_data = self.kite.generate_session(
                request_token=request_token,
                api_secret=self.api_secret
            ) # type: ignore
            self._access_token = session_data.get("access_token") # type: ignore
            self.kite.set_access_token(self._access_token)
            
            # Persist token for dev reloads
            with open(".kite_session", "w") as f:
                f.write(self._access_token)
                
            self._auth_cached_at = 0.0
            logger.info("Successfully generated session and set access token.")
            return session_data # type: ignore
        except kite_exc.TokenException as e:
            self._is_auth_cached = False
            self._auth_cached_at = time.time()
            logger.error(f"Token exception during session generation: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during session generation: {str(e)}")
            raise

    def set_access_token(self, access_token: str) -> None:
        """
        Manually set the access token if retrieved from secure storage.
        """
        self._access_token = access_token
        self.kite.set_access_token(self._access_token)
        self._auth_cached_at = 0.0
        
    def get_profile(self) -> Dict[str, Any]:
        """
        Fetch user profile to verify authentication.
        """
        if not self._access_token:
            raise ValueError("Access token is not set. Cannot fetch profile.")
        
        try:
            return self.kite.profile() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching profile: {str(e)}")
            raise

    def _ensure_authenticated(self):
        """Helper to ensure access token is set before calling broker APIs."""
        if not self._access_token:
            raise ValueError("Access token is not set. Please authenticate first.")

    @broker_retry(retries=3, delay=1.0)
    def get_margins(self) -> Dict[str, Any]:
        """
        Fetch funds and margins for the account.
        """
        if settings.TRADING_MODE == "DRY_RUN":
            if self._access_token:
                try:
                    return self.kite.margins() # type: ignore
                except Exception:
                    pass
            return {"equity": {"available": {"live_balance": 500000.0}, "net": 500000.0}}
            
        self._ensure_authenticated()
        try:
            return self.kite.margins() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token when fetching margins: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching margins: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_holdings(self) -> list[Dict[str, Any]]:
        """
        Fetch current equity holdings.
        """
        self._ensure_authenticated()
        try:
            return self.kite.holdings() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token when fetching holdings: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching holdings: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_positions(self) -> Dict[str, list[Dict[str, Any]]]:
        """
        Fetch day and net open positions.
        """
        if settings.TRADING_MODE == "DRY_RUN":
            state = self._load_dry_run_state()
            raw_pos = state.get("positions", {"net": [], "day": []})
            cleaned_net = []
            for p in raw_pos.get("net", []):
                item = dict(p)
                item["tradingsymbol"] = str(item.get("tradingsymbol", "")).replace(".NS", "").strip()
                item["quantity"] = int(item.get("quantity", 0))
                cleaned_net.append(item)
            return {"net": cleaned_net, "day": raw_pos.get("day", []), "realized_pnl": float(state.get("realized_pnl", 0.0))}
            
        self._ensure_authenticated()
        try:
            return self.kite.positions() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token when fetching positions: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_holdings(self) -> list[Dict[str, Any]]:
        """
        Fetch long term portfolio holdings.
        """
        if settings.TRADING_MODE == "DRY_RUN":
            return []
            
        self._ensure_authenticated()
        try:
            return self.kite.holdings() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token when fetching holdings: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching holdings: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_orders(self) -> list[Dict[str, Any]]:
        """
        Fetch the current day's order book.
        """
        if settings.TRADING_MODE == "DRY_RUN":
            state = self._load_dry_run_state()
            return state.get("orders", [])
            
        self._ensure_authenticated()
        try:
            return self.kite.orders() # type: ignore
        except kite_exc.TokenException as e:
            logger.error(f"Invalid or expired token when fetching orders: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def place_order(self, symbol: str, transaction_type: str, quantity: int, price: float, order_type: str = "LIMIT", product: str = "MIS") -> str:
        """
        Places an order on Kite Connect. Returns the broker_order_id.
        In DRY_RUN mode, generates a mock ID.
        """
        clean_symbol = symbol.replace(".NS", "").strip()
        quantity = abs(int(quantity))

        if price <= 0.0:
            order_type = "MARKET"
        else:
            # Round price to nearest 0.05 tick size for NSE
            price = round(price * 20) / 20.0
            
        if settings.TRADING_MODE == "DRY_RUN":
            import uuid
            dry_id = f"dry_{uuid.uuid4().hex[:12]}"
            
            # Resolve actual market price for MARKET orders (price <= 0.0)
            exec_price = price
            if exec_price <= 0.0:
                try:
                    import app.main as m
                    exec_price = m.price_cache.get_by_symbol(clean_symbol, 0.0)
                except Exception:
                    exec_price = 0.0
            
            logger.info(f"[DRY_RUN] Placed {transaction_type} order on live market feed for {quantity} {clean_symbol} @ ₹{exec_price:.2f}. ID: {dry_id}")
            
            # Persist order and position in DRY_RUN
            state = self._load_dry_run_state()
            state["orders"].append({
                "order_id": dry_id,
                "status": "COMPLETE",
                "tradingsymbol": clean_symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "price": exec_price,
                "filled_quantity": quantity
            })
            
            # Update positions (two-way long/short accounting with accurate realized P&L)
            found = False
            for pos in state["positions"]["net"]:
                if pos["tradingsymbol"] == clean_symbol:
                    found = True
                    curr_qty = int(pos.get("quantity", 0))
                    curr_avg = float(pos.get("average_price", exec_price))
                    effective_price = exec_price if exec_price > 0.0 else curr_avg
                    
                    if transaction_type == "BUY":
                        if curr_qty < 0:
                            # Closing/covering short position
                            covered_qty = min(abs(curr_qty), quantity)
                            pnl_gain = round((curr_avg - effective_price) * covered_qty, 2)
                            state["realized_pnl"] = round(float(state.get("realized_pnl", 0.0)) + pnl_gain, 2)
                            new_qty = curr_qty + quantity
                            pos["quantity"] = new_qty
                            if new_qty > 0:
                                pos["average_price"] = effective_price
                        else:
                            # Increasing long position
                            new_qty = curr_qty + quantity
                            if new_qty > 0 and effective_price > 0:
                                pos["average_price"] = round((curr_qty * curr_avg + quantity * effective_price) / new_qty, 2)
                            pos["quantity"] = new_qty
                    else:  # SELL
                        if curr_qty > 0:
                            # Closing/selling long position
                            sold_qty = min(curr_qty, quantity)
                            pnl_gain = round((effective_price - curr_avg) * sold_qty, 2)
                            state["realized_pnl"] = round(float(state.get("realized_pnl", 0.0)) + pnl_gain, 2)
                            new_qty = curr_qty - quantity
                            pos["quantity"] = new_qty
                            if new_qty < 0:
                                pos["average_price"] = effective_price
                        else:
                            # Opening/increasing short position
                            curr_short = abs(curr_qty)
                            new_short = curr_short + quantity
                            if new_short > 0 and effective_price > 0:
                                pos["average_price"] = round((curr_short * curr_avg + quantity * effective_price) / new_short, 2)
                            pos["quantity"] = -new_short
                    break
                    
            if not found:
                initial_qty = quantity if transaction_type == "BUY" else -quantity
                state["positions"]["net"].append({
                    "tradingsymbol": clean_symbol,
                    "quantity": initial_qty,
                    "average_price": exec_price
                })
                
            self._save_dry_run_state(state)
            return dry_id
            
        self._ensure_authenticated()
        
        # Kite expects tradingsymbols without .NS suffix for NSE
        clean_symbol = symbol.replace(".NS", "")
        
        try:
            order_id = self.kite.place_order( # type: ignore
                variety=self.kite.VARIETY_REGULAR, # type: ignore
                exchange=self.kite.EXCHANGE_NSE, # type: ignore
                tradingsymbol=clean_symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product=product,
                order_type=order_type,
                price=price
            )
            return str(order_id)
        except Exception as e:
            logger.error(f"Error placing order: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_order_history(self, order_id: str) -> list[Dict[str, Any]]:
        """
        Fetches the state transition history of a specific order.
        """
        if settings.TRADING_MODE == "DRY_RUN" and (order_id.startswith("dry_") or order_id.startswith("mock_")):
            state = self._load_dry_run_state()
            for order in state.get("orders", []):
                if isinstance(order, dict) and order.get("order_id") == order_id:
                    return [order]
            return [{"status": "COMPLETE", "status_message": "Dry run complete", "filled_quantity": 100}]
            
        self._ensure_authenticated()
        try:
            return self.kite.order_history(order_id) # type: ignore
        except Exception as e:
            logger.error(f"Error fetching order history for {order_id}: {str(e)}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str = "minute"
    ) -> list[Dict[str, Any]]:
        """
        Fetches historical OHLCV data directly from Zerodha Kite Connect API.
        """
        self._ensure_authenticated()
        try:
            return self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
        except Exception as e:
            logger.warning(f"Error fetching historical data for token {instrument_token}: {e}")
            raise

    @broker_retry(retries=3, delay=1.0)
    def get_quote(self, symbols: list[str]) -> Dict[str, Any]:
        """
        Fetches live market quotes for instruments (e.g. ['NSE:RELIANCE', 'NSE:TCS']) directly from Zerodha.
        Returns quote dictionary mapping symbol to LTP, OHLC, volume, circuit limits, and market depth.
        """
        if not self._access_token or self._access_token.startswith("fake_"):
            return {}
        try:
            return self.kite.quote(symbols) # type: ignore
        except Exception as e:
            err_msg = str(e)
            if "TokenException" in err_msg or "invalid" in err_msg.lower() or "expire" in err_msg.lower():
                self._is_auth_cached = False
                self._auth_cached_at = time.time()
                logger.warning("Zerodha access token expired. Please re-authenticate.")
            else:
                logger.warning(f"Error fetching live Zerodha quote: {err_msg}")
            return {}
