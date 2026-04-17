import os
from groq import Groq
from typing import List

SYSTEM_PROMPT = """Olet kokenut sijoitusstrategi ja osakeanalyytikko. Analysoit päivän uutisia ja
osakemarkkinoiden liikkeitä löytääksesi parhaat sijoitusmahdollisuudet.

Tehtäväsi on antaa TÄSMÄLLEEN 5 sijoitussuositusta. Kukin suositus sisältää:

1. OSAKE: Ticker ja yhtiön nimi
2. SUOSITUSTYYPPI: OSTA / LYHYT (shorttaus) / PIDÄ SILMÄLLÄ
3. KURSSI NYT: Nykyinen hinta
4. MIKSI JUURI NYT: Konkreettinen perustelu uutisten ja kurssidatan pohjalta (3-5 lausetta)
5. POSITIIVISET TEKIJÄT: Mitä tilanteessa on erityisen hyvää (bullet points)
6. PERUSTIEDOT: Toimiala, markkina-arvo, P/E, analyytikkojen arvio
7. RISKIT: Mitä voi mennä pieleen (bullet points, oltava rehellinen)
8. SIJOITUSHORISONTTI: Kuinka kauan pitää salkussa
9. MYYNTISTRATEGIA: Milloin myydä - konkreettiset trigger-pisteet
10. TAVOITEKURSSI: Realistinen tavoite ja stop-loss taso

Muotoile vastaus selkeästi, suomeksi. Ole rehellinen riskeistä.
TÄRKEÄÄ: Perusta suositukset AINA konkreettiseen dataan jota saat - älä keksi lukuja."""


def get_client():
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def analyze_market(news_text: str, movers_text: str, detailed_stocks: List[str] = None, client=None) -> str:
    if client is None:
        client = get_client()

    detailed_info = ""
    if detailed_stocks:
        from stock_analyzer import get_detailed_info
        details = [get_detailed_info(t) for t in detailed_stocks[:10]]
        detailed_info = "\n\nDETAILED STOCK INFO:\n" + "\n".join(details)

    user_message = f"""Analysoi seuraava markkinadata ja uutiset. Anna 5 parasta sijoitusmahdollisuutta.

=== OSAKEMARKKINOIDEN LIIKKEET ===
{movers_text}
{detailed_info}

=== PÄIVÄN UUTISET ===
{news_text}

Anna nyt 5 sijoitussuositusta yllä olevan datan perusteella."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=4000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content


def quick_news_scan(news_text: str, client=None) -> List[str]:
    if client is None:
        client = get_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Lue nämä uutiset ja listaa lyhyesti (max 10 kpl) osakkeiden ticker-symbolit "
                f"jotka mainitaan tai joihin uutiset eniten vaikuttavat. Vastaa vain lista tickereistä.\n\n{news_text[:3000]}"
            )
        }],
    )

    text = response.choices[0].message.content
    tickers = []
    for word in text.split():
        word = word.strip(".,()[]\"'").upper()
        if 1 < len(word) <= 5 and word.isalpha():
            tickers.append(word)

    return list(dict.fromkeys(tickers))[:10]
