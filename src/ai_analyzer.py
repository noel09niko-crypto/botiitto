import os
import json
from groq import Groq
import anthropic
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

def _get_masked_key(key_name: str) -> str:
    val = os.environ.get(key_name, "")
    if not val: return "PUUTTUU"
    if val == "placeholder": return "VIRHE: placeholder"
    if len(val) < 10: return "LIIAN LYHYT"
    return f"{val[:6]}...{val[-4:]}"


SYSTEM_PROMPT = """Olet kokenut sijoitusanalyytikko. Käytät TRATEGO-analyysijärjestelmää (12 vaihetta, Max 19 pistettä).

TRATEGO-VAIHEET (Pisteytys 0-1 tai 0-2 per vaihe, yhteensä max 19p):
V1: Ostopaikka ja houkuttelevuus (0-1p)
V2: Muutossignaali ja markkina (0-2p)
V3: Tuotteen laatu ja skaalautuvuus (0-2p)
V4: Hinnoitteluvoima (0-2p)
V5: Markkinaosuus ja kilpailutilanne (0-1p)
V6: Johto ja omistus (0-2p)
V7: Kannattavuus ja kassavirta (0-2p)
V8: Regulaatioriski (0-1p)
V9: Avainluvut (0-1p)
V10: Ajoitus ja katalyytti (0-1p)
V11: Hinta vs. Arvo (GARP) (0-2p)
V12: Sisäpiiri ja instituutiot (0-1p)

KIRJOITUSTYYLI:
- AMMATTIMAINEN & TÖKKIVÄ: Lyhyitä, tylyjä ja selkeitä lauseita. Fakta kerrallaan.
- YTIMEKÄS: Pidä jokainen vaihe tiiviinä (max 3-5 lausetta per vaihe).
- SIMPPELI: Selitä vaikeat asiat helposti.

JSON-RAKENNE:
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "PIKAKUVAUS: Mitä yritys tekee lyhyesti.",
    "global_context": "ISO KUVA: Markkinatilanne ja maailman tapahtumat (V1 & V2).",
    "competitive_landscape": "KILPAILUASEMA JA TUOTE: (V3, V4 & V5).",
    "reasoning": "TRATEGO-ANALYYSI: Kirjoita tähän KAIKKI 12 VAIHETTA (V1 - V12) otsikoittain. Käytä tökkivää tyyliä. Anna jokaisesta vaiheesta pisteet (esim. V1: 1/1p). Lopeta 'YHTEENVETO' osioon, jossa lasket kokonaispisteet (X/19p) ja annat suosituksen.",
    "metrics_explanation": "NUMEROT: Keskeiset luvut ja niiden merkitys (V7 & V9).",
    "recommendation": "OSTA / PIDÄ / MYY",
    "confidence": "Lopulliset TRATEGO-pisteet (esim. 14/19)",
    "timeframe": "Sijoitushorisontti (esim. 1-3 vuotta)",
    "risks": "Keskeisimmät riskit (V8)."
  }
]
"""



def get_client():
    return get_anthropic_client() or Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "placeholder":
        print(f"[VAROITUS] Anthropic-avain puuttuu tai on 'placeholder' ({_get_masked_key('ANTHROPIC_API_KEY')})")
        return None
    return anthropic.Anthropic(api_key=key)


