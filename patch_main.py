import re

with open("app/main.py", "r") as f:
    content = f.read()

# 1. Update the fetching logic
old_fetch = """            watchlist_payload = []
            
            for sym in symbols:
                df = yf.download(sym, period="5d", interval="1m", progress=False)
                if df.empty:
                    continue"""

new_fetch = """            watchlist_payload = []
            
            import time
            import asyncio
            
            # Fetch all symbols concurrently to prevent event-loop blocking
            tasks = [asyncio.to_thread(yf.download, sym, period="5d", interval="1m", progress=False) for sym in symbols]
            source_ts = time.time() # Timestamp of the source data fetch
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sym, result in zip(symbols, results):
                if isinstance(result, Exception):
                    continue
                    
                df = result
                if df.empty:
                    continue"""

content = content.replace(old_fetch, new_fetch)

# 2. Update watchlist_payload.append
old_append = """                watchlist_payload.append({
                    "symbol": display_symbols[sym],
                    "ltp": current_price,
                    "change": change,
                    "signal": signal_str
                })"""

new_append = """                watchlist_payload.append({
                    "symbol": display_symbols[sym],
                    "ltp": current_price,
                    "change": change,
                    "signal": signal_str,
                    "source_ts": source_ts
                })"""

content = content.replace(old_append, new_append)

# 3. Update websocket broadcast
old_ws = """                for connection in active_connections:
                    try:
                        await connection.send_text(json.dumps({
                            "type": "market_update",
                            "watchlist": watchlist_payload,
                            "positions": frontend_positions,
                            "account_stats": {
                                "margin": available_margin,
                                "realized_pnl": 0 # Realized PNL calculation can be added later
                            }
                        }))"""

new_ws = """                backend_ts = time.time()
                for connection in active_connections:
                    try:
                        await connection.send_text(json.dumps({
                            "type": "market_update",
                            "watchlist": watchlist_payload,
                            "positions": frontend_positions,
                            "account_stats": {
                                "margin": available_margin,
                                "realized_pnl": 0 # Realized PNL calculation can be added later
                            },
                            "backend_ts": backend_ts
                        }))"""

content = content.replace(old_ws, new_ws)

# 4. Update sleep
old_sleep = "await asyncio.sleep(0.001) # Poll every 15 seconds for faster updates"
new_sleep = "await asyncio.sleep(2) # Non-blocking poll every 2 seconds"
content = content.replace(old_sleep, new_sleep)

with open("app/main.py", "w") as f:
    f.write(content)
