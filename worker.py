import asyncio
from app.analysis.timeframes import start_timeframe_service

PAIRS = [("BTCUSDT", "1m"), ("BTCUSDT", "1h")]

async def main():
    await start_timeframe_service(PAIRS)
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
