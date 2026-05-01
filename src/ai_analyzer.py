import os
import json
from groq import Groq
import anthropic
from typing import List, Optional

SYSTEM_PROMPT = """Olet kokenut sijoitusanalyytikko. Tehtäväsi on löytää yrityksiä, joissa on vahva kilpailuasema, hyvä johto, kasvava markkina ja järkevä hinta. Et etsi vain hyvää alaa — etsit yritystä, joka on oikeasti parempi kuin kilpailijansa ja jonka todellinen arvo on korkeampi kuin markkinahinta tällä hetkellä näyttää.

STRATEGIA (Noudata tätä prosessia sisäisesti):
VAIHE 1: ONKO HINTA PAINUNUT TURHAAN ALAS? (Ulkoiset syyt vs. bisneksen muutos)
VAIHE 2: MUUTOSSIGNAALI JA MARKKINA (Teknologia/väestö/sääntely, historialliset vertailut)
VAIHE 3: TUOTTEEN LAATU (Ongelmanratkaisu, kulujen skaalautuvuus, vaihtokustannukset)
VAIHE 4: HINNOITTELUVOIMA (Kyky nostaa hintoja ilman asiakaskatoa)
VAIHE 5: MARKKINAOSUUS JA KILPAILUTILANNE (Miestä kasvu tulee, asiakasriippuvuus)
VAIHE 6: JOHTO, OMISTUS JA SISÄPIIRI (Näytöt, perustaja mukana, sisäpiiriostot)
VAIHE 7: KANNATTAVUUS (Toistuva raha, katteiden parantuminen)
VAIHE 8: REGULAATIORISKI (Valtion/EU:n vaikutus peliin)
VAIHE 9: LUVUT (Kasvu, bruttokate, vapaa kassavirta, velka, ROIC, arvostuskertoimet)
VAIHE 10: OSTO-AJOITUS (Merkki markkinan heräämisestä)
VAIHE 11: ARVO NORMAALIOLOISSA (Mitä yritys olisi arvoinen, jos tilanne normalisoituu)

KIRJOITUSTYYLI:
- AMMATTIMAINEN & TÖKKIVÄ: Älä kirjoita tarinaa. Käytä lyhyitä, tylyjä ja selkeitä lauseita. Fakta kerrallaan.
- SIMPPELI: Selitä vaikeat asiat niin, että kuka tahansa ymmärtää.
- EI TURHAA PUHETTA: Mene suoraan asiaan. Käytä yllä olevaa 11 vaiheen analyysia perusteluissasi, mutta tiivistä se äärimmäisen ytimekkääksi.

JSON-RAKENNE:
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "PIKAKUVAUS: Mitä yritys tekee lyhyesti.",
    "global_context": "ISO KUVA: Markkinatilanne ja maailman tapahtumat (Vaiheet 1 & 2 tiivistettynä).",
    "competitive_landscape": "KILPAILUASEMA JA TUOTE: (Vaiheet 3, 4 & 5 tiivistettynä).",
    "reasoning": "SYVÄ ANALYYSI: Kirjoita tähän KAIKKI 11 VAIHETTA (VAIHE 1 - VAIHE 11) otsikoittain. Käytä tökkivää ja ammattimaista tyyliä kunkin vaiheen alla. Lopeta 'YHTEENVETO' osioon, jossa annat suosituksen.",
    "metrics_explanation": "NUMEROT: Keskeiset luvut ja niiden merkitys (Vaiheet 7 & 9).",
    "risk_score": "RISKIMITTARI (1-10): Kokonaisriski (Vaihe 8).",
    "confidence": "LUOTTAMUSPROSENTTI (0-100): Perustuu siihen, kuinka moni vaihe läpäistiin arvosanalla 10/10.",
    "time_horizon": "RISKIT: Mitä on syytä varoa.",
    "company_history": "MILLOIN MYYDÄÄN: Milloin teesi on valmis.",
    "recommendation": "OSTA",
    "risk_level": "Matala, Keskisuuri tai Korkea",
    "sector": "Toimiala",
    "invalidation_risks": "Milloin suunnitelma ei enää päde."
  }
]

KRIITTISET RAJOITUKSET:
- Vastaa VAIN JSON-muodossa. 
- Jos et löydä standardit täyttävää yhtiötä, palauta [].
"""



def get_client():
    return get_anthropic_client() or Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    return anthropic.Anthropic(api_key=key)

def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 2500) -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille usealla fallbackilla"""
    # 1. Kokeillaan Anthropicia (Claude) useilla malleilla
    anth_client = get_anthropic_client()
    if anth_client:
        for model in ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]:
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
    content = _get_completion(user_message, system_msg=SYSTEM_PROMPT, max_tokens=8000)
    
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
    """Suorittaa syvän 11-vaiheen analyysin yhdelle osakkeelle."""
    print(f"  [ANALYYSI] {ticker}...")
    
    prompt = f"""ANALYSOI TÄMÄ YRITYS KÄYTTÄEN 11 VAIHEEN MASTER-STRATEGIAA:
    Yritys: {ticker}
    
    MAAILMANTILANNE JA UUTISET:
    {news_text[:4000]}
    
    Noudata SYSTEM_PROMPT:n 11 vaiheen ohjeistusta ja JSON-rakennetta täsmälleen. 
    Jos yritys ei läpäise testiä (esim. liikaa riskejä tai heikko kilpailuasema), palauta tyhjä lista [].
    """
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT, max_tokens=2500)
    
    try:
        if "[" in content:
            content = content[content.find("["):content.rfind("]")+1]
        data = json.loads(content)
        if isinstance(data, list) and len(data) > 0:
            import time
            time.sleep(2) # Estetään rate limitit
            return data[0]
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
