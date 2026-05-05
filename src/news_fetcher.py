import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict

# Yrityskohtaiset uutislähteet
RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Finance": "https://feeds.reuters.com/reuters/financialsNews",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "CNBC Markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
}

# Maailmantapahtumia, kriisejä, geopolitiikkaa, makrotaloutta
WORLD_NEWS_FEEDS = {
    "Reuters World": "https://feeds.reuters.com/Reuters/worldNews",
    "Reuters Politics": "https://feeds.reuters.com/Reuters/PoliticsNews",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR World": "https://feeds.npr.org/1004/rss.xml",
    "AP Top News": "https://rsshub.app/apnews/topics/apf-topnews",
    "Reuters Tech": "https://feeds.reuters.com/reuters/technologyNews",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestingBot/1.0)"
}


def fetch_feed(name: str, url: str, max_age_hours: int = 24) -> List[Dict]:
    articles = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
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
    """Hakee sekä yritysuutiset ETTÄ maailmantapahtumat."""
    all_articles = []
    for name, url in RSS_FEEDS.items():
        articles = fetch_feed(name, url, max_age_hours)
        all_articles.extend(articles)

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    return all_articles


def fetch_world_news(max_age_hours: int = 48) -> List[Dict]:
    """Hakee maailmantapahtumat, kriisit, geopolitiikka, makrotalous — laaja kuva."""
    all_articles = []
    for name, url in WORLD_NEWS_FEEDS.items():
        articles = fetch_feed(name, url, max_age_hours)
        all_articles.extend(articles)

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    return all_articles


def format_news_for_prompt(articles: List[Dict], max_articles: int = 60) -> str:
    if not articles:
        return "Ei tuoreita uutisia saatavilla."

    lines = []
    for i, art in enumerate(articles[:max_articles], 1):
        lines.append(
            f"{i}. [{art['source']}] {art['title']}\n"
            f"   {art['summary'][:200]}\n"
            f"   Published: {art['published']}"
        )

    return "\n\n".join(lines)


def format_world_news_for_prompt(articles: List[Dict], max_articles: int = 30) -> str:
    """Muotoilee maailmantapahtumat AI:lle luettavaan muotoon."""
    if not articles:
        return "Ei maailmantapahtumia saatavilla."

    lines = ["=== MAAILMANTAPAHTUMAT, KRIISIT JA GEOPOLITIIKKA ==="]
    for i, art in enumerate(articles[:max_articles], 1):
        lines.append(
            f"{i}. [{art['source']}] {art['title']}\n"
            f"   {art['summary'][:300]}"
        )

    return "\n\n".join(lines)
