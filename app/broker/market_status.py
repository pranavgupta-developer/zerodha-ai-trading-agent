from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional

IST = ZoneInfo("Asia/Kolkata")

# Hardcoded a few common Indian market holidays for 2026 as placeholders
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26), # Republic Day
    date(2026, 4, 3),  # Good Friday
    date(2026, 5, 1),  # Maharashtra Day
    date(2026, 8, 15), # Independence Day
    date(2026, 10, 2), # Gandhi Jayanti
    date(2026, 11, 8), # Diwali (approx)
    date(2026, 12, 25) # Christmas
}

def is_market_holiday(d: date) -> bool:
    return d in NSE_HOLIDAYS_2026

def get_market_status(latest_tick_time: Optional[datetime] = None, stale_threshold_seconds: int = 300) -> str:
    """
    Evaluates the current market time and the freshness of the data to return
    a clear status: 'CLOSED', 'OPEN', 'STALE', or 'HEALTHY'.
    """
    now = datetime.now(tz=IST)
    
    # 1. Check weekends
    if now.weekday() >= 5: # 5 = Saturday, 6 = Sunday
        return "CLOSED"
        
    # 2. Check holidays
    if is_market_holiday(now.date()):
        return "CLOSED"
        
    # 3. Check market hours (9:15 AM - 3:30 PM IST)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now < market_open or now > market_close:
        return "CLOSED"
        
    # 4. Check Stale Data
    if latest_tick_time:
        if latest_tick_time.tzinfo is None:
            latest_tick_time = latest_tick_time.replace(tzinfo=IST)
            
        time_diff = (now - latest_tick_time).total_seconds()
        
        # If the market just opened, we might not have a tick yet, but if it's been stale longer than threshold
        if time_diff > stale_threshold_seconds:
            return "STALE"
        return "HEALTHY"
        
    return "OPEN"
