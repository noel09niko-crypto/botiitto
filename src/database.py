import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bot_database.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            tickers TEXT NOT NULL,
            summary TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            time_horizon TEXT NOT NULL,
            recommendation TEXT DEFAULT 'Tarkkaile',
            risk_level TEXT DEFAULT 'Keskisuuri',
            confidence INTEGER DEFAULT 50,
            historical_comparison TEXT,
            invalidation_risks TEXT,
            sector TEXT DEFAULT 'Yleinen',
            supporting_news TEXT,
            global_context TEXT,
            metrics_explanation TEXT,
            company_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            is_favorite BOOLEAN DEFAULT 0
        )
    ''')
    
    # Migraatio: Lisää sarakkeet jos ne puuttuvat
    cols = ["supporting_news", "global_context", "metrics_explanation", "company_history"]
    for col in cols:
        try:
            cursor.execute(f"ALTER TABLE scenarios ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
        
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_scenario(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    def ensure_str(val):
        if isinstance(val, (list, dict)):
            import json
            return json.dumps(val, ensure_ascii=False)
        return val

    # Smart mapper for AI-generated keys
    def get_field(data, keys, default="N/A"):
        for k in keys:
            if k in data:
                return data[k]
        return default

    title = get_field(data, ["title", "otsikko", "nimi", "company", "yhtiö"])
    tickers = get_field(data, ["tickers", "ticker", "tarkkavala", "symboli"])
    summary = get_field(data, ["summary", "johdanto", "yhteenveto", "tiivistelmä", "kuvaus", "pikakuvaus"])
    reasoning = get_field(data, ["reasoning", "perustelut", "selite", "analyysi", "miksi_nousee"])
    risks = get_field(data, ["invalidation_risks", "riskit", "uhka", "riski"])
    news = get_field(data, ["supporting_news", "uutiset", "news", "viimeaikaiset_tapahtumat"])
    sector = get_field(data, ["sector", "toimiala", "ala"])
    horizon = get_field(data, ["time_horizon", "aikajänne", "horisontti", "aikaväli", "ostohorisontti"])
    history = get_field(data, ["historical_comparison", "historia", "vertailu"])
    
    # Uudet storytelling-kentät
    global_context = get_field(data, ["global_context", "maailman_tapahtumat", "konteksti", "mitä_maailmalla_tapahtuu"])
    metrics_exp = get_field(data, ["metrics_explanation", "yhtiön_numerot", "tunnusluvut_selitettynä", "numerot"])
    company_hist = get_field(data, ["company_history", "yhtiön_historia", "tarina", "yhtiön_tarina"])

    cursor.execute('''
        INSERT INTO scenarios (
            title, tickers, summary, reasoning, time_horizon, 
            recommendation, risk_level, confidence, historical_comparison, 
            invalidation_risks, sector, supporting_news,
            global_context, metrics_explanation, company_history
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ensure_str(title),
        ensure_str(tickers),
        ensure_str(summary),
        ensure_str(reasoning),
        ensure_str(horizon),
        ensure_str(get_field(data, ["recommendation", "suositus", "toimenpide"], "OSTA (Core)")),
        ensure_str(get_field(data, ["risk_level", "riskitaso", "riski_taso"], "Matala")),
        get_field(data, ["confidence", "luottamus", "varmuus"], 75),
        ensure_str(history),
        ensure_str(risks),
        ensure_str(sector),
        ensure_str(news),
        ensure_str(global_context),
        ensure_str(metrics_exp),
        ensure_str(company_hist)
    ))
    conn.commit()
    conn.close()

def get_active_scenarios(limit=25):
    conn = get_db_connection()
    scenarios = conn.execute('SELECT * FROM scenarios WHERE is_active = 1 AND is_favorite = 0 ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return [dict(ix) for ix in scenarios]

def get_favorite_scenarios():
    conn = get_db_connection()
    scenarios = conn.execute('SELECT * FROM scenarios WHERE is_favorite = 1 ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(ix) for ix in scenarios]

def toggle_favorite(scenario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute('SELECT is_favorite FROM scenarios WHERE id = ?', (scenario_id,)).fetchone()
    if row:
        new_status = 0 if row['is_favorite'] else 1
        cursor.execute('UPDATE scenarios SET is_favorite = ? WHERE id = ?', (new_status, scenario_id))
        conn.commit()
    conn.close()
