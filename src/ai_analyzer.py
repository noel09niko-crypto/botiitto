import os
import json
from groq import Groq
import anthropic
from typing import List, Optional

SYSTEM_PROMPT = """Olet aloittelijaystävällinen mutta ammattimainen sijoitusanalyytikko. Etsit ja esittelet potentiaalisesti markkinoiden väärinhinnoittelemia osakkeita.
Jos annetussa datassa ei ole OIKEASTI hyviä kohteita näiden sääntöjen puitteissa, palauta TYHJÄ LISTA []. Älä pakota analyyseja!

PERUSAJATUS:
Markkinat eivät aina hinnoittele osaketta oikein — joko pelko painaa kurssia liian alas, maailman muutos ei ole vielä täysin näkynyt hinnassa, tai yhtiöllä on edessä jotain, jonka potentiaalia ei vielä arvosteta tarpeeksi. Etsit tilanteita joissa nousuvaraa on selkeästi jäljellä.

MITÄ ETSITÄÄN (Analyysin runko):
1. YHTIÖN ESITTELY (aloittelijaystävällinen): Selitä aivan ensimmäiseksi erittäin selkeästi mitä yritys tekee. Puhu kuin selittäisit sen kaverille.
2. NOUSUVARA (Joka ei näy kurssissa): Yhtiöllä on tulossa jotain konkreettista. Vaikka markkinat huomaisivat tilanteen, nousuvaraa pitää olla jäljellä.
3. MAAILMAN MUUTOS: Mikä globaali trendi tai tapahtuma suosii yhtiötä? Kysy: kuka hyötyy tästä oikeasti? (esim. öljyn hinta laskee -> lentoyhtiö hyötyy).
4. MARKKINAPELKO (Ylikorostunut): Mikä paniikki tai väärinkäsitys painaa kurssia? Miksi yhtiön liiketoiminta on kuitenkin kunnossa? (Edellyttää katalyyttiä 6kk sisään).
5. ARVOSTUS: Onko arvostus kohtuullinen? Ei saa olla ylikuumentunut.
6. RISKINHALLINTA: Määrittele sääntö, että jos alkuperäinen syy ostaa osoittautuu vääräksi, myydään välittömästi.

VASTAA AINA JSON-MUODOSSA:
[
  {
    "title": "HOUKUTTELEVA OTSIKKO TÄSTÄ TILANTEESTA",
    "tickers": "TICKER",
    "summary_title": "Mitä yhtiö tekee?",
    "summary": "Selkokielinen, täysin aloittelijalle ymmärrettävä selitys yhtiön liiketoiminnasta.",
    "global_title": "Maailman muutos, joka suosii",
    "global_context": "Selitys markkinatrendistä tai maailmantilanteesta, ja miten tämä yhtiö hyötyy siitä salaa/epäsuorasti.",
    "reasoning_title": "Miksi kurssissa on yhä nousuvaraa?",
    "reasoning": "Perustelut sille, miksi potentiaalia ei ole vielä hinnoiteltu kurssiin ja mikä on katalyytti.",
    "history_title": "Ylikorostunut markkinapelko",
    "company_history": "Mikä on se paniikki tai väärinkäsitys, joka pitää hinnan alhaalla? Miksi markkinat ovat väärässä?",
    "metrics_title": "Kohtuullinen arvostus",
    "metrics_explanation": "Selitä selkokielellä, miksi arvostus ei ole ylikuumentunut.",
    "horizon_title": "Riskinhallinta ja Exit-suunnitelma",
    "time_horizon": "Jos oletuksemme on väärin, myydään heti. Mitä merkkejä pitää seurata?",
    "recommendation": "OSTA",
    "risk_level": "Matala, Keskisuuri tai Korkea",
    "confidence": 85,
    "sector": "Toimiala"
  }
]

Vastaa pelkällä validilla JSON-taulukolla (array). Älä kirjoita mitään muuta.
"""

def get_client():
    return get_anthropic_client() or Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    return anthropic.Anthropic(api_key=key)

