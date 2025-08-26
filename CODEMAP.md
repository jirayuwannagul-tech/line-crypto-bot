cat > CODEMAP.md <<'MD'
# CODEMAP — Line Crypto Bot

## โครงสร้างหลัก
- `app/` แอปหลัก (FastAPI + Logic)
  - `adapters/` ต่อภายนอก (LINE, ราคา, cache)
  - `analysis/` วิเคราะห์กราฟ (dow, elliott, fib, indicators, timeframes)
  - `engine/` รวมสัญญาณ → signal_engine.py
  - `features/` ฟีเจอร์ย่อย (alerts, replies)
  - `logic/` ตรรกะกลยุทธ์
  - `routers/` API routes (line, webhook, analyze, chat, health)
  - `services/` บริการ (news, notifier_line, wave_service ฯลฯ)
  - `utils/` เครื่องมือ (settings, time_tools, logging_tools)
  - `config/` ไฟล์คอนฟิก
- `scripts/` คำสั่ง CLI
- `backtest/` โค้ด+ผล backtest
- `jobs/` งานตามเวลา
- `tests/` pytest
- `reports/` กราฟ/ผลเทส
- `render.yaml` `Procfile` `worker.py` สำหรับ deploy

## API สำคัญ
- `/health` → health check  
- `/webhook/line` → รับข้อความ LINE  
- `/analyze/*` → วิเคราะห์  
- `app/main.py` → create_app รวม routes  

## จุดใช้งานบ่อย
- วิเคราะห์ TF: `scripts/analyze_multi_tf.py`  
- วิเคราะห์+ส่งไลน์: `scripts/analyze_and_push.py`, `scripts/push_line_report.py`  
- วาดกราฟ: `scripts/plot_chart.py`  
- ส่งข้อความทดสอบ LINE: `scripts/send_line_message.py`  
- งานเวลา: `jobs/*.py`, `app/scheduler/runner.py`  

## ข้อมูล
- `app/data/` : CSV + historical.xlsx  
- ตัวดึงราคา: services/price_provider_binance.py  

## ทดสอบ
- ทั้งหมด: `pytest -q`  
- เฉพาะไฟล์: `pytest tests/analysis/test_elliott.py -q`  
- ตรวจ webhook: `pytest tests/routers/test_line_webhook_price.py -q`  

## Backtest
- หลัก: `backtest/runner.py`  
- ตัวอย่าง:
```bash
python backtest/runner.py --mode elliott
