import time
import threading
from datetime import datetime
from src.database import init_db, add_scenario

# Tila-muuttuja jotta emme aja kahta yhtä aikaa
_WORKER_RUNNING = False

def run_scenario_generation(force=False):
    global _WORKER_RUNNING
    if _WORKER_RUNNING:
        print("Worker is already running. Skipping...")
        return
        
    _WORKER_RUNNING = True
    print(f"[{datetime.now()}] Starting autonomous scenario generation...")
    
    try:
        from src.news_fetcher import fetch_all_news, format_news_for_prompt
        from src.stock_analyzer import get_market_snapshot, get_top_movers, format_movers_for_prompt, WATCHLIST
        from src.ai_analyzer import generate_scenarios, quick_news_scan, get_client

        client = get_client()

        print("1/3 Fetching news data...")
        articles = fetch_all_news(max_age_hours=24)
        news_text = format_news_for_prompt(articles, max_articles=60)
        
        print("2/3 Fetching market data...")
        mentioned = quick_news_scan(news_text, client) if articles else []
        all_tickers = list(dict.fromkeys(mentioned + WATCHLIST))
        snapshot = get_market_snapshot(all_tickers)
        movers = get_top_movers(snapshot, top_n=15)
        movers_text = format_movers_for_prompt(movers)
        
        print("3/3 Asking AI to brainstorm long-term scenarios. This might take 30s...")
        scenarios = generate_scenarios(news_text, movers_text, client)
        
        print(f"-> Generated {len(scenarios)} scenarios. Saving to DB.")
        for scen in scenarios:
            add_scenario(scen)
            
        print(f"[{datetime.now()}] Background task completed successfully.")
        
    except Exception as e:
        print(f"Error in background worker: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _WORKER_RUNNING = False


def _worker_loop(interval_hours=6):
    """Loop that forever generates new scenarios periodically"""
    print(f"Background worker thread started. Interval: {interval_hours}h")
    # Aja kerran heti kun käynnistetään
    run_scenario_generation()
    
    while True:
        # Nuku haluttu aika
        time.sleep(interval_hours * 3600)
        run_scenario_generation()

def start_background_worker(interval_hours=2):
    # Varmista, että tietokanta on luotu
    init_db()
    
    thread = threading.Thread(target=_worker_loop, args=(interval_hours,), daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    init_db()
    run_scenario_generation()
