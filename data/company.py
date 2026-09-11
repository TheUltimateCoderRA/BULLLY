import os
import re

import pandas as pd
from dotenv import load_dotenv
from edgar import Company, set_identity

load_dotenv()

# Canonical concept aliases used by edgartools EntityFacts statements.
# Order matters: first hit wins.
CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTaxAbstract",
    ],
    "cogs": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
    ],
    "grossProfit": [
        "GrossProfit",
        "GrossProfit_Calculated",
    ],
    "operatingIncome": [
        "OperatingIncomeLoss",
    ],
    "netIncome": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "eps": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
    ],
    "shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
    "totalAssets": [
        "Assets",
    ],
    "totalLiabilities": [
        "Liabilities",
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "operatingCashFlow": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    "debtParts": [
        "LongTermDebtNoncurrent",
        "LongTermDebtCurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "CommercialPaper",
        "ShortTermBorrowings",
        "NotesPayableCurrent",
        "LinesOfCreditCurrent",
        "DebtCurrent",
    ],
}


def fundamentals(tickers, periods=8):
    email = os.getenv("userEmail")
    if not email:
        raise ValueError("userEmail not found in environment variables.")

    set_identity(email)
    results = []

    def fyColumns(df):
        if df is None or df.empty:
            return []
        cols = [col for col in df.columns if re.match(r"^FY\s+\d{4}$", str(col))]
        # Newest fiscal year first.
        return sorted(cols, key=lambda col: int(str(col).split()[-1]), reverse=True)

    def pick(df, fyCol, aliases):
        if df is None or fyCol is None or fyCol not in getattr(df, "columns", []):
            return None

        for concept in aliases:
            if concept not in df.index:
                continue
            value = df.loc[concept, fyCol]
            # Duplicate index rows can return a Series.
            if isinstance(value, pd.Series):
                value = value.dropna()
                if value.empty:
                    continue
                value = value.iloc[0]
            if pd.isna(value):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def sumParts(df, fyCol, aliases):
        total = 0.0
        found = False
        for concept in aliases:
            value = pick(df, fyCol, [concept])
            if value is None:
                continue
            total += value
            found = True
        return total if found else None

    def toInt(value):
        if value is None:
            return None
        try:
            return int(round(value))
        except (TypeError, ValueError):
            return None

    def reportDates(facts, fyCols):
        """Map FY columns to period-end dates using balance-sheet instant facts."""
        mapping = {col: None for col in fyCols}
        if not fyCols:
            return mapping
        try:
            series = facts.time_series("Assets", periods=max(24, len(fyCols) * 4))
            ends = []
            seen = set()
            for end in sorted(series["period_end"].dropna().unique(), reverse=True):
                key = str(end)[:10]
                if key in seen:
                    continue
                seen.add(key)
                ends.append(key)
            for index, col in enumerate(fyCols):
                if index < len(ends):
                    mapping[col] = ends[index]
        except Exception:
            pass
        return mapping

    def unpackFacts(ticker, company, facts):
        incomeDf = facts.income_statement(periods=periods, as_dataframe=True, annual=True)
        balanceDf = facts.balance_sheet(periods=periods, as_dataframe=True, annual=True)
        cashDf = facts.cash_flow_statement(periods=periods, as_dataframe=True, annual=True)

        fyCols = []
        seen = set()
        for df in (incomeDf, balanceDf, cashDf):
            for col in fyColumns(df):
                if col not in seen:
                    seen.add(col)
                    fyCols.append(col)
        fyCols = sorted(fyCols, key=lambda col: int(str(col).split()[-1]), reverse=True)

        dates = reportDates(facts, fyCols)
        records = []

        for fyCol in fyCols:
            fiscalYear = int(str(fyCol).split()[-1])
            reportDate = dates.get(fyCol)

            revenue = pick(incomeDf, fyCol, CONCEPTS["revenue"])
            cogs = pick(incomeDf, fyCol, CONCEPTS["cogs"])
            grossProfit = pick(incomeDf, fyCol, CONCEPTS["grossProfit"])
            if grossProfit is None and revenue is not None and cogs is not None:
                grossProfit = revenue - cogs

            operatingIncome = pick(incomeDf, fyCol, CONCEPTS["operatingIncome"])
            netIncome = pick(incomeDf, fyCol, CONCEPTS["netIncome"])
            eps = pick(incomeDf, fyCol, CONCEPTS["eps"])

            sharesOutstanding = toInt(pick(incomeDf, fyCol, CONCEPTS["shares"]))
            if sharesOutstanding is None:
                sharesOutstanding = toInt(pick(balanceDf, fyCol, CONCEPTS["shares"]))
            if sharesOutstanding is None and fyCol == fyCols[0]:
                sharesOutstanding = toInt(getattr(facts, "shares_outstanding", None))

            totalAssets = pick(balanceDf, fyCol, CONCEPTS["totalAssets"])
            totalLiabilities = pick(balanceDf, fyCol, CONCEPTS["totalLiabilities"])
            equity = pick(balanceDf, fyCol, CONCEPTS["equity"])
            if totalLiabilities is None and totalAssets is not None and equity is not None:
                totalLiabilities = totalAssets - equity

            cashAndEquivalents = pick(balanceDf, fyCol, CONCEPTS["cash"])
            totalDebt = sumParts(balanceDf, fyCol, CONCEPTS["debtParts"])

            operatingCashFlow = pick(cashDf, fyCol, CONCEPTS["operatingCashFlow"])
            capex = pick(cashDf, fyCol, CONCEPTS["capex"])
            if operatingCashFlow is None or capex is None:
                freeCashFlow = None
            else:
                freeCashFlow = operatingCashFlow - abs(capex)

            records.append({
                "ticker": ticker,
                "report_date": reportDate,
                "fiscal_year": fiscalYear,
                "fiscal_quarter": 4,
                "revenue": revenue,
                "gross_profit": grossProfit,
                "operating_income": operatingIncome,
                "net_income": netIncome,
                "eps": eps,
                "total_assets": totalAssets,
                "total_liabilities": totalLiabilities,
                "total_debt": totalDebt,
                "cash_and_equivalents": cashAndEquivalents,
                "free_cash_flow": freeCashFlow,
                "shares_outstanding": sharesOutstanding,
                "market_cap": None,
                "pe_ratio": None,
                "peg_ratio": None,
                "price_to_sales": None,
                "price_to_book": None,
                "revenue_growth": None,
                "earnings_growth": None,
            })

        for index in range(len(records) - 1):
            current = records[index]
            prior = records[index + 1]
            if current["revenue"] is not None and prior["revenue"]:
                current["revenue_growth"] = (
                    (current["revenue"] - prior["revenue"]) / abs(prior["revenue"])
                )
            if current["net_income"] is not None and prior["net_income"]:
                current["earnings_growth"] = (
                    (current["net_income"] - prior["net_income"])
                    / abs(prior["net_income"])
                )

        return records

    for ticker in tickers:
        try:
            company = Company(ticker)
            facts = company.get_facts()
            if facts is None:
                continue
            results.extend(unpackFacts(ticker, company, facts))
        except Exception:
            # Keep batch running; caller/tests can detect missing tickers.
            continue

    return results
