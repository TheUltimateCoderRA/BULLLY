import os
import re
import pandas as pd
from dotenv import load_dotenv
from edgar import Company, set_identity

load_dotenv()


def fundamentals(tickers):
    email = os.getenv("userEmail")
    if not email:
        raise ValueError("userEmail not found in environment variables.")

    set_identity(email)
    results = []

    def periodColumns(df):
        cols = []
        for col in df.columns:
            if re.match(r"^\d{4}-\d{2}-\d{2}", str(col)):
                cols.append(col)
        return cols

    def normalizePeriodKey(periodCol):
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(periodCol))
        return match.group(1) if match else str(periodCol)

    def findPeriodCol(df, periodKey):
        for col in periodColumns(df):
            if normalizePeriodKey(col) == periodKey:
                return col
        return None

    def lookupValue(df, periodCol, labels):
        if periodCol is None or periodCol not in df.columns:
            return 0

        labelSet = {label.lower() for label in labels}
        for _, row in df.iterrows():
            if bool(row.get("dimension", False)) or bool(row.get("abstract", False)):
                continue

            candidates = [
                str(row.get("label", "") or "").lower(),
                str(row.get("standard_concept", "") or "").lower(),
            ]
            if not any(candidate in labelSet for candidate in candidates):
                continue

            value = row.get(periodCol)
            if pd.isna(value):
                return 0
            return value
        return 0

    def toNumber(value, cast=float):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return cast(0)
        try:
            return cast(value)
        except (TypeError, ValueError):
            return cast(0)

    def parsePeriod(periodKey, periodCol):
        year, month, day = periodKey.split("-")
        reportDate = periodKey
        fiscalYear = int(year)
        fiscalQuarter = 4 if "(FY)" in str(periodCol) else ((int(month) - 1) // 3) + 1
        return reportDate, fiscalYear, fiscalQuarter

    def unpackResponse(ticker, incomeStatement, balanceSheet, cashFlow):
        incomeDf = incomeStatement.to_dataframe()
        balanceDf = balanceSheet.to_dataframe()
        cashDf = cashFlow.to_dataframe()

        periodKeys = set()
        for df in (incomeDf, balanceDf, cashDf):
            for col in periodColumns(df):
                periodKeys.add(normalizePeriodKey(col))

        records = []
        for periodKey in sorted(periodKeys, reverse=True):
            incomeCol = findPeriodCol(incomeDf, periodKey)
            balanceCol = findPeriodCol(balanceDf, periodKey)
            cashCol = findPeriodCol(cashDf, periodKey)
            periodHint = incomeCol or balanceCol or cashCol or periodKey
            reportDate, fiscalYear, fiscalQuarter = parsePeriod(periodKey, periodHint)

            revenue = toNumber(lookupValue(incomeDf, incomeCol, ["net sales", "total revenue", "revenue"]))
            grossProfit = toNumber(lookupValue(incomeDf, incomeCol, ["gross margin", "gross profit", "grossprofit"]))
            operatingIncome = toNumber(lookupValue(incomeDf, incomeCol, ["operating income", "operatingincomeloss"]))
            netIncome = toNumber(lookupValue(incomeDf, incomeCol, ["net income", "netincome"]))
            eps = toNumber(lookupValue(incomeDf, incomeCol, [
                "diluted (in dollars per share)",
                "earnings per share diluted",
            ]))

            totalAssets = toNumber(lookupValue(balanceDf, balanceCol, ["total assets", "assets"]))
            totalLiabilities = toNumber(lookupValue(balanceDf, balanceCol, ["total liabilities", "liabilities"]))
            cashAndEquivalents = toNumber(lookupValue(balanceDf, balanceCol, [
                "cash and cash equivalents",
                "cashandmarketablesecurities",
            ]))
            sharesOutstanding = toNumber(lookupValue(balanceDf, balanceCol, [
                "common stock, shares outstanding (in shares)",
                "sharesyearend",
                "sharesissued",
            ]), cast=int)

            commercialPaper = toNumber(lookupValue(balanceDf, balanceCol, ["commercial paper", "shorttermdebt"]))
            currentTermDebt = toNumber(lookupValue(balanceDf, balanceCol, ["currentportionoflongtermdebt"]))
            longTermDebt = toNumber(lookupValue(balanceDf, balanceCol, ["longtermdebt"]))
            if currentTermDebt == 0 and longTermDebt == 0:
                # Fallback when standard_concept is missing and both lines share label "Term debt".
                termDebtTotal = 0
                if balanceCol is not None:
                    for _, row in balanceDf.iterrows():
                        if bool(row.get("dimension", False)) or bool(row.get("abstract", False)):
                            continue
                        if str(row.get("label", "") or "").lower() != "term debt":
                            continue
                        value = row.get(balanceCol)
                        if not pd.isna(value):
                            termDebtTotal += toNumber(value)
                totalDebt = commercialPaper + termDebtTotal
            else:
                totalDebt = commercialPaper + currentTermDebt + longTermDebt

            operatingCashFlow = toNumber(lookupValue(cashDf, cashCol, [
                "cash generated by operating activities",
                "netcashfromoperatingactivities",
            ]))
            capex = toNumber(lookupValue(cashDf, cashCol, [
                "payments for acquisition of property, plant and equipment",
                "capitalexpenses",
            ]))
            freeCashFlow = operatingCashFlow + capex if capex <= 0 else operatingCashFlow - capex

            records.append({
                "ticker": ticker,
                "reportDate": reportDate,
                "fiscalYear": fiscalYear,
                "fiscalQuarter": fiscalQuarter,
                "revenue": revenue,
                "grossProfit": grossProfit,
                "operatingIncome": operatingIncome,
                "netIncome": netIncome,
                "eps": eps,
                "totalAssets": totalAssets,
                "totalLiabilities": totalLiabilities,
                "totalDebt": totalDebt,
                "cashAndEquivalents": cashAndEquivalents,
                "freeCashFlow": freeCashFlow,
                "sharesOutstanding": sharesOutstanding,
                "marketCap": 0,
                "peRatio": 0.0,
                "pegRatio": 0.0,
                "priceToSales": 0.0,
                "priceToBook": 0.0,
                "revenueGrowth": 0.0,
                "earningsGrowth": 0.0,
            })

        # records are newest-first; growth compares each period to the next older one
        for index in range(len(records) - 1):
            current = records[index]
            prior = records[index + 1]
            if prior["revenue"]:
                current["revenueGrowth"] = (current["revenue"] - prior["revenue"]) / abs(prior["revenue"])
            if prior["netIncome"]:
                current["earningsGrowth"] = (current["netIncome"] - prior["netIncome"]) / abs(prior["netIncome"])

        return records

    for ticker in tickers:
        company = Company(ticker)
        financials = company.get_financials()

        incomeStatement = financials.income_statement()
        balanceSheet = financials.balance_sheet()
        cashFlow = financials.cash_flow_statement()

        results.extend(unpackResponse(ticker, incomeStatement, balanceSheet, cashFlow))

    return results