def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 1000) -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille usealla fallbackilla"""
    # 1. Kokeillaan Anthropicia (Claude) useilla malleilla
    anth_client = get_anthropic_client()
    if anth_client:
        for model in ["claude-sonnet-4-6", "claude-3-5-sonnet-20240620", "claude-3-sonnet-20240229"]:
            try:
                resp = anth_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_msg if system_msg else "",
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.content[0].text
            except Exception as e:
                print(f"Claude ({model}) error: {e}")
                continue
    
    # 2. Fallback Groqiin (Llama)
    try:
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_msg} if system_msg else {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Groq error: {e}")
    
    return ""

def generate_scenarios(news_text: str, movers_text: str, client=None) -> List[dict]:
    user_message = f"Luo 1-3 syvällistä analyysia näistä tiedoista:\n\nDATA:\n{movers_text}\n\nUUTISET:\n{news_text[:4000]}"
    content = _get_completion(user_message, system_msg=SYSTEM_PROMPT, max_tokens=8000)
    
    try:
        # Poista mahdolliset markdown-koodilaatikot
        if "```" in content:
            content = content.split("```json")[-1].split("```")[0] if "```json" in content else content.split("```")[1].split("```")[0]
        
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        
        data = json.loads(content)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list): return v
            return [data]
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Yritä pelastaa katkaistu JSON – ota ainakin ensimmäinen analyysi
        try:
            first_obj = content[content.find("{"):]
            # Etsi ensimmäisen täyden objektin loppu
            depth = 0
            for i, c in enumerate(first_obj):
                if c == '{': depth += 1
                elif c == '}': depth -= 1
                if depth == 0:
                    single = json.loads(first_obj[:i+1])
                    return [single]
            return []
        except:
            return []
    except:
        return []

def quick_news_scan(news_text: str, client=None) -> List[str]:
    prompt = f"Poimi uutisista 1-10 teknologia-tickerit. Vastaa VAIN JSON: {{\"tickers\": [\"AAPL\", ...]}}\n\nUUTISET:\n{news_text[:4000]}"
    content = _get_completion(prompt, max_tokens=300)
    try:
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        data = json.loads(content)
        return [str(t).upper().strip() for t in data.get("tickers", [])]
    except:
        return []

def resolve_ticker(query: str, client=None) -> Optional[str]:
    if 1 < len(query) <= 5 and query.isalpha() and query.isupper(): return query
    prompt = f"Mikä on '{query}' virallinen pörssitunnus usassa? Vastaa VAIN JSON: {{\"ticker\": \"TUNNUS\"}}"
    content = _get_completion(prompt, max_tokens=100)
    try:
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        data = json.loads(content)
        return data.get("ticker").upper() if data.get("ticker") else None
    except:
        return None

def validate_scenario(scenario: dict, latest_news: str, client=None) -> dict:
    prompt = f"""ARVIOI ANALYYSIN JATKO (HODL-STRATEGIA):
    Analyysi: {scenario.get('title')} ({scenario.get('recommendation')})
    
    Tärkeä ohje: Sijoitushorisontti on PITKÄ (kuukausia/vuosia). Älä poista analyysia helposti.
    
    ASETA STATUS:
    - 'VALID': Jos analyysin perusajatus on yhä kunnossa. Hiljaisuus uutisissa EI ole syy poistolle.
    - 'UPDATE': Jos on tullut jotain uutta kiinnostavaa, joka tarkentaa kuvaa.
    - 'INVALID': VAIN jos yhtiön tilanteessa on tapahtunut jotain TODELLA kriittistä ja pahaa, tai jos alkuperäinen noususyy on todistetusti poistunut kokonaan.
    
    TUOREIMMAT UUTISET:
    {latest_news[:3000]}
    
    VASTAA JSON: {{"status": "VALID"/"INVALID"/"UPDATE", "reason": "Lyhyt perustelu"}}"""
    content = _get_completion(prompt, max_tokens=300)
    try:
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        return json.loads(content)
    except:
        return {"status": "VALID", "reason": "Check failed"}
