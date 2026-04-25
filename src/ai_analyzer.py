import os
import json
from groq import Groq
import anthropic
from typing import List, Optional

SYSTEM_PROMPT = """Olet kokenut osakeanalyytikko, joka osaa selittää vaikeat asiat niin yksinkertaisesti, että kuka tahansa ymmärtää ne. Kirjoitat suomeksi.

TÄRKEÄT KIELISÄÄNNÖT:
- ÄLÄ KÄYTÄ vaikeita sanoja tai sijoitusalan ammattisanoja.
- Jos joudut käyttämään numeroa tai termiä, selitä se heti arkikielellä (esim. "kate" on "myynnistä jäävä voitto").
- Käytä lyhyitä, selkeitä lauseita. Puhu kuin selittäisit asiaa ystävälle, joka ei tiedä pörssistä mitään.
- Vältä "hienostunutta" kieltä. Valitse aina mahdollisimman tavallinen ja ymmärrettävä sana.

ANALYYSIKETJU:
1. MARKKINAPELKO: Miksi kaikki pelkäävät tätä osaketta juuri nyt? Onko pelko turha vai oikea? Selitä miksi markkinat saattavat olla väärässä.
2. SYY NOUSUUN (Katalyytti): Mikä konkreettinen tapahtuma nostaa osaketta pian? (esim. uusi tuote tai hyvä tulos päivä).
3. VAIKUTUKSET: Miten tämä vaikuttaa muihin saman alan yrityksiin?
4. RAHA-ASLAT: Selitä yrityksen rahatilanne tavallisilla sanoilla. Käytä numeroita vain tukemaan tarinaa.
5. MAAILMAN TILANNE: Miten korot tai maailman tapahtumat vaikuttavat SUORAAN tähän yritykseen?
6. TEKNINEN TILANNE: Suosittele ostamista VAIN, jos hinta on "sopivan kylmä" eikä liian kallis juuri nyt (RSI on matala, ollaan lähellä tukitasoa ja hinta on kääntymässä ylöspäin). Jos osake on jo noussut liikaa, sano "TARKKAILE" tai "VÄLTÄ".
7. RISKIT: Sano lopuksi lyhyesti mitkä asiat voivat mennä pieleen.

VASTAA TÄSSÄ JSON-MUODOSSA:
{
  "otsikko": "YHTIÖ: Selkeä ja houkutteleva otsikko",
  "ticker": "TICKER",
  "pikakuvaus_otsikko": "Miksi kaikki pelkäävät tätä nyt?",
  "pikakuvaus": "Selitä markkinoiden pelko ja väärinkäsitys mahdollisimman tavallisilla sanoilla.",
  "maailman_tapahtumat_otsikko": "Mikä nostaa hintaa pian?",
  "maailman_tapahtumat": "Selitä nousun syy ja vaikutus muihin yrityksiin arkikielellä.",
  "perustelut_otsikko": "Yrityksen rahat ja maailman tilanne",
  "perustelut": "Selitä yrityksen talous ja maailman tapahtumien vaikutus ilman vaikeita sanoja.",
  "yhtiön_numerot_otsikko": "Onko hinta sopiva juuri nyt?",
  "yhtiön_numerot": "Analyysi siitä, onko osake liian kallis vai sopiva ostoon nykyisellä hinnalla.",
  "ostohorisontti_otsikko": "Mikä voi mennä pieleen? (Riskit)",
  "ostohorisontti": "Listaa riskit lyhyesti ja selkeästi.",
  "yhtiön_tarina_otsikko": "Yhteenveto",
  "yhtiön_tarina": "Loppupäätelmä selkokielellä.",
  "suositus": "OSTA (Vahva), OSTA (Kokeileva), TARKKAILE, VÄLTÄ tai MYY",
  "riskitaso": "Matala, Keskisuuri tai Korkea",
  "luottamus": 85,
  "toimiala": "Teknologia"
}

LAATUTAKUU JA HARKINTA (VISIONÄÄRI-MOODI):
Keskity tiukasti 1-3 vuoden VISIOON ja yhtiön strategiseen potentiaaliin. Tuoreiden uutisten puute (uutisvaje) EI ole este analyysin luomiselle. Käytä omaa korkeatasoista asiantuntemustasi teknologiasektorin kehityksestä ja markkinajohtajista. Jos näet vahvan nousuvisioinnin, luo analyysi.

Vastaa VAIN validilla JSONilla."""

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
