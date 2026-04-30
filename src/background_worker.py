import time
import threading
import os
import sys
from datetime import datetime
from src.database import init_db, add_scenario

# Tila-muuttuja jotta emme aja kahta yhtä aikaa (saman prosessin sisällä)
_WORKER_RUNNING = False

# Lukitustiedosto — estää duplikaatit eri prosessien välillä
_LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "worker.lock")

def _acquire_lock() -> bool:
    """Yrittää hankkia lukituksen. Palauttaa True jos onnistui."""
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # Tarkista onko vanha prosessi vielä käynnissä
            os.kill(old_pid, 0)  # Ei tapa — vain tarkistaa
            print(f"[Worker] Lukko on prosessilla {old_pid} — tämä prosessi ({os.getpid()}) ei käynnistä workeria.")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            # Vanha prosessi on kuollut → lukko on vapaa
            print(f"[Worker] Vanhentunut lukko poistettu (PID ei enää käynnissä).")
            os.remove(_LOCK_FILE)

    # Kirjoita oma PID lukitustiedostoon
    with open(_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    print(f"[Worker] Lukko hankittu prosessille {os.getpid()}.")
    return True

def _release_lock():
    """Vapauttaa lukituksen jos tämä prosessi omistaa sen."""
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(_LOCK_FILE)
                print(f"[Worker] Lukko vapautettu.")
        except Exception:
            pass

def run_scenario_generation(force=False):
    global _WORKER_RUNNING
    if _WORKER_RUNNING:
        print("Worker is already running. Skipping...")
        return
        
    _WORKER_RUNNING = True
    print(f"[{datetime.now()}] Starting autonomous scenario generation...")
    
    try:
        from src.database import prune_old_scenarios, get_favorite_tickers, get_active_scenarios, deactivate_scenario
        from src.ai_analyzer import generate_scenarios, quick_news_scan, get_client, validate_scenario
        from src.stock_analyzer import get_market_snapshot, get_top_movers, format_movers_for_prompt, WATCHLIST
        from src.news_fetcher import fetch_all_news, format_news_for_prompt

        client = get_client()
        fav_tickers = get_favorite_tickers()

        print("1/3 Fetching news data...")
        articles = fetch_all_news(max_age_hours=168)
        news_text = format_news_for_prompt(articles, max_articles=60)
        mentioned = quick_news_scan(news_text, client) if articles else []

        print("1.5/3 Validating existing scenarios against new info & price...")
        active_scens = get_active_scenarios(limit=50)
        snapshot_list = get_market_snapshot([s.get('tickers', 'YLEINEN') for s in active_scens])
        snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
        
        for scen in active_scens:
            ticker = scen.get('tickers', 'YLEINEN')
            # 1. Hintamuutos tiedoksi valvontaan
            price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
            
            # 2. Sisältöpohjainen validointi
            validation = validate_scenario(scen, news_text, client)
            status = validation.get('status', 'VALID')
            
            # Poistetaan VASTA jos tekoäly on saanut lukea alkuperäisen perustelun ja toteaa ettei se enää päde.
            if status == 'INVALID':
                reason = validation.get('reason', 'Tekoäly arvioi perustelun mitätöityneen.')
                print(f"  [POISTO] {ticker}: {reason}")
                from src.database import deactivate_scenario
                deactivate_scenario(scen['id'], reason=reason)
            elif status == 'UPDATE':
                print(f"  [PÄIVITYS] Päivitetään {ticker} uuden tiedon valossa...")
                update_scens = generate_scenarios(f"UPDATE ANALYSIS FOR {ticker} due to: {validation.get('reason')}", f"TICKER: {ticker}, CHANGE: {price_change}%", client)
                if update_scens:
                    from src.database import add_scenario, deactivate_scenario
                    deactivate_scenario(scen['id'], reason=f"Päivitetty uudella analyysilla: {validation.get('reason')}")
                    add_scenario(update_scens[0], is_manual=True, price_change=price_change, is_updated=True)
        
        print("2/3 Fetching market data...")
        all_tickers = list(dict.fromkeys(mentioned + WATCHLIST + fav_tickers))
        snapshot = get_market_snapshot(all_tickers)
        movers = get_top_movers(snapshot, top_n=15)
        movers_text = format_movers_for_prompt(movers)
        
        print("3/3 Asking AI to brainstorm long-term scenarios. This might take 30s...")
        scenarios = generate_scenarios(news_text, movers_text, client)
        
        print(f"-> Generated {len(scenarios)} scenarios. Saving to DB.")
        for scen in scenarios:
            # Mark as 'Huippu' if confidence is very high
            is_huippu = scen.get('luottamus', 0) >= 95 or scen.get('confidence', 0) >= 95
            if is_huippu:
                print(f"  [Huippu] Löydetty huippuanalyysi: {scen.get('otsikko', 'Tuntematon')}")
            
            # Hae osakkeen hintamuutos snapshotista (jos saatavilla)
            ticker = scen.get('tickers', scen.get('ticker', 'YLEINEN'))
            price_change = 0.0
            if ticker in snapshot:
                price_change = snapshot[ticker].get('change_pct_1d', 0.0)
            
            add_scenario(scen, is_pinned=is_huippu, price_change=price_change)
            
        # Laitetaan isompi raja, jotta 6kk horisontin kohteet eivät katoa
        prune_old_scenarios(keep_limit=50)
        
        try:
            with open("last_scan.txt", "w") as f:
                f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
        except:
            pass
            
        print(f"[{datetime.now()}] Background task completed successfully.")
        
    except Exception as e:
        print(f"Error in background worker: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _WORKER_RUNNING = False


def _worker_loop(interval_hours=2):
    """Loop that forever generates new scenarios periodically"""
    print(f"Background worker thread started. Interval: {interval_hours}h")
    try:
        # Aja kerran heti kun käynnistetään
        run_scenario_generation()
        
        while True:
            # Nuku haluttu aika
            time.sleep(interval_hours * 3600)
            run_scenario_generation()
    finally:
        # Vapautetaan lukko aina kun looppi loppuu
        _release_lock()

def start_background_worker(interval_hours=3):
    """Käynnistää background workerin — mutta VAIN jos tämä prosessi saa lukon."""
    # Varmista, että tietokanta on luotu
    init_db()

    if not _acquire_lock():
        print(f"[Worker] Toinen prosessi ajaa jo workeria. Tämä instanssi toimii vain web-palvelimena.")
        return None

    thread = threading.Thread(target=_worker_loop, args=(interval_hours,), daemon=True)
    thread.daemon = True  # Daemon-säie kuolee kun prosessi kuolee
    thread.start()
    return thread

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    init_db()
    run_scenario_generation()
