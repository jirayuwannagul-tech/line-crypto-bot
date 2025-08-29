import os

def test_dotenv_loaded_flag():
    assert os.getenv("DOTENV_LOADED") == "1"

def test_line_env_exists():
    assert bool(os.getenv("LINE_CHANNEL_SECRET"))
    assert bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    assert bool(os.getenv("LINE_USER_ID"))
