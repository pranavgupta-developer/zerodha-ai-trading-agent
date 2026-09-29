import sys, time, json
import asyncio
from app.broker.kite_adapter import BrokerAdapter

broker = BrokerAdapter()
broker._access_token = open(".kite_session").read().strip() if open(".kite_session").read().strip() else None

last_broker_sync = 0
cached_holdings = []
cached_positions = []
symbols = ["RELIANCE.NS"]
display_symbols = {"RELIANCE.NS": "RELIANCE"}

try:
    cached_holdings = broker.get_holdings() or []
    cached_positions_data = broker.get_positions()
    cached_positions = cached_positions_data.get("net", []) if cached_positions_data else []
except Exception as e:
    print(f"Failed to sync broker data: {e}")

try:
    portfolio_symbols = set([h.get("tradingsymbol") for h in cached_holdings] + [p.get("tradingsymbol") for p in cached_positions])
    for ps in portfolio_symbols:
        yf_sym = f"{ps}.NS"
        if yf_sym not in symbols:
            symbols.append(yf_sym)
            display_symbols[yf_sym] = ps
    print(symbols)
except Exception as e:
    print(f"Error in portfolio symbols loop: {e}")
