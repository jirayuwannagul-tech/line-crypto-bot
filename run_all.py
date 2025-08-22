import subprocess

print(">>> Step 1: Running build_historical_binance.py ...")
subprocess.run(["python", "scripts/build_historical_binance.py"], check=True)

print(">>> Step 2: Running push_btc_hourly.py ...")
subprocess.run(["python", "-m", "jobs.push_btc_hourly"], check=True)

print(">>> All tasks completed successfully ✅")

