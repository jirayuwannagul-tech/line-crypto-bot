from app.scheduler.runner import tick_once
import asyncio

async def main():
    await tick_once(symbols=["BTC", "ETH", "ETC"], dry_run=False)

if __name__ == "__main__":
    asyncio.run(main())
