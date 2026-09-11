"""
Smoke-test fundamentals() across a broad ticker universe.

Prints only pass/fail summaries (no full financial dumps).

Usage:
  python test.py
  python test.py --limit 20
  python test.py --tickers AAPL MSFT JPM
"""

from __future__ import annotations

import argparse
import traceback
from collections import defaultdict

from data.company import fundamentals

# Intentionally not scraped yet — excluded from field scoring.
SKIP_FIELDS = {
    "market_cap",
    "pe_ratio",
    "peg_ratio",
    "price_to_sales",
    "price_to_book",
}

# Always expected on the newest period when a filing parses.
CORE_FIELDS = [
    "ticker",
    "report_date",
    "fiscal_year",
    "fiscal_quarter",
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "eps",
    "total_assets",
    "total_liabilities",
    "total_debt",
    "cash_and_equivalents",
    "free_cash_flow",
    "shares_outstanding",
]

# Only scored when 2+ periods exist.
GROWTH_FIELDS = ["revenue_growth", "earnings_growth"]

# 300 liquid US tickers across sectors (tech, finance, healthcare, energy,
# consumer, industrial, telecom, utilities, REITs, mid-cap).
TICKERS = [
    # Mega / large tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "CSCO", "ACN", "IBM", "INTC", "AMD", "QCOM", "TXN", "INTU",
    "NOW", "AMAT", "MU", "LRCX", "KLAC", "SNPS", "CDNS", "ADI", "NXPI", "MCHP",
    "PANW", "CRWD", "FTNT", "SNOW", "PLTR", "DDOG", "NET", "ZS", "TEAM", "WDAY",
    "SHOP", "XYZ", "PYPL", "COIN", "UBER", "ABNB", "BKNG", "EA", "TTWO", "RBLX",
    # Communication / media
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "WBD", "PARA", "FOX",
    "FOXA", "LYV", "SPOT", "MTCH", "PINS", "SNAP", "TTD", "ROKU", "SIRI", "NWSA",
    # Financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "USB",
    "PNC", "TFC", "BK", "STT", "COF", "AIG", "MET", "PRU", "ALL", "TRV",
    "CB", "PGR", "AFL", "MMC", "AON", "ICE", "CME", "SPGI", "MCO", "MSCI",
    "V", "MA", "FIS", "FI", "GPN", "DFS", "SYF", "ALLY", "HOOD", "SOFI",
    # Healthcare / pharma / biotech
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "VRTX", "REGN", "MDT", "SYK", "BSX", "ISRG", "EW", "ZBH",
    "CI", "ELV", "CVS", "HUM", "MCK", "COR", "CAH", "HCA", "CNC", "MOH",
    "BIIB", "MRNA", "ILMN", "DXCM", "IDXX", "IQV", "A", "MTD", "WAT", "ALGN",
    # Consumer discretionary / staples
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD", "CMG", "YUM",
    "TJX", "ROST", "DG", "DLTR", "BBY", "ORLY", "AZO", "TSCO", "ULTA", "LULU",
    "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "GIS", "K", "SYY",
    "MDLZ", "HSY", "STZ", "TAP", "KR", "CVNA", "ETSY", "DECK", "DPZ", "POOL",
    # Industrials
    "CAT", "DE", "GE", "HON", "UNP", "UPS", "FDX", "BA", "LMT", "RTX",
    "NOC", "GD", "MMM", "EMR", "ETN", "ITW", "PH", "ROK", "CARR", "OTIS",
    "WM", "RSG", "CSX", "NSC", "DAL", "UAL", "LUV", "AAL", "PCAR", "CMI",
    "FAST", "GWW", "URI", "PWR", "JCI", "TT", "IR", "XYL", "DOV", "SWK",
    # Energy / materials
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL",
    "WMB", "KMI", "EPD", "ET", "LNG", "BKR", "FANG", "DVN", "CTRA", "OKE",
    "LIN", "APD", "SHW", "ECL", "DD", "DOW", "NEM", "FCX", "NUE", "STLD",
    # Utilities / real estate
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PEG", "ED", "XEL",
    "WEC", "ES", "AWK", "DTE", "EIX", "PPL", "FE", "AES", "CMS", "CNP",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "SPG", "O", "WELL", "DLR", "AVB",
    # Mid / growth / other liquid names
    "SMCI", "ARM", "APP", "MSTR", "DELL", "HPE", "HPQ", "NTAP", "WDC", "STX",
]


def isPresent(value) -> bool:
    return value is not None and value != ""


def scoreRecord(record: dict, hasPriorPeriod: bool) -> dict[str, bool]:
    scores = {}
    for field in CORE_FIELDS:
        scores[field] = isPresent(record.get(field))

    for field in GROWTH_FIELDS:
        if hasPriorPeriod:
            scores[field] = isPresent(record.get(field))
        # If only one period, growth is expected to be missing — do not score.

    return scores


