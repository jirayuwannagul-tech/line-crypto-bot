import os, sys
from dotenv import load_dotenv, find_dotenv

def _load_env():
    print("[sitecustomize] CWD =", os.getcwd(), file=sys.stderr)
    print("[sitecustomize] sys.path[0] =", sys.path[0], file=sys.stderr)

    dotenv_path = ".env"
    if not os.path.isfile(dotenv_path):
        found = find_dotenv(usecwd=True)
        print("[sitecustomize] find_dotenv ->", found, file=sys.stderr)
        if found:
            dotenv_path = found

    if os.path.isfile(dotenv_path):
        print("[sitecustomize] loading .env from", dotenv_path, file=sys.stderr)
        load_dotenv(dotenv_path, override=False)
        os.environ["DOTENV_LOADED"] = "1"
    else:
        print("[sitecustomize] .env not found", file=sys.stderr)

try:
    if os.environ.get("DOTENV_LOADED") != "1":
        _load_env()
except Exception as e:
    print(f"[sitecustomize] dotenv load error: {e}", file=sys.stderr)
