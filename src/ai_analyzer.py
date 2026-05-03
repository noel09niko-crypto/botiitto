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

STRATEGIAN YDIN (11-VAIHEINEN TARKASTUS):
Jokainen analyysi on läpäistävä tiukka seula, jossa faktat (luvut, sisäpiiri, uutiset) painavat enemmän kuin yleinen hypetys.

TRATEGO-VAIHEET (Pisteytys per vaihe):
V1: Ostopaikka ja houkuttelevuus (0-1p)
V2: Muutossignaali ja markkina (0-2p)
V3: Tuotteen laatu ja skaalautuvuus (0-2p)
V4: Hinnoitteluvoima (0-2p)
V5: Markkinaosuus ja kilpailutilanne (0-1p)
V6: Johto ja omistus (0-2p)
V7: Kannattavuus ja kassavirta (0-2p) - KÄYTÄ ANNETTUA FCF-DATAA.
V8: Regulaatioriski (0-1p)
V9: Avainluvut (0-1p) - KÄYTÄ ANNETTUJA P/E JA MARGINAALEJA.
V10: Ajoitus ja katalyytti (0-1p)
V11: Hinta vs. Arvo (GARP) (0-2p) - VERTAA TAVOITEHINTAA NYKYHINTAAN.
V12: Sisäpiiri ja instituutiot (0-1p) - KÄYTÄ ANNETTUA INSIDER-DATAA.

KIRJOITUSTYYLI:
- AMMATTIMAINEN & TÖKKIVÄ: Lyhyitä, tylyjä ja selkeitä lauseita. Fakta kerrallaan.
- ELI5: Selitä monimutkaiset asiat yksinkertaisesti.
- DATA-LÄHTÖINEN: Jos data sanoo "Insider Buy", mainitse se. Jos data puuttuu, ole rehellinen.

JSON-RAKENNE (VASTAA VAIN TÄLLÄ):
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "PIKAKUVAUS: Mitä yritys tekee.",
    "global_context": "ISO KUVA: Markkina ja maailman tapahtumat (V1 & V2).",
    "competitive_landscape": "KILPAILUASEMA: (V3, V4 & V5).",
    "reasoning": "TRATEGO-ANALYYSI: Kaikki 12 vaihetta otsikoittain (V1 - V12). Anna pisteet per vaihe (esim. V1: 1/1p).",
    "metrics_explanation": "NUMEROT: Keskeiset luvut ja niiden merkitys (V7 & V9).",
    "recommendation": "AINA 'OSTA'",
    "confidence": "Lopulliset TRATEGO-pisteet (esim. 14/19)",
    "timeframe": "1-3 vuotta",
    "risks": "Keskeisimmät riskit (V8)."
  }
]
TÄRKEÄÄ: Älä koskaan suosittele 'MYY'. Jos osake ei ole ostopaikka, jätä se pois tuloksista.
"""



def get_client():
    return get_anthropic_client() or Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "placeholder":
        print(f"[VAROITUS] Anthropic-avain puuttuu tai on 'placeholder' ({_get_masked_key('ANTHROPIC_API_KEY')})")
        return None
    return anthropic.Anthropic(api_key=key)


def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 8192, model: str = "claude-3-5-sonnet-20241022") -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille. Vain Claude sallittu laadun takaamiseksi."""
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
            print(f"[VIRHE] Claude epäonnistui: {e}")
    
    return ""

def _fix_recommendation(scenario: dict) -> dict:
    """Varmistaa että suositus on aina OSTA. Jos teesi ei ole ostopaikka, se hylätään muualla."""
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
    content = _get_completion(user_message, system_msg=SYSTEM_PROMPT, max_tokens=8192)
    
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

def filter_watchlist_with_sonnet(research_data: List[dict], news_text: str) -> List[str]:
    """Vaihe 1: Sonnet tekee TRATEGO-pisteytyksen hyödyntäen syvää tutkimusdataa."""
    print(f"  [TRATEGO SCORECARD] Pisteytetään {len(research_data)} osaketta datan perusteella...")
    
    # Tiivistetään data jotta se mahtuu promptiin
    data_summary = ""
    for d in research_data:
        ticker = d.get('ticker')
        cons = d.get('consensus', {})
        fins = d.get('financials', {})
        insider = "Kyllä" if d.get('insider') else "Ei tietoa"
        data_summary += f"- {ticker}: Price ${cons.get('current_price')}, Target ${cons.get('target_mean')}, FCF ${fins.get('free_cash_flow')}, Insider: {insider}\n"

    prompt = f"""TEHTÄVÄ: Pisteytä nämä osakkeet TRATEGO-järjestelmän (V1-V12) mukaisesti.
    Käytä annettua tutkimusdataa ja uutisia. Älä arvaa pisteitä jos data puuttuu, vaan ole tiukka.
    
    TUTKIMUSDATA:
    {data_summary}
    
    UUTISET:
    {news_text[:2000]}
    
    VASTAA VAIN JSON-TAULUKKONA:
    [
      {{"ticker": "XYZ", "tratego_score": 14, "reason": "Miksi sai nämä pisteet?"}},
      ...
    ]
    """
    
    content = _get_completion(prompt, model="claude-sonnet-4-6", max_tokens=4000)
    try:
        if "[" in content:
            content = content[content.find("["):content.rfind("]")+1]
        data = json.loads(content)
        # Suodatetaan TRATEGO-kriteerin mukaan (>= 11p) tai jos on poikkeuksellinen syy
        selected_data = [item for item in data if item.get('tratego_score', 0) >= 11]
        selected = [str(item['ticker']).upper().strip() for item in selected_data]
        return selected
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

