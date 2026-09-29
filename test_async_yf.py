import asyncio
import yfinance as yf
import time

async def fetch_symbol(sym):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: yf.download(sym, period="1d", interval="1m", progress=False))

async def main():
    symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
    start = time.time()
    tasks = [fetch_symbol(sym) for sym in symbols]
    results = await asyncio.gather(*tasks)
    print("Time taken:", time.time() - start)
    for r in results:
        print("Rows:", len(r))

asyncio.run(main())
