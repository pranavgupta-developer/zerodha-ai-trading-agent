import re

with open("app/main.py", "r") as f:
    content = f.read()

# Add periodic refresh for holdings/positions
loop_start = """
    last_broker_sync = 0
    cached_holdings = []
    cached_positions = []
    
    while True:
        try:
            # Sync broker data every 10 seconds to avoid rate limits
            if time.time() - last_broker_sync > 10:
                try:
                    cached_holdings = broker.get_holdings() or []
                    cached_positions_data = broker.get_positions()
                    cached_positions = cached_positions_data.get("net", []) if cached_positions_data else []
                except Exception as e:
                    logger.error(f"Failed to sync broker data: {e}")
                last_broker_sync = time.time()

            # Dynamically add portfolio symbols to watchlist
            portfolio_symbols = set([h.get("tradingsymbol") for h in cached_holdings] + [p.get("tradingsymbol") for p in cached_positions])
            for ps in portfolio_symbols:
                yf_sym = f"{ps}.NS"
                if yf_sym not in symbols:
                    symbols.append(yf_sym)
                    display_symbols[yf_sym] = ps
"""
content = re.sub(r'    while True:\n        try:', loop_start, content, count=1)

# Replace the fetching of positions/holdings later in the loop with the cached versions and update LTPs
old_positions_block = """
                    positions_data = broker.get_positions()
                    pos_list = positions_data.get("net", []) if positions_data else []
"""
new_positions_block = """
                    pos_list = cached_positions
"""
content = content.replace(old_positions_block, new_positions_block)

old_holdings_block = """
                try:
                    holdings_list = broker.get_holdings()
                except Exception as e:
                    logger.error(f"Failed to fetch holdings for broadcast: {e}")
                    holdings_list = []
"""
new_holdings_block = """
                holdings_list = cached_holdings
                for h in holdings_list:
                    sym = h.get("tradingsymbol")
                    for w in watchlist_payload:
                        if w["symbol"] == sym:
                            h["last_price"] = w["ltp"]
                            break
"""
content = content.replace(old_holdings_block, new_holdings_block)

with open("app/main.py", "w") as f:
    f.write(content)
print("Updated main.py")
