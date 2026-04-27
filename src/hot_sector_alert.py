import os
import sys
import html
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

from config import (
    BENCHMARK,
    SECTOR_ETFS,
    INDUSTRY_ETFS,
    MIN_PRICE,
    MIN_DOLLAR_VOLUME,
    TOP_SECTORS,
    TOP_INDUSTRIES,
    TOP_STOCKS_OVERALL,
    TARGET_PACIFIC_TIMES,
    WEEKDAYS_ONLY,
)

PACIFIC = pytz.timezone("America/Los_Angeles")


def now_pacific():
    return datetime.now(PACIFIC)


def should_send_now(force=False):
    if force:
        return True

    now = now_pacific()

    if WEEKDAYS_ONLY and now.weekday() >= 5:
        return False

    return now.strftime("%H:%M") in TARGET_PACIFIC_TIMES


def normalize_ticker(t):
    return str(t).strip().replace(".", "-")


def safe_pct(x):
    try:
        if pd.isna(x) or not np.isfinite(x):
            return 0.0
        return float(x) * 100
    except:
        return 0.0


# =========================
# SECTOR FIX (CRITICAL)
# =========================
def map_hot_sector_to_gics(sector):
    mapping = {
        "Technology": "Information Technology",
        "Consumer Discretionary": "Consumer Discretionary",
        "Materials": "Materials",
    }
    return mapping.get(sector, sector)


# =========================
# INDUSTRY MATCH FIX
# =========================
def is_hot_industry(stock_industry, hot_industries):
    s = stock_industry.lower()

    for h in hot_industries:
        h = h.lower()

        if "semi" in h and "semiconductor" in s:
            return True
        if "software" in h and "software" in s:
            return True
        if "internet" in h and ("internet" in s or "interactive" in s or "retail" in s):
            return True
        if "oil" in h and ("oil" in s or "gas" in s):
            return True
        if "solar" in h and ("renewable" in s or "electrical" in s):
            return True

    return False


def fetch_sp500_constituents():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)

    from io import StringIO

    tables = pd.read_html(StringIO(res.text))
    df = tables[0]

    df["Ticker"] = df["Symbol"].apply(normalize_ticker)

    df = df.rename(
        columns={
            "Security": "Name",
            "GICS Sector": "Sector",
            "GICS Sub-Industry": "Industry",
        }
    )

    return df[["Ticker", "Name", "Sector", "Industry"]]


def download_prices(tickers, period="3mo"):
    return yf.download(
        tickers,
        period=period,
        group_by="ticker",
        auto_adjust=True,
        progress=False,
    )


def extract(df, ticker):
    if isinstance(df.columns, pd.MultiIndex):
        return df[ticker].dropna()
    return df.dropna()


def etf_metrics(etfs):
    tickers = list(etfs.values()) + [BENCHMARK]
    df = download_prices(tickers)

    spy = extract(df, BENCHMARK)

    spy_1d = spy["Close"].pct_change().iloc[-1]
    spy_5d = spy["Close"].pct_change(5).iloc[-1]

    rows = []

    for name, t in etfs.items():
        d = extract(df, t)
        c = d["Close"]
        v = d["Volume"]

        r1 = c.pct_change().iloc[-1]
        r5 = c.pct_change(5).iloc[-1]

        rvol = v.iloc[-1] / v.rolling(20).mean().iloc[-1]

        score = (
            safe_pct(r1) * 3
            + safe_pct(r5) * 2
            + safe_pct(r1 - spy_1d) * 2
            + rvol
        )

        rows.append(
            dict(Group=name, ETF=t, **{"1D%": safe_pct(r1), "5D%": safe_pct(r5), "RVOL": rvol, "Score": score})
        )

    return pd.DataFrame(rows).sort_values("Score", ascending=False)


