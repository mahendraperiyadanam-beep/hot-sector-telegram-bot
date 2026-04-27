\
import os
import sys
import math
import html
import time
from datetime import datetime
from typing import Dict, List, Tuple

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
    TOP_STOCKS_PER_HOT_SECTOR,
    TOP_STOCKS_OVERALL,
    TARGET_PACIFIC_TIMES,
    WEEKDAYS_ONLY,
)

PACIFIC = pytz.timezone("America/Los_Angeles")


def now_pacific() -> datetime:
    return datetime.now(PACIFIC)


def should_send_now(force: bool = False) -> bool:
    """Protects against DST problems and duplicate GitHub UTC schedules."""
    if force:
        return True

    now = now_pacific()
    if WEEKDAYS_ONLY and now.weekday() >= 5:
        print(f"Weekend in Pacific time: {now}. Exiting.")
        return False

    current_hhmm = now.strftime("%H:%M")
    if current_hhmm not in TARGET_PACIFIC_TIMES:
        print(f"Current Pacific time {current_hhmm} is not in target times {TARGET_PACIFIC_TIMES}. Exiting.")
        return False

    return True


def normalize_ticker(t: str) -> str:
    """Yahoo Finance uses '-' for tickers like BRK.B -> BRK-B."""
    return str(t).strip().replace(".", "-")


def safe_pct(x) -> float:
    try:
        if pd.isna(x) or not np.isfinite(x):
            return 0.0
        return float(x) * 100.0
    except Exception:
        return 0.0


