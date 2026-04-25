from flask import Flask, render_template, jsonify, request
import os
from datetime import datetime
from dotenv import load_dotenv

from src.database import init_db, get_active_scenarios, get_favorite_scenarios, toggle_favorite, get_db_connection
from src.background_worker import start_background_worker

load_dotenv()

app = Flask(__name__)

# Alusta tietokanta (myös kun gunicorn importtaa)
init_db()

# Oletusreitti, joka tarjoilee HTML-pääsivun
@app.route('/')
def index():
    return render_template('index.html')

# Hakee kaikki aktiiviset (ja uudet) mahdollisuudet
@app.route('/api/scenarios', methods=['GET'])
def fetch_scenarios():
    try:
        active = get_active_scenarios(limit=15)
        favorites = get_favorite_scenarios()
        
        return jsonify({
            "success": True,
            "active": active,
            "favorites": favorites,
            "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M")
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

# Endpoint manuaaliseen 2h skannauksen herättämiseen
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


# MANUAALINEN HAKU JA ANALYYSI
@app.route('/api/search_and_analyze', methods=['POST'])
def search_and_analyze():
    data = request.json
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({"success": False, "error": "Hakusana puuttuu"}), 400
        
    try:
        from src.ai_analyzer import resolve_ticker, generate_scenarios, get_client
        from src.stock_analyzer import get_stock_data, format_movers_for_prompt
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
        
        # 4. Pyydä AI-analyysi (ilman uutisia, tai hae uutisia jos halutaan)
        from src.news_fetcher import fetch_all_news, format_news_for_prompt
        news_articles = fetch_all_news(max_age_hours=48) # Hieman laajempi haku manuaaliselle
        news_text = format_news_for_prompt(news_articles, max_articles=40)
        
        scenarios = generate_scenarios(news_text, movers_text, client)
        
        if not scenarios:
             return jsonify({"success": False, "error": "AI-analyysin luonti epäonnistui."}), 500
             
        # 5. Tallenna kantaan manuaalisena hakuna (is_manual=True)
        add_scenario(scenarios[0], is_manual=True)
        
        return jsonify({"success": True, "ticker": ticker})
        
        return jsonify({"success": True, "ticker": ticker})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def calculate_rsi(data, window=14):
    try:
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

        # Ladataan kootusti kaikki 15
        data = {
            "name": info.get("longName", ticker),
            "summary": info.get("longBusinessSummary", "Ei kuvausta.")[:400] + "...",
            "price": fmt_num(current_price),
            "changePercent": round(change_pct, 2),
            "pe": fmt_num(info.get("trailingPE")),               # 1
            "pb": fmt_num(info.get("priceToBook")),               # 2
            "ev_ebitda": fmt_num(info.get("enterpriseToEbitda")), # 3
            "eps_growth": fmt_pct(info.get("earningsQuarterlyGrowth")), # 4
            "rev_growth": fmt_pct(info.get("revenueGrowth")),     # 5
            "net_margin": fmt_pct(info.get("profitMargins")),     # 6
            "roe": fmt_pct(info.get("returnOnEquity")),           # 7
            "fcf": fcf_str,                                       # 8
            "debt_equity": fmt_num(info.get("debtToEquity")),     # 9
            "div_yield": fmt_pct(info.get("dividendYield")),      # 10
            "high52": fmt_num(info.get("fiftyTwoWeekHigh")),      # 11
            "low52": fmt_num(info.get("fiftyTwoWeekLow")),        # 12
            "rsi": rsi_val,                                       # 13
            "beta": fmt_num(info.get("beta")),                    # 14
            "marketCap": mcap_str                                 # 15
        }

        return jsonify({"success": True, "data": data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Alusta tietokanta ennen ku käynnistetään
    init_db()
    
    # Käynnistetään taustamoottori, joka keksii uusia skenaarioita
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        iv = int(os.environ.get("INTERVAL_HOURS", 2))
        start_background_worker(interval_hours=iv)
    
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
