import time
import threading
import os
import sys
from datetime import datetime
from src.database import (
    init_db, add_scenario, prune_old_scenarios, get_favorite_tickers, 
    get_active_scenarios, deactivate_scenario
)
from src.ai_analyzer import generate_scenarios, quick_news_scan, get_client, validate_scenario
from src.stock_analyzer import get_market_snapshot, get_top_movers, format_movers_for_prompt, WATCHLIST
from src.news_fetcher import fetch_all_news, format_news_for_prompt

# Tila-muuttuja jotta emme aja kahta yhtä aikaa (saman prosessin sisällä)
_WORKER_RUNNING = False
WORKER_STATE = {
    "status": "Odottaa...",
    "current_ticker": "N/A"
}

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
    global _WORKER_RUNNING, WORKER_STATE
    if _WORKER_RUNNING:
        print("[Worker] Already running – skipping new run.")
        return

    _WORKER_RUNNING = True
    WORKER_STATE["status"] = "KÄYNNISSÄ"
    WORKER_STATE["current_ticker"] = "Alustetaan..."
    print(f"[{datetime.now()}] Starting autonomous scenario generation (force={force})")

    try:
        client = get_client()
        fav_tickers = get_favorite_tickers()

        # 1/3 – News fetching
        WORKER_STATE["status"] = "Haetaan uutisia..."
        WORKER_STATE["current_ticker"] = "Uutiset"
        print("1/3 Fetching news data...")
        try:
            articles = fetch_all_news(max_age_hours=168)
            news_text = format_news_for_prompt(articles, max_articles=60)
        except Exception as e:
            print(f"News fetch error: {e}")
            news_text = "Ei uutisdataa saatavilla."
            articles = []

        # 1.5/3 – Validate old scenarios
        WORKER_STATE["status"] = "Validointi vanhoille analyyseille..."
        print("1.5/3 Validating existing scenarios...")
        try:
            active_scens = get_active_scenarios(limit=50)
            snapshot_list = get_market_snapshot([s.get('tickers', 'YLEINEN') for s in active_scens])
            snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
            for scen in active_scens:
                ticker = scen.get('tickers', 'YLEINEN')
                WORKER_STATE["current_ticker"] = ticker
                price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
                validation = validate_scenario(scen, news_text, client)
                status = validation.get('status', 'VALID')
                if status == 'INVALID':
                    deactivate_scenario(scen['id'], reason=validation.get('reason'))
                elif status == 'UPDATE':
                    update_scens = generate_scenarios(
                        f"UPDATE ANALYSIS FOR {ticker} due to: {validation.get('reason')}",
                        f"TICKER: {ticker}, CHANGE: {price_change}%", client)
                    if update_scens:
                        deactivate_scenario(scen['id'], reason=f"Päivitetty: {validation.get('reason')}")
                        add_scenario(update_scens[0], is_manual=True, price_change=price_change, is_updated=True)
        except Exception as e:
            print(f"Validation error: {e}")

        # 2/3 – Market snapshot
        WORKER_STATE["status"] = "Haetaan markkinadata..."
        print("2/3 Fetching market data...")
        try:
            # Merge watchlist, favorites and mentioned tickers
            mentioned = []  # will be filled later when news scanning is added
            all_tickers = list(dict.fromkeys(mentioned + WATCHLIST + fav_tickers))
            snapshot_list = get_market_snapshot(all_tickers)
            snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
            movers = get_top_movers(snapshot_list, top_n=15)
            movers_text = format_movers_for_prompt(movers)
        except Exception as e:
            print(f"Market snapshot error: {e}")
            snapshot = {}
            movers_text = "Markkinadata ei saatavilla."

        # 3/3 – KAKSIVAIHEINEN ANALYYSI (SONNET SCORECARD -> SONNET DEEP)
        WORKER_STATE["status"] = "Vaihe 1: Sonnet-pisteytys..."
        print(f"3/3 Vaihe 1: Sonnet skannaa {len(WATCHLIST)} osaketta...")
        
        try:
            from src.ai_analyzer import filter_watchlist_with_sonnet, analyze_single_stock
            
            # 1. SONNET SCORECARD: Poimitaan parhaat 15 ehdokasta koko listalta
            candidates = filter_watchlist_with_sonnet(news_text, movers_text, WATCHLIST)
            print(f"[WORKER] Sonnet valitsi {len(candidates)} ehdokasta jatkoon.")
            
            # 2. SONNET: Syväanalyysi valituille ehdokkaille
            WORKER_STATE["status"] = "Vaihe 2: Sonnet-syväanalyysi..."
            final_scenarios = []
            
            for ticker in candidates:
                WORKER_STATE["current_ticker"] = ticker
                # Sonnet tekee täyden 11-vaiheen analyysin
                scen = analyze_single_stock(ticker, news_text, client)
                
                if scen:
                    rec = str(scen.get('recommendation', '')).upper()
                    # Puhdistetaan confidence (voi olla esim. "14/19 - perustelut...")
                    raw_conf = str(scen.get('confidence', '0'))
                    import re
                    conf_match = re.search(r'(\d+)', raw_conf)
                    points = int(conf_match.group(1)) if conf_match else 0
                    
                    if rec == 'OSTA' and points >= 11:
                        final_scenarios.append(scen)
                        print(f"  [VALITTU] {ticker} läpäisi TRATEGO-seulan (Pisteet: {points}/19)")
                    else:
                        print(f"  [HYLÄTTY] {ticker} ei täyttänyt TRATEGO-kriteereitä ({rec}, {points}/19)")
                
                time.sleep(1) # Rate limit

            # Tallennetaan parhaat (MAX 5-7 kerrallaan)
            if final_scenarios:
                print(f"[WORKER] Julkaistaan {len(final_scenarios[:7])} parasta analyysia.")
                for scen in final_scenarios[:7]:
                    ticker = scen.get('tickers', 'YLEINEN')
                    price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
                    is_pinned = float(scen.get('confidence', 0)) > 92
                    add_scenario(scen, is_pinned=is_pinned, price_change=price_change)
            else:
                print("[WORKER] Yksikään ehdokas ei läpäissyt lopullista Sonnet-seulaa.")
                
        except Exception as e:
            print(f"[VIRHE] Kolmivaiheisessa analyysissä: {e}")
            import traceback
            traceback.print_exc()

        # Prune old scenarios after full run
        prune_old_scenarios(keep_limit=50)

        # Write last scan timestamp
        try:
            with open("last_scan.txt", "w") as f:
                f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
        except Exception as e:
            print(f"Failed to write last_scan.txt: {e}")

        print(f"[{datetime.now()}] Background task completed successfully.")
    except Exception as e:
        import traceback
        print(f"Global Worker Error: {traceback.format_exc()}")
        # Tallennetaan virhe jotta se näkyy /api/logs
        global LAST_ERROR
        # LAST_ERROR on web.py:ssä, joten käytetään printtiä jos emme saa sitä tässä.
        # Mutta meillä on LAST_ERROR capture web.py:ssä jo.
    finally:
        _WORKER_RUNNING = False
        WORKER_STATE["status"] = "Valmis / Odottaa"
        WORKER_STATE["current_ticker"] = "N/A"