def fetch_sp500_constituents() -> pd.DataFrame:
    """
    Pulls S&P 500 constituents from Wikipedia using a browser-like User-Agent.
    Fixes GitHub Actions HTTP 403 issue.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    from io import StringIO
    tables = pd.read_html(StringIO(response.text))
    df = tables[0].copy()

    df["Ticker"] = df["Symbol"].apply(normalize_ticker)

    df = df.rename(
        columns={
            "Security": "Name",
            "GICS Sector": "Sector",
            "GICS Sub-Industry": "Industry",
        }
    )

    return df[["Ticker", "Name", "Sector", "Industry"]]


def download_prices(tickers: List[str], period: str = "3mo", interval: str = "1d", prepost: bool = False) -> pd.DataFrame:
    """
    Downloads adjusted OHLCV using yfinance.
    Uses group_by='ticker' so multi-ticker output is easier to process.
    """
    tickers = sorted(set([t for t in tickers if isinstance(t, str) and len(t) > 0]))
    if not tickers:
        return pd.DataFrame()

    data = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        prepost=prepost,
        threads=True,
        progress=False,
    )
    return data


def extract_single_ticker(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        if ticker not in df.columns.get_level_values(0):
            return pd.DataFrame()
        out = df[ticker].copy()
    else:
        out = df.copy()
    out = out.dropna(how="all")
    return out


def etf_metrics(etf_map: Dict[str, str]) -> pd.DataFrame:
    tickers = list(etf_map.values()) + [BENCHMARK]
    daily = download_prices(tickers, period="3mo", interval="1d", prepost=False)

    rows = []
    spy = extract_single_ticker(daily, BENCHMARK)
    spy_ret_1d = 0.0
    spy_ret_5d = 0.0
    if len(spy) >= 6:
        spy_ret_1d = spy["Close"].iloc[-1] / spy["Close"].iloc[-2] - 1
        spy_ret_5d = spy["Close"].iloc[-1] / spy["Close"].iloc[-6] - 1

    for label, ticker in etf_map.items():
        d = extract_single_ticker(daily, ticker)
        if len(d) < 30:
            continue

        close = d["Close"]
        vol = d["Volume"] if "Volume" in d.columns else pd.Series(index=d.index, data=np.nan)
        ret_1d = close.iloc[-1] / close.iloc[-2] - 1
        ret_5d = close.iloc[-1] / close.iloc[-6] - 1 if len(close) >= 6 else np.nan
        ret_20d = close.iloc[-1] / close.iloc[-21] - 1 if len(close) >= 21 else np.nan
        above_20 = close.iloc[-1] > close.rolling(20).mean().iloc[-1]
        above_50 = close.iloc[-1] > close.rolling(50).mean().iloc[-1] if len(close) >= 50 else False
        rvol = vol.iloc[-1] / vol.rolling(20).mean().iloc[-1] if "Volume" in d.columns else 1.0

        score = (
            safe_pct(ret_1d) * 3.0
            + safe_pct(ret_5d) * 1.5
            + safe_pct(ret_20d) * 0.5
            + safe_pct(ret_1d - spy_ret_1d) * 2.0
            + safe_pct(ret_5d - spy_ret_5d) * 1.0
            + min(float(rvol), 3.0) * 1.0
            + (2.0 if above_20 else 0.0)
            + (2.0 if above_50 else 0.0)
        )

        rows.append(
            {
                "Group": label,
                "ETF": ticker,
                "Price": close.iloc[-1],
                "1D%": safe_pct(ret_1d),
                "5D%": safe_pct(ret_5d),
                "20D%": safe_pct(ret_20d),
                "RS_vs_SPY_1D%": safe_pct(ret_1d - spy_ret_1d),
                "RVOL": float(rvol) if pd.notna(rvol) else 1.0,
                "Above20": bool(above_20),
                "Above50": bool(above_50),
                "Score": float(score),
            }
        )

    return pd.DataFrame(rows).sort_values("Score", ascending=False)


def stock_metrics(universe: pd.DataFrame, hot_sectors: List[str]) -> pd.DataFrame:
    # Limit to stocks in hot sectors for speed and quality.
    pool = universe[universe["Sector"].isin(hot_sectors)].copy()
    tickers = pool["Ticker"].dropna().unique().tolist()

    # Keep one extra benchmark for relative strength.
    daily = download_prices(tickers + [BENCHMARK], period="6mo", interval="1d", prepost=False)
    spy = extract_single_ticker(daily, BENCHMARK)

    spy_ret_1d = spy["Close"].iloc[-1] / spy["Close"].iloc[-2] - 1 if len(spy) >= 2 else 0
    spy_ret_5d = spy["Close"].iloc[-1] / spy["Close"].iloc[-6] - 1 if len(spy) >= 6 else 0
    spy_ret_20d = spy["Close"].iloc[-1] / spy["Close"].iloc[-21] - 1 if len(spy) >= 21 else 0

    rows = []
    meta = pool.set_index("Ticker").to_dict("index")

    for ticker in tickers:
        d = extract_single_ticker(daily, ticker)
        if len(d) < 60:
            continue

        close = d["Close"]
        high = d["High"]
        low = d["Low"]
        vol = d["Volume"]

        price = float(close.iloc[-1])
        avg_vol_20 = float(vol.rolling(20).mean().iloc[-1])
        dollar_vol = price * avg_vol_20

        if price < MIN_PRICE or dollar_vol < MIN_DOLLAR_VOLUME:
            continue

        ret_1d = close.iloc[-1] / close.iloc[-2] - 1
        ret_5d = close.iloc[-1] / close.iloc[-6] - 1
        ret_20d = close.iloc[-1] / close.iloc[-21] - 1
        ret_63d = close.iloc[-1] / close.iloc[-64] - 1 if len(close) >= 64 else np.nan

        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan
        rvol = vol.iloc[-1] / avg_vol_20 if avg_vol_20 > 0 else 1.0
        near_high_20 = close.iloc[-1] / high.rolling(20).max().iloc[-1] - 1
        atr14 = (high - low).rolling(14).mean().iloc[-1]
        atr_pct = atr14 / price if price > 0 else np.nan

        trend_points = 0
        trend_points += 2 if close.iloc[-1] > sma20 else 0
        trend_points += 2 if close.iloc[-1] > sma50 else 0
        trend_points += 2 if pd.notna(sma200) and close.iloc[-1] > sma200 else 0
        trend_points += 1 if sma20 > sma50 else 0

        score = (
            safe_pct(ret_1d) * 3.0
            + safe_pct(ret_5d) * 2.0
            + safe_pct(ret_20d) * 0.75
            + safe_pct(ret_63d) * 0.25
            + safe_pct(ret_1d - spy_ret_1d) * 2.0
            + safe_pct(ret_5d - spy_ret_5d) * 1.5
            + safe_pct(ret_20d - spy_ret_20d) * 1.0
            + min(float(rvol), 4.0) * 2.0
            + trend_points
            + max(0, 2.0 + safe_pct(near_high_20))  # prefers stocks near 20-day highs
            - max(0, safe_pct(atr_pct) - 8) * 0.25  # small penalty for very wild stocks
        )

        rows.append(
            {
                "Ticker": ticker,
                "Name": meta[ticker]["Name"],
                "Sector": meta[ticker]["Sector"],
                "Industry": meta[ticker]["Industry"],
                "Price": price,
                "1D%": safe_pct(ret_1d),
                "5D%": safe_pct(ret_5d),
                "20D%": safe_pct(ret_20d),
                "63D%": safe_pct(ret_63d),
                "RS_1D%": safe_pct(ret_1d - spy_ret_1d),
                "RS_5D%": safe_pct(ret_5d - spy_ret_5d),
                "RVOL": float(rvol),
                "DollarVolM": dollar_vol / 1_000_000,
                "Near20DHigh%": safe_pct(near_high_20),
                "Score": float(score),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Score", ascending=False)


def format_table_rows(df: pd.DataFrame, columns: List[str], n: int) -> str:
    if df.empty:
        return "None"
    lines = []
    for _, r in df.head(n).iterrows():
        parts = []
        for c in columns:
            v = r[c]
            if isinstance(v, float):
                if "%" in c:
                    parts.append(f"{c}:{v:+.1f}")
                elif c == "RVOL":
                    parts.append(f"RVOL:{v:.1f}x")
                elif c == "DollarVolM":
                    parts.append(f"$Vol:{v:.0f}M")
                elif c == "Score":
                    parts.append(f"Score:{v:.1f}")
                else:
                    parts.append(f"{c}:{v:.2f}")
            else:
                parts.append(f"{v}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def build_message() -> str:
    run_time = now_pacific().strftime("%a %Y-%m-%d %I:%M %p PT")

    universe = fetch_sp500_constituents()

    sectors = etf_metrics(SECTOR_ETFS)
    industries = etf_metrics(INDUSTRY_ETFS)

    hot_sectors = sectors.head(TOP_SECTORS)["Group"].tolist()
    leaders = stock_metrics(universe, hot_sectors)

    msg = []
    msg.append(f"🔥 <b>Hot Sector / Industry / Stock Leaders</b>")
    msg.append(f"<b>Run:</b> {html.escape(run_time)}")
    msg.append("")
    msg.append("<b>Top Hot Sectors</b>")
    for _, r in sectors.head(TOP_SECTORS).iterrows():
        msg.append(
            f"• <b>{html.escape(r['Group'])}</b> ({r['ETF']}): "
            f"1D {r['1D%']:+.1f}% | 5D {r['5D%']:+.1f}% | "
            f"RS {r['RS_vs_SPY_1D%']:+.1f}% | RVOL {r['RVOL']:.1f}x"
        )

    msg.append("")
    msg.append("<b>Top Hot Industries / Themes</b>")
    for _, r in industries.head(TOP_INDUSTRIES).iterrows():
        msg.append(
            f"• <b>{html.escape(r['Group'])}</b> ({r['ETF']}): "
            f"1D {r['1D%']:+.1f}% | 5D {r['5D%']:+.1f}% | "
            f"RS {r['RS_vs_SPY_1D%']:+.1f}% | RVOL {r['RVOL']:.1f}x"
        )

    msg.append("")
    msg.append("<b>Top Stock Leaders in Hot Sectors</b>")
    if leaders.empty:
        msg.append("No qualified leaders found based on filters.")
    else:
        for _, r in leaders.head(TOP_STOCKS_OVERALL).iterrows():
            msg.append(
                f"• <b>{r['Ticker']}</b> — {html.escape(str(r['Name'])[:34])} | "
                f"{html.escape(str(r['Sector']))} | "
                f"1D {r['1D%']:+.1f}% | 5D {r['5D%']:+.1f}% | "
                f"20D {r['20D%']:+.1f}% | RVOL {r['RVOL']:.1f}x | "
                f"$Vol {r['DollarVolM']:.0f}M"
            )

    msg.append("")
    msg.append("<b>How to read this</b>")
    msg.append("Leader = strong sector + strong industry + stock outperforming SPY with volume and trend confirmation.")
    msg.append("Not financial advice. Use your chart rules, stop loss, and position sizing.")

    # Telegram max message is 4096 chars. Keep safe.
    output = "\n".join(msg)
    return output[:3900]


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub secrets.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")


def main() -> None:
    force = "--force" in sys.argv or os.environ.get("FORCE_SEND", "false").lower() == "true"

    if not should_send_now(force=force):
        return

    message = build_message()
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    main()
