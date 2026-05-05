from flask import Flask, render_template, jsonify, request
import os
import threading
from datetime import datetime
from dotenv import load_dotenv

from src.database import init_db, get_active_scenarios, get_favorite_scenarios, toggle_favorite, get_db_connection
from src.background_worker import start_background_worker

load_dotenv()

app = Flask(__name__)

LAST_ERROR = "Ei virheitä"

# Alusta tietokanta (myös kun gunicorn importtaa)
try:
    init_db()
    print("[Startup] Tietokanta alustettu.")
except Exception as e:
    print(f"[Startup] VAROITUS: Tietokanta-alustus epäonnistui: {e}")
    import traceback; traceback.print_exc()

# Keep-alive: estää Render free tierin nukahtamisen
def _keep_alive():
    import urllib.request
    url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not url:
        return  # Ei Render-ympäristössä, ei tehdä mitään
    import time as _time
    _time.sleep(60)  # Odotetaan että palvelin on ylhäällä ennen ensimmäistä pingiä
    while True:
        try:
            urllib.request.urlopen(url + "/health", timeout=10)
        except Exception:
            pass
        _time.sleep(14 * 60)  # 14 minuuttia

threading.Thread(target=_keep_alive, daemon=True).start()

# Käynnistetään taustamoottori, joka keksii uusia skenaarioita
# Tätä ei suoriteta lokaalissa debugissa vahingossa kahdesti
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    try:
        start_background_worker()
        print("[Startup] Background worker käynnistetty (21:00 aikataululla).")
    except Exception as e:
        print(f"[Startup] VAROITUS: Background worker epäonnistui: {e}")
        import traceback; traceback.print_exc()

# Oletusreitti, joka tarjoilee HTML-pääsivun
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

