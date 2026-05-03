import time
import threading
import os
import sys
from datetime import datetime

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
    
    # Paikallinen import jotta vältetään UnboundLocalError lopullisesti
    from src.database import add_scenario, deactivate_scenario, get_active_scenarios, get_favorite_tickers
    from src.ai_analyzer import get_client, validate_scenario, generate_scenarios
    
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

        # 2/3 – TUTKIMUSVAIHE (UUSI: HAETAAN DATA ENNEN PISTEITÄ)
        WORKER_STATE["status"] = "Vaihe 1: Syvän datan keruu..."
        print("2/3 Vaihe 1: Kerätään tutkimusdataa kaikille osakkeille...")
        
        research_bundles = []
        try:
            # Uutisissa mainitut + watchlist + suosikit
            mentioned = quick_news_scan(news_text, client) if news_text else []
            all_tickers = list(dict.fromkeys(mentioned + WATCHLIST + fav_tickers))
            
            # Kerätään syvä data jokaisesta (tämä kestää hetken)
            for ticker in all_tickers:
                WORKER_STATE["current_ticker"] = ticker
                bundle = get_research_bundle(ticker)
                if bundle and "error" not in bundle:
                    research_bundles.append(bundle)
                time.sleep(0.5) # Pieni viive jotta yfinance ei suutu
        except Exception as e:
            print(f"Research bundle error: {e}")

        # 3/3 – PISTEYTYS JA ANALYYSI (11-VAIHEINEN SEULA)
        WORKER_STATE["status"] = "Vaihe 2: TRATEGO-pisteytys..."
        print(f"3/3 Vaihe 2: Sonnet pisteyttää {len(research_bundles)} osaketta...")
        
        try:
            # 1. TRATEGO SCORECARD: Poimitaan parhaat ehdokkaat kovan datan perusteella
            candidates = filter_watchlist_with_sonnet(research_bundles, news_text)
            print(f"[WORKER] Sonnet valitsi {len(candidates)} ehdokasta jatkoon datan perusteella.")
            
            # 2. SYVÄANALYYSI JA VARMISTUS
            final_scenarios = []
            for ticker in candidates:
                WORKER_STATE["status"] = f"Vaihe 3: Syväanalyysi ({ticker})..."
                WORKER_STATE["current_ticker"] = ticker
                
                # Etsitään oikea bundle
                bundle = next((b for b in research_bundles if b['ticker'] == ticker), None)
                if not bundle: continue
                
                # Kirjoitetaan analyysi
                scen = analyze_single_stock(ticker, bundle, news_text)
                
                if scen:
                    # Vaihe 4: STRATEGINEN LAADUNVARMISTUS
                    WORKER_STATE["status"] = f"Vaihe 4: Laadunvarmistus ({ticker})..."
                    if verify_analysis_quality(ticker, scen, bundle):
                        final_scenarios.append(scen)
                        print(f"  [VALITTU] {ticker} läpäisi seulan ja laadunvarmistuksen.")
                    else:
                        print(f"  [HYLÄTTY] {ticker} hylättiin laadunvarmistuksessa.")
                
                time.sleep(1)

            # Tallennetaan parhaat (MAX 5-7 kerrallaan)
            if final_scenarios:
                print(f"[WORKER] Julkaistaan {len(final_scenarios[:7])} parasta analyysia.")
                # Haetaan kurssitiedot hinnanmuutosta varten
                snapshot_list = get_market_snapshot([s.get('tickers') for s in final_scenarios])
                snapshot = {s['ticker']: s for s in snapshot_list if 'ticker' in s}
                
                for scen in final_scenarios[:7]:
                    ticker = scen.get('tickers', 'YLEINEN')
                    price_change = snapshot.get(ticker, {}).get('change_pct_1d', 0.0)
                    # Jos pisteet > 17/19, pinnataan (vahva luottamus)
                    conf_str = str(scen.get('confidence', '0'))
                    import re
                    match = re.search(r'(\d+)', conf_str)
                    points = int(match.group(1)) if match else 0
                    is_pinned = points >= 17
                    
                    add_scenario(scen, is_pinned=is_pinned, price_change=price_change)
            else:
                print("[WORKER] Yksikään ehdokas ei läpäissyt kriteereitä tänään.")
                
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
        err_msg = traceback.format_exc()
        print(f"Global Worker Error: {err_msg}")
        try:
            with open("last_error.txt", "w") as f:
                f.write(err_msg)
        except:
            pass
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
