import logging
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import Instrument

logger = logging.getLogger(__name__)

class InstrumentMaster:
    """
    In-memory and DB-backed cache for instrument lookups.
    Translates (tradingsymbol, exchange) -> instrument_token.
    """
    
    def __init__(self):
        # symbol_exchange -> token
        self._lookup: Dict[str, int] = {}
        self._is_loaded = False
        
    def _key(self, tradingsymbol: str, exchange: str) -> str:
        return f"{tradingsymbol}:{exchange}"
        
    def load_from_db(self, db: Session):
        """Loads the instrument lookup cache from the database."""
        instruments = db.query(Instrument).all()
        for inst in instruments:
            key = self._key(str(inst.tradingsymbol), str(inst.exchange))
            self._lookup[key] = int(inst.instrument_token) # type: ignore
            
        self._is_loaded = True
        logger.info(f"Loaded {len(self._lookup)} instruments from database into memory.")
        
    def resolve_token(self, tradingsymbol: str, exchange: str = "NSE") -> Optional[int]:
        """
        Resolves an instrument_token for a given symbol and exchange.
        """
        clean_sym = tradingsymbol.upper().replace(".NS", "").replace("NSE:", "").strip()
        if not self._is_loaded:
            try:
                db = SessionLocal()
                try:
                    self.load_from_db(db)
                finally:
                    db.close()  # always release even if load_from_db raises
            except Exception:
                pass

        token = self._lookup.get(self._key(clean_sym, exchange))
        if token:
            return token

        # Standard Zerodha NSE Tokens
        TOP_NSE_TOKENS = {
            "RELIANCE": 738561,
            "TCS": 2953217,
            "INFY": 408065,
            "HDFCBANK": 341249,
            "ICICIBANK": 1270529,
            "TATASTEEL": 895745,
            "SBIN": 779521,
            "BHARTIARTL": 2714625,
            "ITC": 424961,
            "KOTAKBANK": 492033,
            "LT": 2939649,
            "AXISBANK": 1510401,
            "MARUTI": 2815745,
            "BAJFINANCE": 81153,
            "WIPRO": 969473,
            "HCLTECH": 1850625,
            "ASIANPAINT": 60417,
            "SUNPHARMA": 857857,
            "TITAN": 897281,
            "ADANIENT": 6401
        }
        return TOP_NSE_TOKENS.get(clean_sym)

    def fetch_and_store_instruments(self, broker, db: Session):
        """
        Fetches the complete instrument dump from the broker and saves it to the database.
        Note: This is a heavy operation, usually run once a day before market opens.
        """
        logger.info("Fetching instruments from broker...")
        # Get raw instruments list of dicts
        instruments_data = broker.kite.instruments()
        
        logger.info(f"Fetched {len(instruments_data)} instruments. Saving to database...")
        
        # We can do an efficient bulk insert/upsert.
        # For simplicity, we just delete all and insert fresh, or clear table.
        # Since this is a capstone/demo, we'll clear and insert to keep it simple.
        db.query(Instrument).delete()
        
        # Batch insert
        batch_size = 5000
        batch = []
        for row in instruments_data:
            inst = Instrument(
                instrument_token=row.get('instrument_token'),
                exchange_token=str(row.get('exchange_token')),
                tradingsymbol=row.get('tradingsymbol'),
                name=row.get('name'),
                last_price=row.get('last_price', 0.0),
                expiry=row.get('expiry'),
                strike=row.get('strike'),
                tick_size=row.get('tick_size'),
                lot_size=row.get('lot_size'),
                instrument_type=row.get('instrument_type'),
                segment=row.get('segment'),
                exchange=row.get('exchange')
            )
            batch.append(inst)
            
            if len(batch) >= batch_size:
                db.bulk_save_objects(batch)
                batch = []
                
        if batch:
            db.bulk_save_objects(batch)
            
        db.commit()
        logger.info("Instruments saved to database successfully.")
        
        # Reload cache
        self.load_from_db(db)

# Global singleton
instrument_master = InstrumentMaster()
