import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime

# Teknologiayritykset – analyysi keskittyy 100% tekniikkaan
WATCHLIST = [
    # US – Mega cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD",
    # US – Semiconductors & Hardware
    "QCOM", "INTC", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON", "TER", "ASML",
    # US – Cloud & SaaS
    "CRM", "SNOW", "DDOG", "NET", "ZS", "CRWD", "OKTA", "MDB", "PLTR", "SHOP", 
    "TEAM", "HUBS", "ZM", "DOCU", "NOW", "WDAY", "ADBE",
    # US – AI / Infrastructure / Edge
    "ARM", "SMCI", "DELL", "HPE", "AI", "SOUN", "DOCN",
    # US – Cybersecurity
    "PANW", "FTNT", "S", "TMUS",
    # US – Fintech & E-commerce
    "PYPL", "SQ", "COIN", "AFRM", "UPST", "MELI", "SE",
    # US – Social & Digital Ads
    "PINS", "SNAP", "TTD", "U", "RBLX",
    # European / Nordic Tech
    "SAP", "ERICB.ST", "NOKIA.HE", "ADYEN.AS", "LOGN.SW",
    # High Growth / Speculative Tech
    "IONQ", "RGTI", "QUBT", "TSM"
]


def get_stock_data(ticker: str) -> Optional[Dict]:
    try:
        stock = yf.Ticker(ticker)
        # Haetaan 60 päivää jotta saadaan RSI(14) laskettua luotettavasti
        hist = stock.history(period="60d")

        if hist.empty or len(hist) < 15:
            return None

        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2])
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # RSI(14) laskenta
        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 100

        week_ago_price = float(hist["Close"].iloc[-5]) if len(hist) >= 5 else float(hist["Close"].iloc[0])
        week_change_pct = ((current_price - week_ago_price) / week_ago_price) * 100

        volume = float(hist["Volume"].iloc[-1])
        avg_volume = float(hist["Volume"].mean())
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

        info = stock.fast_info
        market_cap = getattr(info, "market_cap", None)
        h52 = getattr(info, "year_high", current_price)
        l52 = getattr(info, "year_low", current_price)
        
        # Etäisyys tuesta/vastuksesta (%)
        dist_from_low = ((current_price - l52) / l52) * 100 if l52 > 0 else 0
        dist_from_high = ((current_price - h52) / h52) * 100 if h52 > 0 else 0

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "change_pct_1d": round(change_pct, 2),
            "change_pct_5d": round(week_change_pct, 2),
            "volume": int(volume),
            "volume_ratio": round(volume_ratio, 2),
            "market_cap": market_cap,
            "rsi": round(rsi, 2),
            "dist_from_low": round(dist_from_low, 2),
            "dist_from_high": round(dist_from_high, 2),
            "52w_high": h52,
            "52w_low": l52,
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
            f"RSI: {s['rsi']} | "
            f"Dist from Low: {s['dist_from_low']}% | "
            f"Vol: {s['volume_ratio']:.1f}x avg"
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