def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 16000, model: str = "claude-sonnet-4-6") -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille tietyllä mallilla."""
    anth_client = get_anthropic_client()
    if anth_client:
        try:
            resp = anth_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_msg if system_msg else "",
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text
        except Exception as e:
            print(f"Claude ({model}) error: {e} | Käytössä avain: {_get_masked_key('ANTHROPIC_API_KEY')}")
            # Yritetään fallbackia jos ensisijainen malli epäonnistuu
            if model != "claude-sonnet-4-6":
                return _get_completion(prompt, system_msg, max_tokens, model="claude-sonnet-4-6")
    
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
        print(f"Groq error: {e} | Käytössä avain: {_get_masked_key('GROQ_API_KEY')}")
    
    return ""

def _fix_recommendation(scenario: dict) -> dict:
    """Korjaa ristiriitaisen recommendation/sävy-yhdistelmän.
    Jos summary/reasoning on selkeästi nouseva mutta recommendation on MYY, 
    muutetaan se TARKKAILE jotta kortti ei ole ristiriitainen."""
    rec = str(scenario.get("recommendation", "TARKKAILE")).upper().strip()
    # Normalisoi suomenkieliset variantit
    mapping = {
        "OSTA": "OSTA", "BUY": "OSTA", "STRONG BUY": "OSTA",
        "MYY": "MYY", "SELL": "MYY", "STRONG SELL": "MYY",
        "TARKKAILE": "TARKKAILE", "WATCH": "TARKKAILE", "HOLD": "TARKKAILE",
    }
    # Muunna TARKKAILE → OSTA (ei tarkkailu-vaihtoehtoa)
    if scenario["recommendation"] not in ("OSTA", "MYY"):
        scenario["recommendation"] = "OSTA"

    # Tunnista sävy tekstistä
    positive_words = ["nousee", "nousu", "osta", "hyötyy", "kasvu", "potentiaali", "aliarvostettu", "mahdollisuus"]
    negative_words = ["myy", "lasku", "riski", "yliarvostettu", "varoitus"]
    combined_text = (str(scenario.get("summary", "")) + " " + str(scenario.get("reasoning", ""))).lower()
    pos_score = sum(1 for w in positive_words if w in combined_text)
    neg_score = sum(1 for w in negative_words if w in combined_text)

    # Ristiriita: teksti nouseva mutta suositus MYY → vaihdetaan OSTA
    if scenario["recommendation"] == "MYY" and pos_score > neg_score + 1:
        print(f"  [KORJAUS] Ristiriitainen MYY vaikka teksti nouseva → OSTA")
        scenario["recommendation"] = "OSTA"
    return scenario

def generate_scenarios(news_text: str, movers_text: str, client=None, watchlist_hint: str = "") -> List[dict]:
    """Pyytää tekoälyä arvioimaan koko seurantalistan ja poimimaan parhaat pitkän aikavälin keissit."""
    
    user_message = f"""TEHTÄVÄ:
    Käy läpi seurantalista, analyytikoiden suositukset (Consensus) ja uutiset. 
    
    POIMI ERITYISESTI:
    1. Osakkeet, joilla on vahva analyytikoiden suositus ("Strong Buy" tai "Buy") ja selkeä nousupotentiaali tavoitehintaan (Target).
    2. Yhtiöt, joilla on vahva sijoitusperustelu perustuen maailman muuttumiseen (geopolitiikka, sota, politiikka) tai markkinoiden pelkoon.
    
    Valitse vain ne, jotka ovat "Eliitti-tasoa" ja kestävät kovaa kritiikkiä.

    SEURANTALISTA (Käy nämä läpi):
    {watchlist_hint}

    MARKKINADATA (LUVUT):
    {movers_text}

    TUOREET UUTISET:
    {news_text[:4000]}

    VALINTAKRITEERI:
    Valitse vain ne seurantalistan osakkeet, jotka ovat "Eliitti-tasoa" ja täyttävät tiukat ammattimaiset kriteerit.
    """
    content = _get_completion(user_message, system_msg=SYSTEM_PROMPT, max_tokens=16000)
    
    try:
        # Poista mahdolliset markdown-koodilaatikot
        if "```" in content:
            content = content.split("```json")[-1].split("```")[0] if "```json" in content else content.split("```")[1].split("```")[0]
        
        # Etsi JSON-taulukko oikein — ÄLÄ leikkaa [ ] pois
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            content = content[start:end]
        elif "{" in content:
            # Fallback: yksi objekti ilman taulukkoa
            content = "[" + content[content.find("{"):content.rfind("}")+1] + "]"
        
        data = json.loads(content)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list): return [_fix_recommendation(s) for s in v]
            return [_fix_recommendation(data)]
        return [_fix_recommendation(s) for s in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Yritä pelastaa katkaistu JSON – ota ainakin ensimmäinen analyysi
        try:
            first_obj = content[content.find("{"):]
            depth = 0
            for i, c in enumerate(first_obj):
                if c == '{': depth += 1
                elif c == '}': depth -= 1
                if depth == 0:
                    single = json.loads(first_obj[:i+1])
                    return [_fix_recommendation(single)]
            return []
        except:
            return []
    except:
        return []

def filter_watchlist_with_sonnet(news_text: str, movers_text: str, watchlist: List[str]) -> List[str]:
    """Vaihe 1: Sonnet tekee TRATEGO-pisteytyksen (V1-V12, Max 19p) kaikille osakkeille."""
    print(f"  [TRATEGO SCORECARD] Pisteytetään {len(watchlist)} osaketta...")
    
    prompt = f"""TEHTÄVÄ: Pisteytä jokainen alla oleva osake TRATEGO-järjestelmän (V1-V12) mukaisesti.
    
    TRATEGO-PISTEYTYS (Max 19p):
    V1: Ostopaikka (0-1), V2: Muutossignaali (0-2), V3: Laatu (0-2), V4: Hinnoitteluvoima (0-2), 
    V5: Markkinaosuus (0-1), V6: Johto (0-2), V7: Kannattavuus (0-2), V8: Regulaatio (0-1), 
    V9: Luvut (0-1), V10: Katalyytti (0-1), V11: GARP (0-2), V12: Sisäpiiri/Instituutiot (0-1).
    
    VALINTAKRITEERI: 
    - Analyysi käynnistyy: >= 11/19p
    - Hylätään suoraan: < 6/19p
    - Harkinnanvarainen: 6-10/19p
    
    OSAKKEET:
    {", ".join(watchlist)}
    
    DATA:
    {news_text[:3000]}
    {movers_text[:1500]}
    
    VASTAA VAIN JSON-TAULUKKONA:
    [
      {{"ticker": "XYZ", "tratego_score": 14, "recommendation": "OSTA"}},
      ...
    ]
    """
    
    content = _get_completion(prompt, model="claude-sonnet-4-6", max_tokens=6000)
    try:
        if "[" in content:
            content = content[content.find("["):content.rfind("]")+1]
        data = json.loads(content)
        # Suodatetaan TRATEGO-kriteerin mukaan (>= 11p)
        selected_data = [item for item in data if item.get('tratego_score', 0) >= 11]
        # Järjestetään pisteiden mukaan
        sorted_data = sorted(selected_data, key=lambda x: x.get('tratego_score', 0), reverse=True)
        selected = [str(item['ticker']).upper().strip() for item in sorted_data[:15]]
        return selected
    except:
        print("  [TRATEGO ERROR] Pisteytys epäonnistui JSON-virheen takia.")
        return watchlist[:10]

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

def analyze_single_stock(ticker: str, news_text: str, client=None) -> Optional[dict]:
    """Suorittaa syvän TRATEGO 12-vaiheen analyysin yhdelle osakkeelle."""
    print(f"  [TRATEGO ANALYYSI] {ticker}...")
    
    prompt = f"""ANALYSOI TÄMÄ YRITYS KÄYTTÄEN TRATEGO 12-VAIHEEN MASTER-STRATEGIAA (Max 19p):
    Yritys: {ticker}
    
    MAAILMANTILANNE JA UUTISET:
    {news_text[:4000]}
    
    Noudata SYSTEM_PROMPT:n TRATEGO-ohjeistusta ja JSON-rakennetta täsmälleen. 
    Varmista, että käyt läpi jokaisen vaiheen (V1-V12) ja annat niistä pisteet.
    Laske lopulliset TRATEGO-pisteet (X/19) confidence-kenttään.
    """
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT, max_tokens=16000)
    
    try:
        # Puhdistetaan vastauksesta kaikki paitsi JSON
        start_idx_list = content.find("[")
        start_idx_obj = content.find("{")
        
        # Jos löytyy lista
        if start_idx_list != -1 and (start_idx_obj == -1 or start_idx_list < start_idx_obj):
            content_clean = content[start_idx_list:content.rfind("]")+1]
            data = json.loads(content_clean)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
        elif start_idx_obj != -1:
            content_clean = content[start_idx_obj:content.rfind("}")+1]
            data = json.loads(content_clean)
            return data
            
        return None
    except Exception as e:
        print(f"  [JSON ERROR] {ticker}: {e}")
        return None

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
    prompt = f"""ARVIOI ANALYYSIN JATKO (PITKÄN AIKAVÄLIN HODL-STRATEGIA):
    Analyysin kohde: {scenario.get('title')} ({scenario.get('recommendation')})
    
    Tämä investointi tehtiin seuraavalla alkuperäisellä perusteella:
    Miksi nousuvaraa: {scenario.get('reasoning')}
    Maailmantilanne: {scenario.get('global_context')}
    Aikahorisontti: {scenario.get('time_horizon')}
    
    KÄYTTÄJÄN TIUKKA EHTO: Sijoitushorisontti on PITKÄ (1-3 vuotta). 
    - Analyysit EIVÄT SAA vaihtua päivittäin tai viikoittain. 
    - Jos alkuperäinen "Iso kuva" (esim. tekoälyinfra, sota, geopolitiikka) on yhä voimassa, analyysi on VALID.
    - Jos on tullut uutta tietoa, joka muuttaa tilannetta hieman, valitse UPDATE (tämä päivittää perustelun, muttei poista osaketta).
    - Valitse INVALID vain ja ainoastaan, jos alkuperäinen peruste on romuttunut täysin ja osakkeen lasku on varmaa. Pieni hinnan heilahtelu EI ole syy poistolle.
    
    ASETA STATUS:
    - 'VALID': Alkuperäinen teesi on elossa. Uutishiljaisuus tai normaali hinnanvaihtelu on täysin OK.
    - 'UPDATE': Uutta tietoa on tullut. Perustelua pitää päivittää, mutta osake pysyy listalla.
    - 'INVALID': VAIN jos sijoituscase on kuollut ja fundamentit murtuneet.
    
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