def runTicker(ticker: str) -> dict:
    try:
        records = fundamentals([ticker])
    except Exception as exc:
        return {
            "ticker": ticker,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "periods": 0,
            "fieldScores": {},
            "failedFields": [],
            "passedFields": [],
        }

    if not records:
        return {
            "ticker": ticker,
            "status": "empty",
            "error": "no periods returned",
            "periods": 0,
            "fieldScores": {},
            "failedFields": CORE_FIELDS[:],
            "passedFields": [],
        }

    newest = records[0]
    scores = scoreRecord(newest, hasPriorPeriod=len(records) >= 2)
    failed = [field for field, ok in scores.items() if not ok]
    passed = [field for field, ok in scores.items() if ok]
    status = "pass" if not failed else "partial"

    return {
        "ticker": ticker,
        "status": status,
        "error": None,
        "periods": len(records),
        "reportDate": newest.get("report_date"),
        "fieldScores": scores,
        "failedFields": failed,
        "passedFields": passed,
    }


def printReport(results: list[dict]) -> None:
    total = len(results)
    errors = [r for r in results if r["status"] == "error"]
    empty = [r for r in results if r["status"] == "empty"]
    partial = [r for r in results if r["status"] == "partial"]
    passed = [r for r in results if r["status"] == "pass"]

    print("=" * 72)
    print("FUNDAMENTALS SMOKE TEST")
    print("=" * 72)
    print(f"Tickers tested : {total}")
    print(f"Full pass      : {len(passed)}")
    print(f"Partial        : {len(partial)}  (parsed, but some fields missing)")
    print(f"Empty          : {len(empty)}  (no records)")
    print(f"Errors         : {len(errors)}  (exception / fetch failed)")
    print(f"Skipped fields : {', '.join(sorted(SKIP_FIELDS))} (not scraped yet)")
    print()

    # Field fill rates across tickers that returned at least one period
    scored = [r for r in results if r["fieldScores"]]
    if scored:
        print("-" * 72)
        print("FIELD SUCCESS RATE (newest period only)")
        print("-" * 72)
        fieldHits = defaultdict(int)
        fieldTried = defaultdict(int)
        for result in scored:
            for field, ok in result["fieldScores"].items():
                fieldTried[field] += 1
                if ok:
                    fieldHits[field] += 1

        width = max(len(field) for field in fieldTried)
        for field in sorted(fieldTried):
            hits = fieldHits[field]
            tried = fieldTried[field]
            pct = 100.0 * hits / tried if tried else 0.0
            print(f"  {field:<{width}}  {hits:>4}/{tried:<4}  ({pct:5.1f}%)")
        print()

    def printTickerBlock(title: str, rows: list[dict], detail: str) -> None:
        if not rows:
            return
        print("-" * 72)
        print(f"{title} ({len(rows)})")
        print("-" * 72)
        for result in rows:
            if detail == "error":
                print(f"  FAIL  {result['ticker']:<6}  {result['error']}")
            elif detail == "empty":
                print(f"  FAIL  {result['ticker']:<6}  no periods")
            elif detail == "partial":
                missing = ", ".join(result["failedFields"])
                print(
                    f"  PART  {result['ticker']:<6}  "
                    f"periods={result['periods']}  "
                    f"date={result.get('reportDate')}  "
                    f"missing=[{missing}]"
                )
            elif detail == "pass":
                print(
                    f"  OK    {result['ticker']:<6}  "
                    f"periods={result['periods']}  "
                    f"date={result.get('reportDate')}  "
                    f"fields={len(result['passedFields'])}"
                )
        print()

    printTickerBlock("ERRORS", errors, "error")
    printTickerBlock("EMPTY", empty, "empty")
    printTickerBlock("PARTIAL (missing fields on newest period)", partial, "partial")
    printTickerBlock("FULL PASS", passed, "pass")

    # Compact miss matrix: which tickers failed which field
    if scored:
        print("-" * 72)
        print("FAILURES BY FIELD")
        print("-" * 72)
        misses = defaultdict(list)
        for result in scored:
            for field in result["failedFields"]:
                misses[field].append(result["ticker"])
        if not misses:
            print("  None — all scored fields present on every successful ticker.")
        else:
            for field in sorted(misses):
                tickers = ", ".join(misses[field])
                print(f"  {field}: {tickers}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test fundamentals() field coverage")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only test the first N tickers",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Override list with specific tickers",
    )
    parser.add_argument(
        "--verbose-errors",
        action="store_true",
        help="Print full tracebacks for ticker errors",
    )
    args = parser.parse_args()

    tickers = args.tickers or TICKERS
    if args.limit is not None:
        tickers = tickers[: args.limit]

    # De-dupe while preserving order
    seen = set()
    unique = []
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            unique.append(symbol)

    print(f"Running fundamentals smoke test on {len(unique)} tickers...\n")

    results = []
    for index, ticker in enumerate(unique, start=1):
        print(f"[{index}/{len(unique)}] {ticker} ...", flush=True)
        try:
            result = runTicker(ticker)
        except Exception as exc:
            result = {
                "ticker": ticker,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "periods": 0,
                "fieldScores": {},
                "failedFields": [],
                "passedFields": [],
            }
            if args.verbose_errors:
                traceback.print_exc()
        # Progress line rewrite with status
        status = result["status"].upper()
        extra = ""
        if result["status"] == "partial":
            extra = f" missing={result['failedFields']}"
        elif result["status"] == "error":
            extra = f" {result['error']}"
        print(f"[{index}/{len(unique)}] {ticker} -> {status}{extra}", flush=True)
        results.append(result)

    print()
    printReport(results)


if __name__ == "__main__":
    main()
