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
        
        # Recover dev session
        try:
            import os
            if os.path.exists(".kite_session"):
                with open(".kite_session", "r") as f:
                    token = f.read().strip()
                    if token:
                        self.set_access_token(token)
        except Exception:
            pass

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
                
            logger.info("Successfully generated session and set access token.")
            return session_data # type: ignore
        except kite_exc.TokenException as e:
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
            return {"equity": {"available": {"live_balance": 500000.0}}}
            
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
            return state.get("positions", {"net": [], "day": []})
            
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
        if price <= 0.0:
            order_type = "MARKET"
        else:
            # Round price to nearest 0.05 tick size for NSE
            price = round(price * 20) / 20.0
            
        if settings.TRADING_MODE == "DRY_RUN":
            import uuid
            mock_id = f"mock_{uuid.uuid4().hex[:12]}"
            logger.info(f"[DRY_RUN] Placed mock {transaction_type} order for {quantity} {symbol} @ {price}. ID: {mock_id}")
            
            # Persist order and position in DRY_RUN
            state = self._load_dry_run_state()
            state["orders"].append({
                "order_id": mock_id,
                "status": "COMPLETE",
                "tradingsymbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "price": price,
                "filled_quantity": quantity
            })
            
            # Update positions
            found = False
            qty_multiplier = 1 if transaction_type == "BUY" else -1
            for pos in state["positions"]["net"]:
                if pos["tradingsymbol"] == symbol:
                    pos["quantity"] += quantity * qty_multiplier
                    pos["average_price"] = price # Simplified avg
                    found = True
                    break
            if not found:
                state["positions"]["net"].append({
                    "tradingsymbol": symbol,
                    "quantity": quantity * qty_multiplier,
                    "average_price": price
                })
                
            self._save_dry_run_state(state)
            return mock_id
            
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
        if settings.TRADING_MODE == "DRY_RUN" and order_id.startswith("mock_"):
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
    def get_quote(self, symbols: list[str]) -> Dict[str, Any]:
        """
        Fetches full market quotes for a list of instruments (e.g. ['NSE:RELIANCE']).
        Returns a dict mapping instrument token/symbol to its quote data (OHLC, depth, volume, circuit limits).
        """
        if settings.TRADING_MODE == "DRY_RUN":
            # Still try to hit the live API if token exists, fallback to mock if unauthenticated
            try:
                self._ensure_authenticated()
                return self.kite.quote(symbols) # type: ignore
            except ValueError:
                # Return a basic mock quote for DRY_RUN if no token is available
                logger.warning("No access token found. Returning mock quotes for DRY_RUN.")
                return {
                    s: {
                        "instrument_token": 0,
                        "timestamp": "2023-01-01 12:00:00",
                        "last_price": 3000.0,
                        "volume": 1000000,
                        "lower_circuit_limit": 2700.0,
                        "upper_circuit_limit": 3300.0,
                        "depth": {
                            "buy": [{"price": 2999.0, "quantity": 100}],
                            "sell": [{"price": 3001.0, "quantity": 100}]
                        }
                    } for s in symbols
                }
                
        self._ensure_authenticated()
        try:
            return self.kite.quote(symbols) # type: ignore
        except Exception as e:
            err_msg = str(e)
            if "Insufficient permission" not in err_msg:
                logger.error(f"Error fetching quote for {symbols}: {err_msg}")
            raise
