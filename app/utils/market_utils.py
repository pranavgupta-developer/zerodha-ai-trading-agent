import datetime
from zoneinfo import ZoneInfo

from typing import Optional

IST = ZoneInfo("Asia/Kolkata")

# Hardcoded major holidays for NSE (e.g. 2024/2026). In production, keep this updated or fetch from Kite API.
NSE_HOLIDAYS = [
    datetime.date(2026, 1, 26),  # Republic Day
    datetime.date(2026, 3, 20),  # Holi (example, varies)
    datetime.date(2026, 4, 14),  # Ambedkar Jayanti (example)
    datetime.date(2026, 5, 1),   # Maharashtra Day
    datetime.date(2026, 8, 15),  # Independence Day
    datetime.date(2026, 10, 2),  # Gandhi Jayanti
    datetime.date(2026, 12, 25), # Christmas
]

def is_market_open(dt: Optional[datetime.datetime] = None) -> bool:
    """
    Checks if the market is open at the given datetime (defaults to now).
    Market hours: configurable via settings (defaults to 09:30 or 09:15 to 15:30 IST on weekdays).
    """
    if dt is None:
        dt = datetime.datetime.now(tz=IST)
        
    # Ensure dt is timezone aware (IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)

    # Check weekend (0=Monday, 6=Sunday)
    if dt.weekday() >= 5:
        return False
        
    # Check holidays
    if dt.date() in NSE_HOLIDAYS:
        return False

    try:
        from app.core.config import settings
        open_h = getattr(settings, "MARKET_OPEN_HOUR", 9)
        open_m = getattr(settings, "MARKET_OPEN_MINUTE", 15)
        close_h = getattr(settings, "MARKET_CLOSE_HOUR", 15)
        close_m = getattr(settings, "MARKET_CLOSE_MINUTE", 30)
    except Exception:
        open_h, open_m, close_h, close_m = 9, 15, 15, 30

    market_open_time = datetime.time(open_h, open_m)
    market_close_time = datetime.time(close_h, close_m)
    
    current_time = dt.time()
    
    if market_open_time <= current_time <= market_close_time:
        return True
        
    return False

def get_next_market_open(dt: Optional[datetime.datetime] = None) -> datetime.datetime:
    """
    Returns the datetime of the next market open.
    """
    if dt is None:
        dt = datetime.datetime.now(tz=IST)
        
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)

    try:
        from app.core.config import settings
        open_h = getattr(settings, "MARKET_OPEN_HOUR", 9)
        open_m = getattr(settings, "MARKET_OPEN_MINUTE", 15)
    except Exception:
        open_h, open_m = 9, 15

    open_time = datetime.time(open_h, open_m)

    # If it's before market open today, and today is a trading day, next open is today at open_time
    if dt.time() < open_time:
        if dt.weekday() < 5 and dt.date() not in NSE_HOLIDAYS:
            return dt.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
            
    # Otherwise, check subsequent days
    next_day = dt.date() + datetime.timedelta(days=1)
    while next_day.weekday() >= 5 or next_day in NSE_HOLIDAYS:
        next_day += datetime.timedelta(days=1)
        
    return datetime.datetime.combine(next_day, open_time).replace(tzinfo=IST)
