import data.prices

tickers = ["AAPL", "MSFT", "GOOGL"]

dailyPrices = data.prices.dailyPrices(tickers, "1day")

print(dailyPrices)