import os
import json

# Valitse tietokanta: PostgreSQL pilvessä, SQLite paikallisesti
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # Render antaa 'postgres://' mutta psycopg2 vaatii 'postgresql://'
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bot_database.db')

def init_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scenarios (
                id SERIAL PRIMARY KEY,
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
                competitive_landscape TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                is_favorite BOOLEAN DEFAULT FALSE,
                is_manual BOOLEAN DEFAULT FALSE,
                is_pinned BOOLEAN DEFAULT FALSE,
                price_change_24h REAL DEFAULT 0.0,
                summary_title TEXT,
                global_title TEXT,
                reasoning_title TEXT,
                metrics_title TEXT,
                horizon_title TEXT,
                history_title TEXT,
                is_updated BOOLEAN DEFAULT FALSE,
                deactivation_reason TEXT,
                deactivated_at TIMESTAMP
            )
        ''')
        # PostgreSQL-migraatiot: lisää puuttuvat sarakkeet jos ei ole
        pg_migrations = [
            ("is_pinned", "BOOLEAN DEFAULT FALSE"),
            ("is_manual", "BOOLEAN DEFAULT FALSE"),
            ("price_change_24h", "REAL DEFAULT 0.0"),
            ("summary_title", "TEXT"),
            ("global_title", "TEXT"),
            ("reasoning_title", "TEXT"),
            ("metrics_title", "TEXT"),
            ("horizon_title", "TEXT"),
            ("history_title", "TEXT"),
            ("is_updated", "BOOLEAN DEFAULT FALSE"),
            ("competitive_landscape", "TEXT"),
            ("deactivation_reason", "TEXT"),
            ("deactivated_at", "TIMESTAMP"),
        ]
        for col, col_type in pg_migrations:
            try:
                cursor.execute(f"ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS {col} {col_type}")
            except Exception:
                pass
        conn.commit()
        conn.close()

    else:
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
                competitive_landscape TEXT,
                is_active BOOLEAN DEFAULT 1,
                is_favorite BOOLEAN DEFAULT 0,
                is_manual BOOLEAN DEFAULT 0,
                is_pinned BOOLEAN DEFAULT 0,
                price_change_24h REAL DEFAULT 0.0
            )
        ''')
        # SQLite migraatiot
        cols = [
            ("supporting_news", "TEXT"), 
            ("global_context", "TEXT"), 
            ("metrics_explanation", "TEXT"), 
            ("company_history", "TEXT"),
            ("is_pinned", "BOOLEAN DEFAULT 0"),
            ("is_manual", "BOOLEAN DEFAULT 0"),
            ("price_change_24h", "REAL DEFAULT 0.0"),
            ("summary_title", "TEXT"),
            ("global_title", "TEXT"),
            ("reasoning_title", "TEXT"),
            ("metrics_title", "TEXT"),
            ("horizon_title", "TEXT"),
            ("history_title", "TEXT"),
            ("is_updated", "BOOLEAN DEFAULT 0"),
            ("competitive_landscape", "TEXT"),
            # Poistoloki — tallentaa aina MIKSI analyysi poistettiin
            ("deactivation_reason", "TEXT"),
            ("deactivated_at", "TIMESTAMP"),
        ]
        for col, col_type in cols:
            try:
                cursor.execute(f"ALTER TABLE scenarios ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

def get_db_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def _fetchall_as_dicts(cursor, rows):
    """Muuntaa sekä SQLite- että PostgreSQL-rivit sanakirjoiksi."""
    if USE_POSTGRES:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    else:
        return [dict(row) for row in rows]

def _placeholder():
    """Palauttaa oikean placeholder-merkin tietokannalle."""
    return "%s" if USE_POSTGRES else "?"

def add_scenario(data, is_pinned=False, is_manual=False, price_change=0.0, is_updated=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    p = _placeholder()
    
    def ensure_str(val):
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
        return val

    def get_field(data, keys, default="Analyysi valmistuu..."):
        for k in keys:
            if k in data and data[k] and str(data[k]).strip().lower() not in ["n/a", "none", "null", ""]:
                return data[k]
        return default

    title = get_field(data, ["title", "otsikko", "nimi", "company", "yhtiö"], "Tuntematon Yhtiö")
    tickers = get_field(data, ["tickers", "ticker", "tarkkavala", "symboli"], "YLEINEN")
    conf = get_field(data, ["confidence", "luottamus", "varmuus"], 75)

    if not is_manual:
        cursor.execute(f'SELECT id, confidence FROM scenarios WHERE tickers = {p} AND is_active = TRUE AND is_favorite = FALSE', (ensure_str(tickers),))
        existing = cursor.fetchone()
        if existing:
            ex_id = existing[0] if USE_POSTGRES else existing['id']
            ex_conf = existing[1] if USE_POSTGRES else existing['confidence']
            if conf <= ex_conf:
                conn.close()
                return False
            else:
                cursor.execute(f'UPDATE scenarios SET is_active = FALSE WHERE id = {p}', (ex_id,))
    else:
        cursor.execute(f'UPDATE scenarios SET is_active = FALSE WHERE tickers = {p}', (ensure_str(tickers),))

    summary = get_field(data, ["summary", "johdanto", "yhteenveto", "tiivistelmä", "kuvaus", "pikakuvaus"], "Tarkempi tiivistelmä tulossa.")
    reasoning = get_field(data, ["reasoning", "perustelut", "selite", "analyysi", "miksi_nousee"], "Analyysi osakkeen nousuajureista valmistuu.")
    risks = get_field(data, ["invalidation_risks", "riskit", "uhka", "riski"], "Riskiarviointi kesken.")
    news = get_field(data, ["supporting_news", "uutiset", "news", "viimeaikaiset_tapahtumat"], "Ei tuoreita uutisviitteitä.")
    sector = get_field(data, ["sector", "toimiala", "ala"], "Teknologia")
    horizon = get_field(data, ["time_horizon", "aikajänne", "horisontti", "aikaväli", "ostohorisontti"], "Seuraa tilannetta viikoittain.")
    history = get_field(data, ["historical_comparison", "historia", "vertailu"], "Historiallinen vertailu analysoitavana.")
    global_context = get_field(data, ["global_context", "maailman_tapahtumat", "konteksti", "mitä_maailmalla_tapahtuu"], "Maailmanmarkkinoiden tilanne analysoitavana tämän yhtiön osalta.")
    metrics_exp = get_field(data, ["metrics_explanation", "yhtiön_numerot", "tunnusluvut_selitettynä", "numerot"], "Tunnuslukujen tarkempi analyysi päivittyy pian.")
    company_hist = get_field(data, ["company_history", "yhtiön_historia", "tarina", "yhtiön_tarina"], "Yhtiön tausta ja historia tarkentuu seuraavassa päivityksessä.")
    competitive_edge = get_field(data, ["competitive_landscape", "kilpailuasetelma", "kilpailutilanne", "kilpailu", "competitive_edge"], "Kilpailutilanteen analyysi valmistuu.")

    # Dynaamiset otsikot
    sum_title = get_field(data, ["pikakuvaus_otsikko", "summary_title"], "Pikakuvaus yhtiöstä")
    glob_title = get_field(data, ["maailman_tapahtumat_otsikko", "global_title"], "Mitä maailmalla tapahtuu?")
    reasons_title = get_field(data, ["perustelut_otsikko", "reasoning_title"], "Miksi juuri tämä osake nousee?")
    met_title = get_field(data, ["yhtiön_numerot_otsikko", "metrics_title"], "Yhtiön luvut sanallistettuna")
    hor_title = get_field(data, ["ostohorisontti_otsikko", "horizon_title"], "Ostohorisontti")
    hist_title = get_field(data, ["yhtiön_tarina_otsikko", "history_title"], "Yhtiön historia")

    cursor.execute(f'''
        INSERT INTO scenarios (
            title, tickers, summary, reasoning, time_horizon, 
            recommendation, risk_level, confidence, historical_comparison, 
            invalidation_risks, sector, supporting_news,
            global_context, metrics_explanation, company_history, competitive_landscape, is_pinned, is_manual, is_favorite, price_change_24h,
            summary_title, global_title, reasoning_title, metrics_title, horizon_title, history_title, is_updated
        )
        VALUES ({', '.join([p]*27)})
    ''', (
        ensure_str(title), ensure_str(tickers), ensure_str(summary), ensure_str(reasoning), ensure_str(horizon),
        ensure_str(get_field(data, ["recommendation", "suositus"], "Tarkkaile")), 
        ensure_str(get_field(data, ["risk_level", "riskitaso", "riski"], "Keskisuuri")), 
        conf, ensure_str(history), ensure_str(risks), ensure_str(sector), ensure_str(news),
        ensure_str(global_context), ensure_str(metrics_exp), ensure_str(company_hist), ensure_str(competitive_edge),
        True if is_pinned else False, True if is_manual else False, False, price_change,
        ensure_str(sum_title), ensure_str(glob_title), ensure_str(reasons_title), 
        ensure_str(met_title), ensure_str(hor_title), ensure_str(hist_title),
        True if is_updated else False
    ))
    conn.commit()
    conn.close()
    return True

def get_active_scenarios(limit=25):
    conn = get_db_connection()
    cursor = conn.cursor()
    p = _placeholder()
    cursor.execute(f'SELECT * FROM scenarios WHERE is_active = TRUE AND is_favorite = FALSE ORDER BY confidence DESC, created_at DESC LIMIT {p}', (limit,))
    rows = cursor.fetchall()
    result = _fetchall_as_dicts(cursor, rows)
    conn.close()
    return result

def get_favorite_scenarios():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM scenarios WHERE is_favorite = TRUE ORDER BY created_at DESC')
    rows = cursor.fetchall()
    result = _fetchall_as_dicts(cursor, rows)
    conn.close()
    return result

def get_favorite_tickers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT tickers FROM scenarios WHERE is_favorite = TRUE')
    rows = cursor.fetchall()
    conn.close()
    if USE_POSTGRES:
        return [row[0] for row in rows]
    return [row['tickers'] for row in rows]

def toggle_favorite(scenario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    p = _placeholder()
    cursor.execute(f'SELECT is_favorite, is_manual FROM scenarios WHERE id = {p}', (scenario_id,))
    row = cursor.fetchone()
    if row:
        is_fav = row[0] if USE_POSTGRES else row['is_favorite']
        is_man = row[1] if USE_POSTGRES else row['is_manual']
        new_status = not is_fav
        if is_man and not new_status:
            cursor.execute(f'UPDATE scenarios SET is_favorite = FALSE, is_active = FALSE WHERE id = {p}', (scenario_id,))
        else:
            cursor.execute(f'UPDATE scenarios SET is_favorite = {p} WHERE id = {p}', (new_status, scenario_id))
        conn.commit()
    conn.close()

def deactivate_scenario(scenario_id, reason: str = "Ei perustelua kirjattu"):
    """Merkitsee analyysin passiiviseksi ja tallentaa AINA syyn lokiin."""
    from datetime import datetime
    conn = get_db_connection()
    cursor = conn.cursor()
    p = _placeholder()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        f'UPDATE scenarios SET is_active = FALSE, deactivation_reason = {p}, deactivated_at = {p} WHERE id = {p}',
        (reason, now, scenario_id)
    )
    conn.commit()
    conn.close()
    print(f"  [POISTO-LOKI] ID {scenario_id}: {reason}")

def prune_old_scenarios(keep_limit=50):
    """Piilottaa ylimääräiset heikkolaatuisimmat analyysit dashboardilta.
    EI KOSKAAN POISTA RIVEJÄ TIETOKANNASTA — historia säilyy aina.
    Suosikkeja tai pinnattuja ei kosketa.
    """
    from datetime import datetime
    conn = get_db_connection()
    cursor = conn.cursor()
    p = _placeholder()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reason = f"Automaattinen siivous: dashboard täynnä (raja={keep_limit}). Analyysi arkistoitu, ei poistettu."

    if USE_POSTGRES:
        cursor.execute(f'''
            UPDATE scenarios
            SET is_active = FALSE,
                deactivation_reason = {p},
                deactivated_at = {p}
            WHERE id IN (
                SELECT id FROM scenarios
                WHERE is_favorite = FALSE AND is_pinned = FALSE AND is_active = TRUE
                ORDER BY confidence ASC, created_at ASC
                OFFSET {p}
            )
        ''', (reason, now, keep_limit))
    else:
        cursor.execute(f'''
            UPDATE scenarios
            SET is_active = 0,
                deactivation_reason = {p},
                deactivated_at = {p}
            WHERE id IN (
                SELECT id FROM scenarios
                WHERE is_favorite = 0 AND is_pinned = 0 AND is_active = 1
                ORDER BY confidence ASC, created_at ASC
                LIMIT -1 OFFSET {p}
            )
        ''', (reason, now, keep_limit))

    count = cursor.rowcount
    if count > 0:
        print(f"  [ARKISTO] {count} analyysia arkistoitu dashboardilta (ei poistettu tietokannasta).")
    conn.commit()
    conn.close()