def _worker_loop(interval_hours=None):
    """Loop that runs once a day at 21:00 Helsinki time"""
    print(f"Background worker thread started. Target time: 21:00 (Helsinki)")
    
    try:
        while True:
            # Lasketaan aika seuraavaan klo 21:00 (Helsinki = UTC+3 kesällä)
            # Render on yleensä UTC, joten 21:00 Helsinki = 18:00 UTC
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # Tavoite: 18:00 UTC (21:00 Helsinki kesäaika)
            target_hour_utc = 18
            target = now.replace(hour=target_hour_utc, minute=0, second=0, microsecond=0)
            
            if now >= target:
                target += datetime.timedelta(days=1)
            
            sleep_seconds = (target - now).total_seconds()
            print(f"[Worker] Seuraava skannaus klo 21:00 Helsinki ({sleep_seconds/3600:.1f} tunnin kuluttua).")
            
            time.sleep(sleep_seconds)
            run_scenario_generation(force=True)
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

# Initialise worker on module import for Render deployments
# Only start if not under a test environment (e.g., when FLASK_ENV is production)
if os.getenv("FLASK_ENV") == "production" or os.getenv("RUN_WORKER") == "1":
    try:
        # Start the background worker with immediate execution (interval_hours=None runs loop once)
        start_background_worker(interval_hours=None)
    except Exception as e:
        print(f"Failed to start background worker on import: {e}")
