import asyncio
import yfinance as yf
import time

async def fetch_fast(sym):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: yf.Ticker(sym).fast_info.last_price)

async def main():
    symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
    start = time.time()
    tasks = [fetch_fast(sym) for sym in symbols]
    results = await asyncio.gather(*tasks)
    print("Time taken:", time.time() - start)
    print(results)

asyncio.run(main())
