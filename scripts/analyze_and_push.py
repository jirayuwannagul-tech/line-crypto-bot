
# วิเคราะห์ BTC แล้วส่งผลไป LINE (push)
# ใช้ ENV: LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID
# ใช้: python scripts/analyze_and_push.py --symbol BTCUSDT --tf 1D


import os, argparse
from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators
from app.analysis.dow import analyze_dow
from app.analysis.elliott import analyze_elliott
from app.analysis.scenarios import analyze_scenarios
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage

def push_text(to: str, text: str):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token: raise RuntimeError("ENV LINE_CHANNEL_ACCESS_TOKEN is empty")
    cfg = Configuration(access_token=token)
    with ApiClient(cfg) as api_client:
        api = MessagingApi(api_client)
        api.push_message(PushMessageRequest(to=to, messages=[TextMessage(text=text)]))

def main(symbol: str, tf: str, to: str):
    df = get_data(symbol, tf)
    d  = apply_indicators(df)
    dow = analyze_dow(d)
    ell = analyze_elliott(d); ell_targets = ell.get("targets", {})
    sce = analyze_scenarios(d, symbol=symbol, tf=tf)

    msg = (
        f"{symbol} {tf} (สรุป)\n"
        f"• Dow: {dow.get('trend_primary')} / {dow.get('trend_secondary')} (conf {dow.get('confidence')})\n"
        f"• Elliott: {ell.get('pattern')} → next {ell.get('next',{}).get('stage')} ({ell.get('next',{}).get('direction')})\n"
        f"  เป้ารีเทรซ: "
        f"{ell_targets.get('post_impulse_retrace_38.2%', '—')}–{ell_targets.get('post_impulse_retrace_61.8%', '—')}\n"
        f"• Scenarios: ขึ้น {sce['percent']['up']}% / ลง {sce['percent']['down']}% / Side {sce['percent']['side']}%\n"
        f"• Notes: {', '.join(sce.get('rationale', [])[:3])}"
    )
    push_text(to, msg)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="1D")
    ap.add_argument("--to", default=os.getenv("LINE_USER_ID",""))
    args = ap.parse_args()
    if not args.to:
        raise RuntimeError("ต้องระบุ --to หรือเซ็ต ENV LINE_USER_ID")
    main(args.symbol, args.tf, args.to)
