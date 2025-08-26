# app/config/symbols.py
# ============================================
# LAYER: SYMBOL CONFIG / MAPPING
# ============================================

# ===== SYMBOL MAP (Ticker → Provider ID) =====
SYMBOL_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "ADA": "cardano",
    "XRP": "ripple",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "SAND": "the-sandbox",
}

# ===== SUPPORTED LIST =====
SUPPORTED = sorted(SYMBOL_MAP.keys())

# ===== HELPER FUNCTIONS =====
def is_supported(symbol: str) -> bool:
    if not symbol:
        return False
    return symbol.upper() in SYMBOL_MAP

def resolve_symbol(symbol: str) -> str:
    """
    รับ 'BTC' → คืน 'bitcoin' (id สำหรับ API ภายนอก)
    ถ้าไม่รองรับจะ raise ValueError
    """
    if not is_supported(symbol):
        raise ValueError(f"Unsupported symbol: {symbol!r}. Supported: {', '.join(SUPPORTED)}")
    return SYMBOL_MAP[symbol.upper()]
