from dotenv import load_dotenv
import os
import requests as rq
import time
from datetime import datetime

load_dotenv()


def quarterlyFinancials(tickers, years=12, batchSize=5, delaySeconds=0.5):
    results = []
    cutoffYear = datetime.now().year - years

    def unpackResponse(rows, slugToField):
        unpacked = []
        for row in rows:
            rawDate = row.get("date", "")
            fiscalYear = None
            fiscalQuarter = None
            if "Q" in str(rawDate):
                parts = str(rawDate).split()
                if len(parts) == 2:
                    fiscalYear = int(parts[0])
                    fiscalQuarter = int(parts[1].replace("Q", ""))

            if fiscalYear is None or fiscalYear < cutoffYear:
                continue

            field = slugToField.get(row.get("metric"), row.get("metric"))

            unpacked.append({
                "ticker": row.get("ticker"),
                "reportDate": rawDate,
                "fiscalYear": fiscalYear,
                "fiscalQuarter": fiscalQuarter,
                "field": field,
                "value": row.get("value"),
            })
        return unpacked

    key = os.getenv("businessquantKey")
    url = "https://data.businessquant.com/historic"

    slugMap = {
        "revenue": "revenue",
        "gross_profit": "gross-profit",
        "operating_income": "operating-income",
        "net_income": "net-income",
        "eps": "eps-diluted",
        "total_assets": "assets",
        "total_liabilities": "total-liabilities",
        "total_debt": "total-debt",
        "cash_and_equivalents": "cash-and-equivalents",
        "free_cash_flow": "free-cash-flow",
        "shares_outstanding": "shares-outstanding",
        "total_equity": "total-equity",
        "revenue_growth": "revenue-growth-1y",
        "earnings_growth": "net-income-growth-1y",
        "market_cap": "market-capitalization",
        "pe_ratio": "price-to-earnings",
        "price_to_sales": "price-to-sales",
    }

    slugToField = {v: k for k, v in slugMap.items()}
    slugList = list(slugMap.values())

    for i in range(0, len(slugList), batchSize):
        slugBatch = slugList[i:i + batchSize]

        for j in range(0, len(tickers), batchSize):
            tickerBatch = tickers[j:j + batchSize]

            params = {
                "ticker": ",".join(tickerBatch),
                "slug": ",".join(slugBatch),
                "frequency": "quarterly",
                "period": "max",
                "api_key": key,
            }

            response = rq.get(url, params=params)
            data = response.json()

            if not isinstance(data, list):
                time.sleep(delaySeconds)
                continue

            unpacked = unpackResponse(data, slugToField)
            results.extend(unpacked)

            time.sleep(delaySeconds)

    return results