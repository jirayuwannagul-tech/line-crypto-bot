import os
from dotenv import load_dotenv

load_dotenv()

print("LINE_CHANNEL_SECRET:", os.getenv("LINE_CHANNEL_SECRET"))
print("LINE_CHANNEL_ACCESS_TOKEN:", os.getenv("LINE_CHANNEL_ACCESS_TOKEN")[:20] + "...")
print("LINE_USER_ID:", os.getenv("LINE_USER_ID"))
