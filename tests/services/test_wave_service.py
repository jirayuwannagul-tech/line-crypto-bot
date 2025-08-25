# tests/services/test_wave_service.py
def test_analyze_wave_includes_weekly_bias_in_message(monkeypatch):
    import pandas as pd, numpy as np, datetime as dt
    from app.services import wave_service

    # fake get_data: สร้าง df สำหรับทั้ง 1D และ 1W
    def _fake_get_data(symbol, tf, xlsx_path=None):
        n = 30
        idx = pd.date_range(end=dt.datetime(2025, 8, 25), periods=n, freq='D' if tf == '1D' else 'W')
        return pd.DataFrame({
            'timestamp': idx,
            'open':  np.linspace(100,110,n),
            'high':  np.linspace(101,111,n),
            'low':   np.linspace( 99,109,n),
            'close': np.linspace(100,110,n),
            'volume':np.linspace(1000,2000,n),
        })

    # fake weekly classify: ใส่ weekly_bias='up'
    def _fake_classify_weekly(df, timeframe='1W', weekly_det=None):
        return {'pattern':'IMPULSE','kind':'IMPULSE_PROGRESS','current':{'direction':'up','weekly_bias':'up'}}

    # fake scenarios: ให้ payload พื้นฐาน
    def _fake_analyze_scenarios(df, symbol='BTCUSDT', tf='1D', cfg=None, weekly_ctx=None):
        return {'percent':{'up':50,'down':30,'side':20}, 'levels':{}, 'rationale':['fake'], 'meta':{'symbol':symbol,'tf':tf}}

    monkeypatch.setattr(wave_service, 'get_data', _fake_get_data)
    monkeypatch.setattr(wave_service, 'classify_elliott_with_kind', _fake_classify_weekly)
    monkeypatch.setattr(wave_service, 'analyze_scenarios', _fake_analyze_scenarios)

    payload = wave_service.analyze_wave('BTCUSDT','1D')
    msg = wave_service.build_brief_message(payload)
    assert '[UP 1W]' in msg.splitlines()[0]
