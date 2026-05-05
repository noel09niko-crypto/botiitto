import time
import threading
import os
import sys
from datetime import datetime

# Tuodaan moduulit huipulla
import src.database as db
import src.ai_analyzer as ai
import src.stock_analyzer as sa
from src.news_fetcher import fetch_all_news, format_news_for_prompt, fetch_world_news, format_world_news_for_prompt

_WORKER_RUNNING = False
WORKER_STATE = {
    "status": "Odottaa...",
    "current_ticker": "N/A",
    "last_error": "Ei virheitä",
    "last_scan_timestamp": "Ei vielä suoritettu"
}

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
        print("[Worker] Already running – skipping.")
        return

    _WORKER_RUNNING = True
    WORKER_STATE["status"] = "KÄYNNISSÄ"
    WORKER_STATE["current_ticker"] = "Alustetaan..."
    print(f"[{datetime.now()}] Starting scan (force={force})")

    try:
        fav_tickers = db.get_favorite_tickers()

        # === VAIHE 1: Haetaan uutiset JA maailmantapahtumat ===
        WORKER_STATE["status"] = "Vaihe 1: Haetaan uutisia ja maailmantapahtumia..."
        WORKER_STATE["current_ticker"] = "Uutiset + Maailma"
        try:
            articles = fetch_all_news(max_age_hours=168)
            news_text = format_news_for_prompt(articles, max_articles=60)
        except Exception as e:
            print(f"News fetch error: {e}")
            news_text = "Ei uutisdataa saatavilla."
            articles = []

        try:
            world_articles = fetch_world_news(max_age_hours=48)
            world_news_text = format_world_news_for_prompt(world_articles, max_articles=30)
        except Exception as e:
            print(f"World news fetch error: {e}")
            world_news_text = "Ei maailmantapahtumia saatavilla."

        # === VAIHE 1.5: Tarkista vanhat skenaariot — PÄIVITÄ älä poista ===
        WORKER_STATE["status"] = "Vanhojen analyysien tarkistus..."
        try:
            active_scens = db.get_active_scenarios(limit=50)
            for scen in active_scens:
                ticker = scen.get('tickers')
                WORKER_STATE["current_ticker"] = f"Tarkistus: {ticker}"
                val_result = ai.validate_scenario(scen, news_text, world_news_text=world_news_text)
                status = val_result.get('status', 'VALID')
                
                if status == 'UPDATE':
                    # Päivitetään analyysi — EI poisteta
                    update_data = {}
                    if val_result.get('updated_reasoning'):
                        update_data['reasoning'] = val_result['updated_reasoning']
                    if val_result.get('updated_global_context'):
                        update_data['global_context'] = val_result['updated_global_context']
                    if val_result.get('updated_metrics'):
                        update_data['metrics_explanation'] = val_result['updated_metrics']
                    if update_data:
                        db.update_scenario(scen['id'], update_data)
                        print(f"  [PÄIVITETTY] {ticker}: {val_result.get('reason')}")
                elif status == 'INVALID':
                    # Poistetaan VAIN kun ostopaikka on oikeasti ohi
                    db.deactivate_scenario(scen['id'], reason=val_result.get('reason', 'Ostopaikka ohi'))
                    print(f"  [POISTETTU] {ticker}: {val_result.get('reason')}")
                else:
                    print(f"  [OK] {ticker}: Teesi voimassa")
        except Exception as e:
            print(f"Validation error: {e}")

        # === VAIHE 2: Kerää tutkimusdata ===
        WORKER_STATE["status"] = "Vaihe 2: Kerätään tutkimusdataa..."
        research_bundles = []
        for ticker in sa.WATCHLIST:
            WORKER_STATE["current_ticker"] = ticker
            bundle = sa.get_research_bundle(ticker)
            if bundle: research_bundles.append(bundle)

        # === VAIHE 3: AI-suodatus ===
        WORKER_STATE["status"] = "Vaihe 3: Strateginen suodatus..."
        WORKER_STATE["current_ticker"] = "AI Seula"
        
        movers_dict = {
            "gainers": [b for b in research_bundles if (b.get('financials', {}).get('change_pct_1d') or 0) > 2],
            "losers": [b for b in research_bundles if (b.get('financials', {}).get('change_pct_1d') or 0) < -2],
            "high_volume": [b for b in research_bundles if (b.get('financials', {}).get('volume_ratio') or 0) > 2]
        }
        movers_text = sa.format_movers_for_prompt(movers_dict)
        
        candidates = ai.filter_watchlist_with_sonnet(research_bundles, news_text, movers_text, world_news_text=world_news_text)
        print(f"  [SUODATIN] {len(candidates)} osaketta läpäisi seulan: {candidates}")
        
        # === VAIHE 4: Syväanalyysi (kaikki 5 vaihetta joka osakkeelle) ===
        final_scenarios = []
        for ticker in candidates:
            WORKER_STATE["status"] = f"Vaihe 4: Syväanalyysi ({ticker})..."
            WORKER_STATE["current_ticker"] = ticker
            bundle = next((b for b in research_bundles if b['ticker'] == ticker), None)
            if not bundle: continue
            
            scen = ai.analyze_single_stock(ticker, bundle, news_text, world_news_text=world_news_text)
            if scen:
                WORKER_STATE["status"] = f"Vaihe 5: Laadunvarmistus ({ticker})..."
                if ai.verify_analysis_quality(ticker, scen, bundle):
                    final_scenarios.append(scen)
                    print(f"  [HYVÄKSYTTY] {ticker}")

        # === VAIHE 6: Tallennus ===
        if final_scenarios:
            snapshot_list = sa.get_market_snapshot([s.get('tickers') for s in final_scenarios])
            snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
            for scen in final_scenarios[:7]:
                ticker = scen.get('tickers', 'YLEINEN')
                price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
                db.add_scenario(scen, is_pinned=False, price_change=price_change)
                print(f"  [TALLENNETTU] {ticker}")

        with open("last_scan.txt", "w") as f: f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
        WORKER_STATE["last_scan_timestamp"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        print(f"[{datetime.now()}] Scan completed. {len(final_scenarios)} new scenarios saved.")

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
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        # Skannaus klo 21:00 Suomen aikaa = 18:00 UTC
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now >= target: target += dt.timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        print(f"[Worker] Next scan at 21:00 Finnish time (in {sleep_seconds/3600:.1f} hours).")
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
