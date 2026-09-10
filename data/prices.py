from dotenv import load_dotenv
import os
import requests as rq
import time

load_dotenv()

def dailyPrices(tickers, interval="1day", years=12):
    
    results = []
    
    def unpackResponse(data):
        ticker = data.get("meta", {}).get("symbol", "UNKNOWN")
        rows = []
        for row in data.get("values", []):
            rows.append({
                "ticker": ticker,
                "trade_date": row.get("datetime"),
                "open_val": float(row.get("open", 0)),
                "high_val": float(row.get("high", 0)),
                "low_val": float(row.get("low", 0)),
                "close_val": float(row.get("close", 0)),
                "volume_val": int(row.get("volume", 0))
            })
        return rows

    key = os.getenv("twelvedataKey")
    url = "https://api.twelvedata.com/time_series"

    for ticker in tickers:
        params = {
            "symbol": ticker,
            "interval": interval,
            "outputsize": years*252,
            "apikey": key
        }
        response = rq.get(url, params=params)
        data = response.json()

        unpacked = unpackResponse(data)
        results.extend(unpacked)

        time.sleep(8)

    return results