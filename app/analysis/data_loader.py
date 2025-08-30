import requests
import pandas as pd

def get_data(symbol: str, timeframe: str, limit: int = 100):
    """
    ดึงข้อมูล OHLCV จาก Binance API (หรือ Exchange อื่นๆ)
    :param symbol: ชื่อคู่เหรียญ เช่น 'BTC/USDT'
    :param timeframe: ระยะเวลา เช่น '1h', '1d'
    :param limit: จำนวนข้อมูลที่จะดึง
    :return: DataFrame ของข้อมูล OHLCV
    """
    url = f'https://api.binance.com/api/v1/klines'
    params = {
        'symbol': symbol.replace('/', ''),
        'interval': timeframe,
        'limit': limit
    }

    # ส่งคำขอไปยัง API
    response = requests.get(url, params=params)
    
    # ถ้าคำขอสำเร็จ
    if response.status_code == 200:
        data = response.json()
        
        # แปลงข้อมูลให้เป็น DataFrame
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        
        # แปลงเวลาเป็นวันที่
        df['timestamp'] = df['timestamp'].dt.isoformat()
        
        return df
    else:
        raise Exception(f"Error fetching data: {response.status_code}")
