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
    Market hours: 09:15 to 15:30 IST on weekdays (Mon-Fri).
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

    # Check time (09:15 to 15:30)
    market_open_time = datetime.time(9, 15)
    market_close_time = datetime.time(15, 30)
    
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

    # If it's before 9:15 AM today, and today is a trading day, next open is today at 9:15
    if dt.time() < datetime.time(9, 15):
        if dt.weekday() < 5 and dt.date() not in NSE_HOLIDAYS:
            return dt.replace(hour=9, minute=15, second=0, microsecond=0)
            
    # Otherwise, check subsequent days
    next_day = dt.date() + datetime.timedelta(days=1)
    while next_day.weekday() >= 5 or next_day in NSE_HOLIDAYS:
        next_day += datetime.timedelta(days=1)
        
    return datetime.datetime.combine(next_day, datetime.time(9, 15)).replace(tzinfo=IST)