def stock_metrics(universe, hot_sectors, hot_industries):
    mapped = [map_hot_sector_to_gics(s) for s in hot_sectors]

    pool = universe[universe["Sector"].isin(mapped)]

    tickers = pool["Ticker"].tolist()

    df = download_prices(tickers + [BENCHMARK], "6mo")
    spy = extract(df, BENCHMARK)

    spy_1d = spy["Close"].pct_change().iloc[-1]

    rows = []

    meta = pool.set_index("Ticker").to_dict("index")

    for t in tickers:
        d = extract(df, t)

        if len(d) < 50:
            continue

        c = d["Close"]
        v = d["Volume"]

        price = c.iloc[-1]
        dv = price * v.rolling(20).mean().iloc[-1]

        if price < MIN_PRICE or dv < MIN_DOLLAR_VOLUME:
            continue

        r1 = c.pct_change().iloc[-1]
        r5 = c.pct_change(5).iloc[-1]
        r20 = c.pct_change(20).iloc[-1]

        rvol = v.iloc[-1] / v.rolling(20).mean().iloc[-1]

        score = (
            safe_pct(r1) * 3
            + safe_pct(r5) * 2
            + safe_pct(r20)
            + safe_pct(r1 - spy_1d) * 2
            + rvol * 2
        )

        industry = meta[t]["Industry"]
        industry_hot = is_hot_industry(industry, hot_industries)

        if industry_hot:
            score += 25

        rows.append(
            dict(
                Ticker=t,
                Name=meta[t]["Name"],
                Sector=meta[t]["Sector"],
                Industry=industry,
                IndustryHot=industry_hot,
                **{"1D%": safe_pct(r1), "5D%": safe_pct(r5), "20D%": safe_pct(r20), "RVOL": rvol, "DollarVolM": dv / 1e6, "Score": score},
            )
        )

    return pd.DataFrame(rows).sort_values("Score", ascending=False)


def build_message():
    run_time = now_pacific().strftime("%a %Y-%m-%d %I:%M %p PT")

    universe = fetch_sp500_constituents()

    sectors = etf_metrics(SECTOR_ETFS)
    industries = etf_metrics(INDUSTRY_ETFS)

    hot_sectors = sectors.head(TOP_SECTORS)["Group"].tolist()
    hot_industries = industries.head(TOP_INDUSTRIES)["Group"].tolist()

    leaders = stock_metrics(universe, hot_sectors, hot_industries)

    # REMOVE DUPLICATES
    top_sector = leaders.head(TOP_STOCKS_OVERALL)
    remaining = leaders[~leaders["Ticker"].isin(top_sector["Ticker"])]

    hot_industry_leaders = remaining[remaining["IndustryHot"]].head(10)

    msg = []
    msg.append("🔥 <b>Hot Sector / Industry / Stock Leaders</b>")
    msg.append(f"<b>Run:</b> {run_time}")

    msg.append("\n<b>Top Hot Sectors</b>")
    for _, r in sectors.head(TOP_SECTORS).iterrows():
        msg.append(f"• {r['Group']} ({r['ETF']})")

    msg.append("\n<b>Top Hot Industries</b>")
    for _, r in industries.head(TOP_INDUSTRIES).iterrows():
        msg.append(f"• {r['Group']} ({r['ETF']})")

    msg.append("\n<b>Top Stock Leaders in Hot Sectors</b>")
    for _, r in top_sector.iterrows():
        msg.append(
            f"• <b>{r['Ticker']}</b> — {r['Sector']}"
            f"{' 🔥Industry' if r['IndustryHot'] else ''} | 5D {r['5D%']:+.1f}%"
        )

    msg.append("\n<b>Top Stock Leaders in Hot Industries</b>")
    if hot_industry_leaders.empty:
        msg.append("None")
    else:
        for _, r in hot_industry_leaders.iterrows():
            msg.append(
                f"• <b>{r['Ticker']}</b> — {r['Industry']} | 5D {r['5D%']:+.1f}%"
            )

    return "\n".join(msg)


def send_telegram(msg):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    requests.post(url, json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})


def main():
    force = "--force" in sys.argv or os.environ.get("FORCE_SEND") == "true"

    if not should_send_now(force):
        return

    msg = build_message()
    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    main()
