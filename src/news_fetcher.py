import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict

RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Finance": "https://feeds.reuters.com/reuters/financialsNews",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "CNBC Markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestingBot/1.0)"
}


def fetch_feed(name: str, url: str, max_age_hours: int = 24) -> List[Dict]:
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        for entry in feed.entries[:20]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            if published and published < cutoff:
                continue

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary[:500]
            elif hasattr(entry, "description"):
                summary = entry.description[:500]

            articles.append({
                "source": name,
                "title": getattr(entry, "title", ""),
                "summary": summary,
                "link": getattr(entry, "link", ""),
                "published": published.isoformat() if published else "unknown",
            })
    except Exception as e:
        print(f"[news] Error fetching {name}: {e}")

    return articles


def fetch_all_news(max_age_hours: int = 24) -> List[Dict]:
    all_articles = []
    for name, url in RSS_FEEDS.items():
        articles = fetch_feed(name, url, max_age_hours)
        all_articles.extend(articles)

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    return all_articles


def format_news_for_prompt(articles: List[Dict], max_articles: int = 60) -> str:
    if not articles:
        return "No recent news available."

    lines = []
    for i, art in enumerate(articles[:max_articles], 1):
        lines.append(
            f"{i}. [{art['source']}] {art['title']}\n"
            f"   {art['summary'][:200]}\n"
            f"   Published: {art['published']}"
        )

    return "\n\n".join(lines)
