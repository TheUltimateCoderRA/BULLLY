from dotenv import load_dotenv
import os
import requests as rq

load_dotenv()

def dailyPrices(tickers, interval="12years"):
    
    dailyPrices = []
    
    def unpackResponse(data):
        ticker = data.get("meta", {}).get("symbol", "UNKNOWN")
        for row in data.get("values", []):
            trade_date = row.get("datetime")
            open_val = float(row.get("open", 0))
            high_val = float(row.get("high", 0))
            low_val = float(row.get("low", 0))
            close_val = float(row.get("close", 0))
            volume_val = int(row.get("volume", 0))

        return {
            "ticker": ticker,
            "trade_date": trade_date,
            "open_val": open_val,
            "high_val": high_val,
            "low_val": low_val,
            "close_val": close_val,
            "volume_val": volume_val
        }

    key = os.getenv("twelvedataKey")
    url = "https://api.twelvedata.com/time_series"

    for ticker in tickers:
        params = {
            "symbol": ticker,
            "interval": interval,
            "apikey": key
        }
        response = rq.get(url, params=params)
        data = response.json()

        unpacked = unpackResponse(data)
        dailyPrices.append(unpacked)

    return dailyPrices