def rewrite_scenario(scen: dict, client) -> Optional[dict]:
    """Uudelleenkirjoittaa olemassa olevan analyysin uuden promptin mukaisesti."""
    prompt = f"""UUDELLEENKIRJOITA TÄMÄ ANALYYSI. 
    Käytä uusimpia sääntöjä: ammattimainen mutta erittäin simppeli kieli (ELI5), ei vaikeita termejä, ei päivittäistä hintamelua.
    
    ALKUPERÄINEN ANALYYSI:
    Otsikko: {scen.get('title')}
    Ticker: {scen.get('tickers')}
    Yhteenveto: {scen.get('summary')}
    Kilpailutilanne: {scen.get('competitive_landscape')}
    Konteksti: {scen.get('global_context')}
    Perustelu: {scen.get('reasoning')}
    Numerot: {scen.get('metrics_explanation')}
    
    Palauta täsmälleen samassa JSON-muodossa kuin SYSTEM_PROMPT ohjeistaa.
    """
    
    try:
        resp = _get_completion(prompt, system_msg=SYSTEM_PROMPT)
        if "```json" in resp:
            resp = resp.split("```json")[1].split("```")[0].strip()
        elif "```" in resp:
            resp = resp.split("```")[1].split("```")[0].strip()
            
        data = json.loads(resp)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"Error rewriting scenario: {e}")
        return None