# Hakee kaikki aktiiviset (ja uudet) mahdollisuudet
@app.route('/api/scenarios', methods=['GET'])
def fetch_scenarios():
    try:
        active = get_active_scenarios(limit=15)
        favorites = get_favorite_scenarios()
        
        last_scan = "Ei tietoa (Odottaa)"
        if os.path.exists("last_scan.txt"):
            with open("last_scan.txt", "r") as f:
                last_scan = f.read().strip()
        
        return jsonify({
            "success": True,
            "active": active,
            "favorites": favorites,
            "timestamp": last_scan
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint tykkäämiselle
@app.route('/api/favorite/<int:scenario_id>', methods=['POST'])
def favorite_scenario(scenario_id):
    try:
        toggle_favorite(scenario_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint analyysien nollaamiseen (Puhdas pöytä)
@app.route('/api/clear_all', methods=['GET'])
def clear_all_scenarios():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE scenarios SET is_active = FALSE")
        conn.commit()
        conn.close()
        return "<h1>Pöytä on pyyhitty puhtaaksi!</h1><p>Mene takaisin etusivulle, niin näet että kaikki on poissa.</p><a href='/'>Palaa etusivulle</a>"
    except Exception as e:
        return f"Error: {e}"

# Endpoint manuaaliseen 2h skannauksen herättämiseen (Selainlinkki)
@app.route('/api/force_scan', methods=['GET'])
def force_scan():
    import threading
    from src.background_worker import run_scenario_generation
    
    def run_scan():
        print("[FORCE SCAN] Aloitetaan pakotettu täysi markkinaskannaus...")
        run_scenario_generation(force=True)
        print("[FORCE SCAN] Valmis!")
            
    threading.Thread(target=run_scan).start()
    return "<h1>Skannaus käynnistetty taustalla!</h1><p>Tekoäly haravoi uutisia juuri nyt. Palaa etusivulle ja päivitä sivu n. 2-3 minuutin kuluttua.</p><a href='/'>Palaa etusivulle</a>"

# Ajax Endpoint taustapainiketta varten
@app.route('/api/force_scan_ajax', methods=['POST'])
def force_scan_ajax():
    import threading
    from src.background_worker import run_scenario_generation
    def run_scan():
        run_scenario_generation(force=True)
    threading.Thread(target=run_scan).start()
    return jsonify({"success": True, "message": "Skannaus käynnistetty. Odota pari minuuttia ja päivitä sivu."})

@app.route('/api/nuclear_wipe', methods=['GET'])
def nuclear_wipe():
    from src.database import get_db_connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scenarios")
        conn.commit()
        conn.close()
        
        # Käynnistetään heti uusi skannaus puhtaalta pöydältä
        import threading
        from src.background_worker import run_scenario_generation
        def run_with_error_capture():
            global LAST_ERROR
            try:
                run_scenario_generation(force=True)
            except Exception as e:
                import traceback
                LAST_ERROR = traceback.format_exc()
                print(f"[CRITICAL ERROR] {LAST_ERROR}")
                
        threading.Thread(target=run_with_error_capture).start()
        
        return "<h1>Tietokanta tyhjennetty!</h1><p>Kaikki analyysit on poistettu ja uusi skannaus on käynnistetty uusilla säännöillä.</p><a href='/'>Palaa etusivulle</a>"
    except Exception as e:
        LAST_ERROR = str(e)
        return f"Virhe: {str(e)}"
@app.route('/api/refresh_all_style', methods=['GET'])
def refresh_all_style():
    import threading
    from src.database import get_active_scenarios, get_db_connection, USE_POSTGRES
    from src.ai_analyzer import rewrite_scenario, get_client

    def run_refresh():
        print("[REFRESH] Aloitetaan tyylin päivitys...")
        client = get_client()
        scenarios = get_active_scenarios(limit=50)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for scen in scenarios:
            new_data = rewrite_scenario(scen, client)
            if new_data:
                query = """
                    UPDATE scenarios 
                    SET title = %s, summary = %s, global_context = %s, reasoning = %s, 
                        metrics_explanation = %s, time_horizon = %s, company_history = %s,
                        competitive_landscape = %s, risk_score = %s,
                        confidence = %s, risk_level = %s, sector = %s, invalidation_risks = %s,
                        is_updated = TRUE
                    WHERE id = %s
                """
                if not USE_POSTGRES:
                    query = query.replace("%s", "?")
                
                cursor.execute(query, (
                    new_data.get('title'), new_data.get('summary'), new_data.get('global_context'),
                    new_data.get('reasoning'), new_data.get('metrics_explanation'),
                    new_data.get('time_horizon'), new_data.get('company_history'),
                    new_data.get('competitive_landscape'),
                    new_data.get('risk_score', 5),
                    new_data.get('confidence'), new_data.get('risk_level'),
                    new_data.get('sector'), new_data.get('invalidation_risks'),
                    scen['id']
                ))
                conn.commit()
        conn.close()
        print("[REFRESH] Valmis!")

    threading.Thread(target=run_refresh).start()
    return "<h1>Tyylin päivitys aloitettu!</h1><p>Käyn läpi kaikki analyysit ja muutan ne uuteen tyyliin taustalla. Tämä kestää muutaman minuutin.</p><a href='/'>Palaa etusivulle</a>"



@app.route('/api/logs', methods=['GET'])
def view_logs():
    """Näyttää viimeisimmät lokimerkinnät helpottamaan debuggausta."""
    try:
        from src import background_worker
        status = "KÄYNNISSÄ" if background_worker._WORKER_RUNNING else "EI KÄYNNISSÄ"
        w_state = background_worker.WORKER_STATE
        
        # Luetaan last_scan.txt jos olemassa
        last_scan = "Ei vielä suoritettu"
        if os.path.exists("last_scan.txt"):
            with open("last_scan.txt", "r") as f:
                last_scan = f.read().strip()
                
        err_text = LAST_ERROR
        if os.path.exists("last_error.txt"):
            with open("last_error.txt", "r") as f:
                err_text = f.read().strip() or LAST_ERROR

        return jsonify({
            "worker_status": status,
            "current_status": w_state.get("status"),
            "current_ticker": w_state.get("current_ticker"),
            "last_scan_timestamp": last_scan,
            "last_error": err_text,
            "info": "Botti käy läpi osakkeita. 3-vaiheinen syväanalyysi kestää n. 1min per osake."
        })
    except Exception as e:
        return str(e)

@app.route('/api/search_and_analyze', methods=['POST'])
def search_and_analyze():
    data = request.json
    query = data.get('query', '').strip().upper()
    if not query:
        return jsonify({"success": False, "error": "Query missing"}), 400
        
    try:
        from src.ai_analyzer import resolve_ticker, generate_scenarios, get_client
        from src.stock_analyzer import get_stock_data
        from src.database import add_scenario
        
        client = get_client()
        print(f"[DEBUG] Search request for: '{query}'")
        
        # 1. Selvitä ticker nimen perusteella
        ticker = resolve_ticker(query, client)
        print(f"[DEBUG] Resolved ticker: {ticker}")
        if not ticker:
            return jsonify({"success": False, "error": f"Yhtiötä '{query}' ei löytynyt."}), 404
            
        # 2. Hae osakkeen data
        stock_data = get_stock_data(ticker)
        if not stock_data:
            return jsonify({"success": False, "error": f"Dataa tickerille {ticker} ei saatavilla."}), 404
            
        # 3. Luo mini-movers teksti tekoälylle (vain tämä yksi osake)
        movers_text = f"ANALYYSIKOHDE: {stock_data['ticker']}\n"
        movers_text += f"- Hinta: {stock_data['current_price']}$\n"
        movers_text += f"- Muutos: {stock_data['change_pct_1d']}%\n"
        movers_text += f"- Volyymi: {stock_data['volume']}\n"
        
        # 4. Pyydä AI-analyysi
        from src.news_fetcher import fetch_all_news, format_news_for_prompt
        news_articles = fetch_all_news(max_age_hours=168)
        news_text = format_news_for_prompt(news_articles, max_articles=40)
        
        scenarios = generate_scenarios(news_text, movers_text, client, watchlist_hint=ticker)
        
        if not scenarios:
             return jsonify({"success": False, "error": "AI-analyysin luonti epäonnistui."}), 500
             
        # 5. Tallenna kantaan manuaalisena hakuna (is_manual=True)
        add_scenario(scenarios[0], is_manual=True)
        
        return jsonify({"success": True, "ticker": ticker})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def calculate_rsi(data, window=14):
    try:
        import pandas as pd
        if len(data) < window + 1:
            return "N/A"
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        
        avg_gain = gain.rolling(window=window).mean()
        avg_loss = loss.rolling(window=window).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return round(val, 2) if not pd.isna(val) else "N/A"
    except:
        return "N/A"

# Endpoint yksittäisen osakkeen live-tietojen hakemiselle (modaalia varten)
@app.route('/api/stock_info/<ticker>', methods=['GET'])
def get_stock_details(ticker):
    try:
        import yfinance as yf
        import pandas as pd
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 1. Markkina-arvo
        mcap = info.get("marketCap", None)
        if mcap:
            if mcap >= 1e12: mcap_str = f"${mcap/1e12:.2f}T"
            elif mcap >= 1e9: mcap_str = f"${mcap/1e9:.2f}B"
            else: mcap_str = f"${mcap/1e6:.2f}M"
        else: mcap_str = "N/A"
            
        current_price = info.get("currentPrice", info.get("regularMarketPrice", 0))
        
        # Historiadata RSI:tä ja muutosta varten — 3kk takaa >= 15 datapistettä
        hist_1mo = stock.history(period="3mo")
        
        # 2. Päivän muutos
        change_pct = 0
        if len(hist_1mo) >= 2:
            prev_close = float(hist_1mo["Close"].iloc[-2])
            curr_close = float(hist_1mo["Close"].iloc[-1])
            if prev_close > 0:
                change_pct = ((curr_close - prev_close) / prev_close) * 100
        else:
            change_pct = info.get("regularMarketChangePercent", 0)

        # 3. RSI-arvo (laskettu 1kk datasta)
        rsi_val = calculate_rsi(hist_1mo)

        # 4. FCF (Vapaa kassavirta)
        fcf = info.get("freeCashflow", None)
        if fcf:
            if abs(fcf) >= 1e9: fcf_str = f"${fcf/1e9:.1f}B"
            else: fcf_str = f"${fcf/1e6:.1f}M"
        else: fcf_str = "N/A"

        # Muut tunnusluvut
        def fmt_pct(val):
            return f"{val * 100:.2f}%" if isinstance(val, (int, float)) else "N/A"
        
        def fmt_num(val, dec=2):
            return round(val, dec) if isinstance(val, (int, float)) else "N/A"

        # 16. Analyytikko-targetit
        targets = {
            "low": fmt_num(info.get("targetLowPrice")),
            "mean": fmt_num(info.get("targetMeanPrice")),
            "high": fmt_num(info.get("targetHighPrice")),
            "current": fmt_num(current_price)
        }

        # 17. Tuloshistoria (EPS)
        earnings_history = []
        try:
            dates = stock.earnings_dates
            if dates is not None and not dates.empty:
                reported = dates.dropna(subset=['Reported EPS']).head(4)
                for date, row in reported.iterrows():
                    earnings_history.append({
                        "period": date.strftime("%b %y"),
                        "actual": float(row['Reported EPS']) if not pd.isna(row['Reported EPS']) else 0,
                        "estimate": float(row['EPS Estimate']) if not pd.isna(row['EPS Estimate']) else 0
                    })
        except: pass

        # 18. Uutiset (3 kpl)
        news_list = []
        try:
            raw_news = stock.news[:3]
            for n in raw_news:
                news_list.append({
                    "title": n.get("title"),
                    "link": n.get("link"),
                    "publisher": n.get("publisher"),
                    "provider": n.get("providerPublishTime")
                })
        except: pass

        # Ladataan kootusti kaikki
        data = {
            "name": info.get("longName", ticker),
            "summary": info.get("longBusinessSummary", "Ei kuvausta.")[:400] + "...",
            "price": fmt_num(current_price),
            "changePercent": round(change_pct, 2),
            "pe": fmt_num(info.get("trailingPE")),               
            "pb": fmt_num(info.get("priceToBook")),               
            "ev_ebitda": fmt_num(info.get("enterpriseToEbitda")), 
            "eps_growth": fmt_pct(info.get("earningsQuarterlyGrowth")), 
            "rev_growth": fmt_pct(info.get("revenueGrowth")),     
            "net_margin": fmt_pct(info.get("profitMargins")),     
            "roe": fmt_pct(info.get("returnOnEquity")),           
            "fcf": fcf_str,                                       
            "debt_equity": fmt_num(info.get("debtToEquity")),     
            "div_yield": fmt_pct(info.get("dividendYield")),      
            "high52": fmt_num(info.get("fiftyTwoWeekHigh")),      
            "low52": fmt_num(info.get("fiftyTwoWeekLow")),        
            "rsi": rsi_val,                                       
            "beta": fmt_num(info.get("beta")),                    
            "marketCap": mcap_str,
            "targets": targets,
            "earnings_history": earnings_history,
            "news": news_list
        }

        return jsonify({"success": True, "data": data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
# Force redeploy Mon May  4 22:43:15 EEST 2026
# Forced redeploy 1777976493