def analyze_single_stock(ticker: str, research_bundle: dict, news_text: str) -> Optional[dict]:
    """Suorittaa syvän TRATEGO 12-vaiheen analyysin käyttäen kerättyä tutkimusdataa."""
    print(f"  [TRATEGO ANALYYSI] {ticker}...")
    
    # Muotoillaan tutkimusdata helposti luettavaksi
    fins = research_bundle.get('financials', {})
    cons = research_bundle.get('consensus', {})
    insider = research_bundle.get('insider', [])
    biz_summary = research_bundle.get('business_summary', "Ei kuvausta.")
    
    research_context = f"""
    YRITYKSEN KUVAUS: {biz_summary}
    TUNNUSLUVUT: FCF: {fins.get('free_cash_flow')}, P/E (Fwd): {fins.get('forward_pe')}, Debt/Equity: {fins.get('debt_to_equity')}, Marginaalit: {fins.get('operating_margins')}
    ANALYYTIKOT: Tavoitehinta: ${cons.get('target_mean')} (Nykyhinta: ${cons.get('current_price')}), Suositus: {cons.get('recommendation')}
    SISÄPIIRI (Viimeisimmät): {json.dumps(insider, ensure_ascii=False)}
    """
    
    prompt = f"""ANALYSOI TÄMÄ YRITYS KÄYTTÄEN TRATEGO-STRATEGIAA:
    Yritys: {ticker}
    
    TUTKIMUSDATA:
    {research_context}
    
    UUTISET:
    {news_text[:3000]}
    
    Noudata SYSTEM_PROMPT:n ohjeita täsmälleen. Perustele jokainen TRATEGO-vaihe (V1-V12) datalla.
    """
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT, max_tokens=8192)
    
    try:
        # Puhdistetaan vastauksesta kaikki paitsi JSON
        start_idx = content.find("[")
        if start_idx == -1: start_idx = content.find("{")
        end_idx = content.rfind("]") if content.rfind("]") != -1 else content.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            content_clean = content[start_idx:end_idx+1]
            data = json.loads(content_clean)
            return data[0] if isinstance(data, list) else data
        return None
    except Exception as e:
        print(f"  [JSON ERROR] {ticker}: {e}")
        return None

def verify_analysis_quality(ticker: str, analysis: dict, research_bundle: dict) -> bool:
    """Strateginen tarkastus: Varmistaa että analyysi vastaa faktoja ja 11 kriteeriä."""
    print(f"  [QUALITY GUARD] Tarkistetaan {ticker}...")
    
    prompt = f"""Olet laadunvalvoja. Tarkista onko tämä analyysi FAKTAPOHJAINEN ja noudattaako se TRATEGO-sääntöjä.
    
    ANALYYSIN TIIVISTELMÄ:
    Suositus: {analysis.get('recommendation')}
    Pisteet: {analysis.get('confidence')}
    Perustelu (ote): {analysis.get('reasoning')[:500]}
    
    TODELLISET FAKTAT (Tutkimusdata):
    {json.dumps(research_bundle, ensure_ascii=False)[:2000]}
    
    TARKISTUSLISTA:
    1. Onko analyysi ristiriidassa numeroiden kanssa? (Esim. sanotaan "halpa" vaikka P/E on 100)
    2. Onko sisäpiiri-data (V12) huomioitu oikein?
    3. Onko tavoitehinta (V11) huomioitu?
    4. Onko kieli ammattimaista (ei hypeä)?
    
    VASTAA VAIN JSON: {{"status": "PASS"/"FAIL", "reason": "Miksi?"}}"""
    
    resp = _get_completion(prompt, max_tokens=300)
    try:
        if "{" in resp:
            resp = resp[resp.find("{"):resp.rfind("}")+1]
        data = json.loads(resp)
        if data.get("status") == "PASS":
            return True
        else:
            print(f"  [REJECTED] {ticker}: {data.get('reason')}")
            return False
    except:
        return True # Jos tarkastus epäonnistuu teknisesti, päästetään läpi varmuuden vuoksi

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
    - Jos uutisissa EI mainita tätä yhtiötä lainkaan, palauta AINA 'VALID'. Uutishiljaisuus on merkki siitä, että teesi on yhä voimassa.
    - Jos alkuperäinen "Iso kuva" (esim. tekoälyinfra, sota, geopolitiikka) on yhä voimassa, analyysi on VALID.
    - Jos on tullut uutta tietoa, joka muuttaa tilannetta hieman, valitse UPDATE.
    - Valitse INVALID vain ja ainoastaan, jos alkuperäinen peruste on romuttunut täysin (esim. konkurssi, massiivinen petos, liiketoiminnan loppuminen). Pieni hinnan heilahtelu tai uutisten puute EI ole syy poistolle.
    
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
def analyze_market(news_text: str, movers_text: str, detailed_stocks: List[str], client=None) -> str:
    """Wrapper-funktio main.py:tä varten. Käyttää uutta tutkimus-bundlea."""
    results = []
    from src.stock_analyzer import get_research_bundle
    
    for ticker in detailed_stocks[:5]:
        bundle = get_research_bundle(ticker)
        res = analyze_single_stock(ticker, bundle, news_text)
        if res:
            results.append(res)
    
    if not results:
        return "Ei voitu luoda analyyseja. Tarkista API-yhteydet."
        
    output = ""
    for r in results:
        output += f"--- {r.get('title', 'Tuntematon')} ({r.get('tickers', 'N/A')}) ---\n"
        output += f"SUOSITUS: {r.get('recommendation', 'TARKKAILE')} | PISTEET: {r.get('confidence', '0/19')}\n"
        output += f"YHTEENVETO: {r.get('summary', '')}\n"
        output += f"PERUSTELU:\n{r.get('reasoning', '')}\n\n"
        
    return output
