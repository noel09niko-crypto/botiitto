import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Tuki sekä paikalliselle .env että Streamlit Cloud secrets
if "GROQ_API_KEY" in st.secrets:
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]

st.set_page_config(
    page_title="Investing Bot",
    page_icon="📈",
    layout="wide",
)

st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button {
        background-color: #2ecc71;
        color: white;
        font-size: 18px;
        font-weight: bold;
        border-radius: 8px;
        padding: 12px 40px;
        border: none;
        width: 100%;
    }
    .stButton>button:hover { background-color: #27ae60; }
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }
    .green { color: #2ecc71; font-weight: bold; }
    .red { color: #e74c3c; font-weight: bold; }
    .recommendation-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 5px solid #2ecc71;
    }
</style>
""", unsafe_allow_html=True)


# --- Header ---
st.title("📈 Investing Bot")
st.caption("Analysoi markkinauutiset ja antaa 5 sijoitussuositusta")
st.divider()


# --- Tarkista API-avain ---
if not os.environ.get("GROQ_API_KEY"):
    st.error("GROQ_API_KEY puuttuu .env tiedostosta!")
    st.stop()


# --- Session state ---
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "movers" not in st.session_state:
    st.session_state.movers = None
if "last_run" not in st.session_state:
    st.session_state.last_run = None


# --- Käynnistysnappi ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run_btn = st.button("🔍 Analysoi markkinat nyt", use_container_width=True)


if st.session_state.last_run:
    st.caption(f"Viimeksi analysoitu: {st.session_state.last_run}")

st.divider()


# --- Aja analyysi ---
if run_btn:
    from src.news_fetcher import fetch_all_news, format_news_for_prompt
    from src.stock_analyzer import get_market_snapshot, get_top_movers, format_movers_for_prompt, WATCHLIST
    from src.ai_analyzer import analyze_market, quick_news_scan, get_client

    client = get_client()

    with st.status("Analysoidaan markkinoita...", expanded=True) as status:

        st.write("📰 Haetaan päivän uutiset...")
        articles = fetch_all_news(max_age_hours=24)
        st.write(f"✅ {len(articles)} artikkelia löydetty")

        st.write("🔎 Skannataan mainitut osakkeet...")
        news_text = format_news_for_prompt(articles, max_articles=60)
        mentioned = quick_news_scan(news_text, client) if articles else []
        if mentioned:
            st.write(f"✅ Mainitut osakkeet: {', '.join(mentioned)}")

        st.write("📊 Haetaan kurssitiedot...")
        all_tickers = list(dict.fromkeys(mentioned + WATCHLIST))
        snapshot = get_market_snapshot(all_tickers)
        st.write(f"✅ {len(snapshot)} osakkeen data haettu")

        st.write("🤖 AI analysoi markkinatilannetta...")
        movers = get_top_movers(snapshot, top_n=15)
        movers_text = format_movers_for_prompt(movers)

        top_tickers = (
            [s["ticker"] for s in movers["gainers"][:5]]
            + [s["ticker"] for s in movers["losers"][:5]]
            + mentioned[:5]
        )
        analysis = analyze_market(news_text, movers_text, list(dict.fromkeys(top_tickers)), client)

        st.session_state.analysis = analysis
        st.session_state.movers = movers
        st.session_state.last_run = datetime.now().strftime("%d.%m.%Y %H:%M")
        status.update(label="✅ Analyysi valmis!", state="complete")


# --- Näytä tulokset ---
if st.session_state.movers:
    movers = st.session_state.movers

    st.subheader("📊 Päivän liikkujat")
    col_g, col_l = st.columns(2)

    with col_g:
        st.markdown("**🟢 Nousijat**")
        for s in movers["gainers"][:8]:
            pct = s["change_pct_1d"]
            col_a, col_b, col_c = st.columns([2, 2, 1])
            col_a.write(f"**{s['ticker']}**")
            col_b.write(f"${s['current_price']}")
            col_c.markdown(f"<span class='green'>+{pct:.2f}%</span>", unsafe_allow_html=True)

    with col_l:
        st.markdown("**🔴 Laskijat**")
        for s in movers["losers"][:8]:
            pct = s["change_pct_1d"]
            col_a, col_b, col_c = st.columns([2, 2, 1])
            col_a.write(f"**{s['ticker']}**")
            col_b.write(f"${s['current_price']}")
            col_c.markdown(f"<span class='red'>{pct:.2f}%</span>", unsafe_allow_html=True)

    st.divider()


if st.session_state.analysis:
    st.subheader("💡 5 Sijoitussuositusta")

    sections = st.session_state.analysis.strip().split("\n\n")
    current_card = []
    card_num = 0

    for line in st.session_state.analysis.split("\n"):
        is_new = any(
            line.strip().startswith(f"{i}.") or
            line.strip().startswith(f"**{i}.") or
            (f"OSAKE {i}" in line) or
            (f"Suositus {i}" in line.title())
            for i in range(1, 6)
        )

        if is_new and current_card and card_num > 0:
            card_text = "\n".join(current_card)
            st.markdown(
                f'<div class="recommendation-card">{card_text.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )
            current_card = []

        if is_new:
            card_num += 1

        current_card.append(line)

    if current_card:
        card_text = "\n".join(current_card)
        st.markdown(
            f'<div class="recommendation-card">{card_text.replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.download_button(
        label="⬇️ Lataa analyysi tekstitiedostona",
        data=st.session_state.analysis,
        file_name=f"analyysi_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
    )


# --- Footer ---
st.markdown(
    "<br><center><small>⚠️ Tämä ei ole sijoitusneuvontaa. Tee aina oma analyysi ennen sijoituspäätöksiä.</small></center>",
    unsafe_allow_html=True,
)
