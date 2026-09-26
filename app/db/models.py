from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, UniqueConstraint
from datetime import datetime
from app.db.database import Base

class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer, index=True)
    timestamp = Column(DateTime, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    
    __table_args__ = (
        UniqueConstraint('instrument_token', 'timestamp', name='uix_instrument_time'),
    )

class Instrument(Base):
    __tablename__ = "instruments"

    instrument_token = Column(Integer, primary_key=True, index=True)
    exchange_token = Column(String, index=True)
    tradingsymbol = Column(String, index=True)
    name = Column(String)
    last_price = Column(Float)
    expiry = Column(DateTime, nullable=True)
    strike = Column(Float, nullable=True)
    tick_size = Column(Float)
    lot_size = Column(Integer)
    instrument_type = Column(String)
    segment = Column(String)
    exchange = Column(String, index=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String, index=True) # "SIGNAL", "USER_DECISION", "RISK_DECISION", "ORDER_EVENT"
    trade_id = Column(String, index=True, nullable=True)
    symbol = Column(String)
    action = Column(String)
    details = Column(String)
