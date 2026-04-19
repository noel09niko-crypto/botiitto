import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime

# Teknologiayritykset – analyysi keskittyy 100% tekniikkaan
WATCHLIST = [
    # US – Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD",
    # US – Semiconductors
    "QCOM", "INTC", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
    # US – Cloud & SaaS
    "CRM", "SNOW", "DDOG", "NET", "ZS", "CRWD", "OKTA", "MDB", "PLTR", "SHOP",
    # US – AI / Infrastructure
    "ARM", "SMCI", "DELL", "HPE",
    # US – Cybersecurity
    "PANW", "FTNT",
    # US – Fintech & Payments (tech angle)
    "PYPL", "SQ", "COIN",
    # European / Nordic Tech
    "ASML", "SAP", "ERICB.ST", "NOKIA.HE",
]


def get_stock_data(ticker: str) -> Optional[Dict]:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")

        if hist.empty or len(hist) < 2:
            return None

        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2])
        change_pct = ((current_price - prev_close) / prev_close) * 100

        week_ago_price = float(hist["Close"].iloc[0])
        week_change_pct = ((current_price - week_ago_price) / week_ago_price) * 100

        volume = float(hist["Volume"].iloc[-1])
        avg_volume = float(hist["Volume"].mean())
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        info = stock.fast_info
        market_cap = getattr(info, "market_cap", None)
        fifty_two_week_high = getattr(info, "year_high", None)
        fifty_two_week_low = getattr(info, "year_low", None)

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "change_pct_1d": round(change_pct, 2),
            "change_pct_5d": round(week_change_pct, 2),
            "volume": int(volume),
            "volume_ratio": round(volume_ratio, 2),
            "market_cap": market_cap,
            "52w_high": fifty_two_week_high,
            "52w_low": fifty_two_week_low,
        }
    except Exception as e:
        return None


def get_market_snapshot(tickers: List[str] = None) -> List[Dict]:
    if tickers is None:
        tickers = WATCHLIST

    results = []
    print(f"[stocks] Fetching data for {len(tickers)} tickers...")

    for ticker in tickers:
        data = get_stock_data(ticker)
        if data:
            results.append(data)

    results.sort(key=lambda x: abs(x["change_pct_1d"]), reverse=True)
    return results


def get_top_movers(snapshot: List[Dict], top_n: int = 20) -> Dict:
    gainers = sorted(snapshot, key=lambda x: x["change_pct_1d"], reverse=True)[:top_n]
    losers = sorted(snapshot, key=lambda x: x["change_pct_1d"])[:top_n]
    high_volume = sorted(snapshot, key=lambda x: x["volume_ratio"], reverse=True)[:top_n]

    return {
        "gainers": gainers,
        "losers": losers,
        "high_volume": high_volume,
    }


def format_movers_for_prompt(movers: Dict) -> str:
    def fmt_stock(s: Dict) -> str:
        cap = f"${s['market_cap']/1e9:.1f}B" if s.get("market_cap") else "N/A"
        return (
            f"  {s['ticker']}: ${s['current_price']} | "
            f"1d: {s['change_pct_1d']:+.2f}% | "
            f"5d: {s['change_pct_5d']:+.2f}% | "
            f"Vol: {s['volume_ratio']:.1f}x avg | "
            f"MCap: {cap}"
        )

    lines = ["=== TOP GAINERS (1 day) ==="]
    for s in movers["gainers"][:10]:
        lines.append(fmt_stock(s))

    lines.append("\n=== TOP LOSERS (1 day) ===")
    for s in movers["losers"][:10]:
        lines.append(fmt_stock(s))

    lines.append("\n=== HIGHEST VOLUME (vs avg) ===")
    for s in movers["high_volume"][:10]:
        lines.append(fmt_stock(s))

    return "\n".join(lines)


def get_detailed_info(ticker: str) -> str:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("longName", ticker)
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        pe = info.get("trailingPE", "N/A")
        fwd_pe = info.get("forwardPE", "N/A")
        eps = info.get("trailingEps", "N/A")
        revenue = info.get("totalRevenue", None)
        rev_str = f"${revenue/1e9:.1f}B" if revenue else "N/A"
        profit_margin = info.get("profitMargins", None)
        margin_str = f"{profit_margin*100:.1f}%" if profit_margin else "N/A"
        beta = info.get("beta", "N/A")
        analyst_target = info.get("targetMeanPrice", "N/A")
        recommendation = info.get("recommendationKey", "N/A")

        return (
            f"{name} ({ticker}) | Sector: {sector} | Industry: {industry}\n"
            f"P/E: {pe} | Fwd P/E: {fwd_pe} | EPS: {eps}\n"
            f"Revenue: {rev_str} | Profit Margin: {margin_str}\n"
            f"Beta: {beta} | Analyst target: {analyst_target} | Rating: {recommendation}"
        )
    except Exception:
        return f"{ticker}: detailed info unavailable"
