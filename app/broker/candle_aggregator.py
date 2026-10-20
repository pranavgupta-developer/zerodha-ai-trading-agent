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
    Aggregates real-time ticks into 1-minute, 5-minute, and 15-minute candles and persists them to SQLite.
    """
    def __init__(self):
        # Maps interval -> instrument_token -> candle_data
        self.current_candles: Dict[str, Dict[int, Dict[str, Any]]] = {
            '1m': {},
            '5m': {},
            '15m': {}
        }

    def process_ticks(self, ticks: List[Dict[str, Any]]):
        """
        Callback to process incoming ticks from WebSocket.
        """
        now = datetime.now(tz=IST)
        
        # Calculate boundaries for 1m, 5m, 15m
        boundaries = {
            '1m': now.replace(second=0, microsecond=0),
            '5m': now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0),
            '15m': now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        }

        closed_candles = []

        for tick in ticks:
            token = tick.get('instrument_token')
            ltp = tick.get('last_price')
            qty = tick.get('last_traded_quantity', 0)
            
            if not token or not ltp:
                continue
                
            for interval in ['1m', '5m', '15m']:
                current_boundary = boundaries[interval]
                
                if token not in self.current_candles[interval]:
                    # Initialize new candle
                    self.current_candles[interval][token] = {
                        'timestamp': current_boundary,
                        'open': ltp,
                        'high': ltp,
                        'low': ltp,
                        'close': ltp,
                        'volume': qty
                    }
                else:
                    candle = self.current_candles[interval][token]
                    # If boundary has changed, flush the old candle and start a new one
                    if candle['timestamp'] < current_boundary:
                        closed_candles.append((interval, token, dict(candle)))
                        
                        self.current_candles[interval][token] = {
                            'timestamp': current_boundary,
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
            for interval, token, c in closed_candles:
                db_candle = Candle(
                    instrument_token=token,
                    interval=interval,
                    timestamp=c['timestamp'].replace(tzinfo=None),
                    open=c['open'],
                    high=c['high'],
                    low=c['low'],
                    close=c['close'],
                    volume=c['volume']
                )
                db_candles.append(db_candle)
            
            db.bulk_save_objects(db_candles)
            db.commit()
            logger.debug(f"Persisted {len(db_candles)} candles to DB.")
        except Exception as e:
            logger.error(f"Error persisting candles: {str(e)}")
            db.rollback()
        finally:
            db.close()

    def get_recent_candles(self, instrument_token: int, interval: str = '1m', limit: int = 50) -> List[Any]:
        """
        Retrieves recent real aggregated candles from the SQLite database.
        """
        db: Session = SessionLocal()
        try:
            candles = db.query(Candle).filter(
                Candle.instrument_token == instrument_token,
                Candle.interval == interval
            ).order_by(Candle.timestamp.asc()).all()
            return candles[-limit:]
        except Exception as e:
            logger.error(f"Error fetching recent candles for token {instrument_token}: {e}")
            return []
        finally:
            db.close()

# Global aggregator instance
aggregator = CandleAggregator()
