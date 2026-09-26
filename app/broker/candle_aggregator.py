import logging
from typing import List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import Candle

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

class CandleAggregator:
    """
    Aggregates real-time ticks into 1-minute candles and persists them to SQLite.
    """
    def __init__(self):
        # Maps instrument_token -> {
        #   'timestamp': datetime (minute start),
        #   'open': float, 'high': float, 'low': float, 'close': float, 'volume': int
        # }
        self.current_candles: Dict[int, Dict[str, Any]] = {}

    def process_ticks(self, ticks: List[Dict[str, Any]]):
        """
        Callback to process incoming ticks from WebSocket.
        """
        now = datetime.now(tz=IST)
        # 1-minute floor
        current_minute = now.replace(second=0, microsecond=0)

        closed_candles = []

        for tick in ticks:
            token = tick.get('instrument_token')
            ltp = tick.get('last_price')
            
            # Note: Kite tick might contain 'last_traded_quantity' or 'volume_traded_today'
            # To get accurate 1-min volume, we could difference the cumulative volume or 
            # accumulate last_traded_quantity. We use a simple volume proxy here if available.
            qty = tick.get('last_traded_quantity', 0)
            
            if not token or not ltp:
                continue
                
            if token not in self.current_candles:
                # Initialize new candle
                self.current_candles[token] = {
                    'timestamp': current_minute,
                    'open': ltp,
                    'high': ltp,
                    'low': ltp,
                    'close': ltp,
                    'volume': qty
                }
            else:
                candle = self.current_candles[token]
                # If minute has changed, flush the old candle and start a new one
                if candle['timestamp'] < current_minute:
                    closed_candles.append((token, dict(candle)))
                    
                    self.current_candles[token] = {
                        'timestamp': current_minute,
                        'open': ltp,
                        'high': ltp,
                        'low': ltp,
                        'close': ltp,
                        'volume': qty
                    }
                else:
                    # Update current candle
                    candle['high'] = max(candle['high'], ltp)
                    candle['low'] = min(candle['low'], ltp)
                    candle['close'] = ltp
                    candle['volume'] += qty

        # Persist closed candles
        if closed_candles:
            self._persist_candles(closed_candles)

    def _persist_candles(self, closed_candles: List[tuple]):
        """
        Saves the aggregated candles to the database.
        """
        db: Session = SessionLocal()
        try:
            db_candles = []
            for token, c in closed_candles:
                db_candle = Candle(
                    instrument_token=token,
                    timestamp=c['timestamp'].replace(tzinfo=None), # Store as naive UTC or naive local in DB
                    open=c['open'],
                    high=c['high'],
                    low=c['low'],
                    close=c['close'],
                    volume=c['volume']
                )
                db_candles.append(db_candle)
            
            db.bulk_save_objects(db_candles)
            db.commit()
            logger.debug(f"Persisted {len(db_candles)} 1-minute candles to DB.")
        except Exception as e:
            logger.error(f"Error persisting candles: {str(e)}")
            db.rollback()
        finally:
            db.close()

# Global aggregator instance
aggregator = CandleAggregator()
