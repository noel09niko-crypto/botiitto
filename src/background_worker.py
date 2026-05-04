import time
import threading
import os
import sys
from datetime import datetime

# Tuodaan moduulit huipulla, jotta vältetään UnboundLocalError
import src.database as db
import src.ai_analyzer as ai
import src.stock_analyzer as sa
from src.news_fetcher import fetch_all_news, format_news_for_prompt

# Tila-muuttuja jotta emme aja kahta yhtä aikaa (saman prosessin sisällä)
_WORKER_RUNNING = False
WORKER_STATE = {
    "status": "Odottaa...",
    "current_ticker": "N/A",
    "last_error": "Ei virheitä",
    "last_scan_timestamp": "Ei vielä suoritettu"
}

# Lukitustiedosto — estää duplikaatit eri prosessien välillä
_LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "worker.lock")

def _acquire_lock() -> bool:
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            return False
        except:
            if os.path.exists(_LOCK_FILE): os.remove(_LOCK_FILE)
    with open(_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def _release_lock():
    if os.path.exists(_LOCK_FILE):
        try:
            os.remove(_LOCK_FILE)
        except:
            pass

def run_scenario_generation(force=False):
    global _WORKER_RUNNING, WORKER_STATE
    
    if _WORKER_RUNNING:
        print("[Worker] Already running – skipping new run.")
        return

    _WORKER_RUNNING = True
    WORKER_STATE["status"] = "KÄYNNISSÄ"
    WORKER_STATE["current_ticker"] = "Alustetaan..."
    print(f"[{datetime.now()}] Starting autonomous scenario generation (force={force})")

    try:
        client = ai.get_client()
        fav_tickers = db.get_favorite_tickers()

        # 1/3 – News fetching
        WORKER_STATE["status"] = "Haetaan uutisia..."
        WORKER_STATE["current_ticker"] = "Uutiset"
        try:
            articles = fetch_all_news(max_age_hours=168)
            news_text = format_news_for_prompt(articles, max_articles=60)
        except Exception as e:
            print(f"News fetch error: {e}")
            news_text = "Ei uutisdataa saatavilla."
            articles = []

        # 1.5/3 – Validate old scenarios
        WORKER_STATE["status"] = "Validointi vanhoille analyyseille..."
        try:
            active_scens = db.get_active_scenarios(limit=50)
            snapshot_list = sa.get_market_snapshot([s.get('tickers', 'YLEINEN') for s in active_scens])
            snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
            for scen in active_scens:
                ticker = scen.get('tickers')
                if ticker in snapshot:
                    if not ai.validate_scenario(scen, snapshot[ticker]):
                        db.deactivate_scenario(scen['id'])
        except Exception as e:
            print(f"Validation error: {e}")

        # 2/3 – Research Data Collection
        WORKER_STATE["status"] = "Vaihe 1: Kerätään tutkimusdataa..."
        research_bundles = []
        for ticker in sa.WATCHLIST:
            WORKER_STATE["current_ticker"] = ticker
            bundle = sa.get_research_bundle(ticker)
            if bundle: research_bundles.append(bundle)

        # 3/3 – AI Filtering & Analysis
        WORKER_STATE["status"] = "Vaihe 2: Strateginen suodatus..."
        WORKER_STATE["current_ticker"] = "AI Seula"
        movers_text = sa.format_movers_for_prompt(research_bundles)
        
        candidates = ai.filter_watchlist_with_sonnet(research_bundles, news_text, movers_text)
        
        final_scenarios = []
        for ticker in candidates:
            WORKER_STATE["status"] = f"Vaihe 3: Syväanalyysi ({ticker})..."
            WORKER_STATE["current_ticker"] = ticker
            bundle = next((b for b in research_bundles if b['ticker'] == ticker), None)
            if not bundle: continue
            
            scen = ai.analyze_single_stock(ticker, bundle, news_text)
            if scen:
                WORKER_STATE["status"] = f"Vaihe 4: Laadunvarmistus ({ticker})..."
                if ai.verify_analysis_quality(ticker, scen, bundle):
                    final_scenarios.append(scen)

        if final_scenarios:
            snapshot_list = sa.get_market_snapshot([s.get('tickers') for s in final_scenarios])
            snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
            for scen in final_scenarios[:7]:
                ticker = scen.get('tickers', 'YLEINEN')
                price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
                db.add_scenario(scen, is_pinned=False, price_change=price_change)

        db.prune_old_scenarios(keep_limit=50)
        with open("last_scan.txt", "w") as f: f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
        WORKER_STATE["last_scan_timestamp"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        print(f"[{datetime.now()}] Completed successfully.")

    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        WORKER_STATE["last_error"] = str(e)
        print(f"Global Worker Error: {err_msg}")
        with open("last_error.txt", "w") as f: f.write(err_msg)
    finally:
        _WORKER_RUNNING = False
        WORKER_STATE["status"] = "Valmis / Odottaa"
        WORKER_STATE["current_ticker"] = "N/A"

def _worker_loop():
    while True:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now >= target: target += datetime.timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        print(f"[Worker] Next scan in {sleep_seconds/3600:.1f} hours.")
        time.sleep(sleep_seconds)
        run_scenario_generation(force=True)

def start_background_worker(interval_hours=None):
    db.init_db()
    if not _acquire_lock(): return None
    thread = threading.Thread(target=_worker_loop, daemon=True)
    thread.start()
    return thread

if os.getenv("FLASK_ENV") == "production" or os.getenv("RUN_WORKER") == "1":
    start_background_worker()
