import os
import json
from groq import Groq
from typing import List

SYSTEM_PROMPT = """Olet sijoitusanalyytikko. Analysoit AINOASTAAN teknologiayhtiöitä. Kirjoitat suomeksi.

SÄÄNNÖT:
- Valitse aina yksi konkreettinen teknologiayhtiö (esim. Nvidia, Apple, Cloudflare, Palantir).
- Kirjoita lyhyesti ja selkeästi. Ei turhaa jaarittelua.
- Käytä yksinkertaista kieltä – kuin selittäisit kaverille.
- Älä kirjoita listoja. Kaikki tekstit ovat lyhyitä kappaleita (2-4 lausetta maksimissaan).

VASTAA TÄSSÄ JSON-MUODOSSA:
{
  "otsikko": "Yhtiön koko virallinen nimi",
  "ticker": "TICKER",
  "pikakuvaus": "1-2 lausetta: mitä yhtiö tekee, missä maassa, kuinka iso.",
  "maailman_tapahtumat": "1-2 lausetta: mikä maailman tapahtuma tai trendi hyödyttää juuri tätä yhtiötä nyt. Ole konkreettinen.",
  "miksi_nousee": "2-3 lausetta: miksi juuri tämä osake voi nousta. Mainitse jokin luku jos mahdollista.",
  "yhtiön_numerot": "2-3 lausetta: kerro liikevaihdon kasvu, kate tai muu avainluku selkokielellä.",
  "ostohorisontti": "1-2 lausetta: kuinka pitkäksi aikaa tämä idea on hyvä ja mitä seurata.",
  "yhtiön_tarina": "2-3 lausetta: yhtiön historia ja viimeisin iso uutinen.",
  "suositus": "OSTA (Core) tai OSTA (Speculative)",
  "riskitaso": "Matala tai Korkea",
  "luottamus": 85,
  "toimiala": "Teknologia"
}

Vastaa VAIN validilla JSONilla. Ei muuta tekstiä."""

def get_client():
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def generate_scenarios(news_text: str, movers_text: str, client=None) -> List[dict]:
    if client is None:
        client = get_client()

    user_message = f"""Luo 1-3 syvällistä analyysia (yksi per yhtiö) näiden uutisten pohjalta:
{news_text[:5000]}

VASTAA PELKÄLLÄ JSONILLA!"""

    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    
    for model_name in models:
        try:
            print(f"  Trying model: {model_name}")
            response = client.chat.completions.create(
                model=model_name,
                max_tokens=4000,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)
            
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        return v
                return [data]
                
            elif isinstance(data, list):
                return data
                
            return []
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str:
                print(f"  Rate limit on {model_name}, trying fallback...")
                continue
            print(f"Error generating scenarios: {e}")
            return []
    
    print("All models exhausted.")
    return []

def quick_news_scan(news_text: str, client=None) -> List[str]:
    if client is None:
        client = get_client()
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=200,
        messages=[{"role": "user", "content": f"Listaa max 10 ticker-symbolia uutisista:\n\n{news_text[:3000]}"}],
    )
    text = response.choices[0].message.content
    tickers = []
    for word in text.split():
        word = word.strip(".,()[]\"'").upper()
        if 1 < len(word) <= 5 and word.isalpha():
            tickers.append(word)
    return list(dict.fromkeys(tickers))[:10]
