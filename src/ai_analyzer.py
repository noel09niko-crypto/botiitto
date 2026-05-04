import os
import json
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


SYSTEM_PROMPT = """Olet kokenut sijoitusanalyytikko. Käytät tästä eteenpäin AINOASTAAN seuraavaa 3-vaiheista sijoitusstrategiaa arvioidessasi yhtiöitä. Et käytä enää pisteitä, vaan etsit yhtiöitä, jotka aidosti sopivat tähän profiiliin.

STRATEGIAN YDIN (3 VAIHETTA):

Vaihe 1 — Arvostus
Arvostuksessa arvioidaan kuinka paljon sijoittaja maksaa suhteessa yhtiön tulevaisuuden näkymiin ja siihen missä kehitysvaiheessa yhtiö tällä hetkellä on. Tavoitteena ei ole välttämättä ostaa halpaa — yhtiöstä voi maksaa korkeammankin hinnan jos tulevaisuuden kasvunäkymät ovat riittävän vahvat. Olennaista on ettei yhtiö ole yliarvostettu suhteessa tilanteeseen kokonaisuutena. Arvostus on läpileikkaava teema johon palataan analyysin myöhemmissäkin vaiheissa.

Vaihe 2 — Miksi hinta on alempi kuin pitäisi
Etsi syy miksi yhtiö on tällä hetkellä aliarvostettu. Syy on yksi tai useampi seuraavista:
- Markkinapelko: jokin laaja ulkoinen tekijä (kriisi, sota, taantuma, regulaatio) on painanut kurssia alas vaikka liiketoiminta jatkuu normaalisti. Arvioi vaikuttaako ulkoinen paine oikeasti liiketoimintaan pitkällä aikavälillä — jos ei, hinta on perusteettomasti alhaalla.
- Hinnoittelematon muutos: jokin tuleva tai käynnissä oleva tekijä parantaa yhtiön asemaa mutta markkina ei ole reagoinut täysimääräisesti. Uusi tuote, toimialan murros, hyödyttävä regulaatio, kilpailijan heikkeneminen tai muu rakenteellinen muutos joka näkyy tuloksessa vasta myöhemmin.
- Näkymättömyys: yhtiöllä ei ole analyytikkoseurantaa, mediahuomiota tai institutionaalisia sijoittajia. Liiketoiminta on kunnossa mutta markkina ei ole löytänyt sitä vielä (erityisen yleistä pienissä ja keskisuurissa yhtiöissä).

Vaihe 3 — Tuote ja Kilpailuetu
Botti arvioi onko tuote oikeasti poikkeuksellinen vai ainoastaan hyvä. Ero on merkittävä — hyvä tuote kilpailluilla markkinoilla tuottaa kohtuullisen bisneksen, poikkeuksellinen tuote uudessa markkinassa voi tuottaa kymmenkertaisen kasvun.
- Markkina ensin: Onko markkina vasta syntymässä, nopeasti kasvava vai jo kypsä. Paras tilanne on varhainen tai nopeasti kasvava markkina jossa yhtiö kasvaa markkinan mukana ilman kovaa taistelua osuuksista. Onko yhtiö muutoksen tekijä vai uhri? Murroksen tekijällä on ajan henki puolellaan.
- Tuotteen laatu: Onko tuote selvästi parempi kuin vaihtoehdot vai ainoastaan marginaalisesti erilainen? Onko se välttämätön vai mukavuus? Onko yhtiöllä hinnoitteluvoimaa?
- Adoptiovauhti ja asiakaskäyttäytyminen: Leviääkö tuote orgaanisesti? Tuleeko kasvu uusilta asiakkailta ja lisäostoista? Jos NRR (Net Revenue Retention) on yli 110%, tuote on oikeasti arvokas.
- Este kopioinnille (Kilpailuetu): Etsi vähintään yksi asia jota on vaikea kopioida — verkostovaikutus, switching cost, brändi, patentit, data joka paranee käytön myötä, tai vuosien kehitystyö jota ei pysty ostamaan rahalla lyhyessä ajassa.

KIRJOITUSTYYLI:
- AMMATTIMAINEN & TÖKKIVÄ: Lyhyitä, tylyjä ja selkeitä lauseita. Fakta kerrallaan.
- ELI5: Selitä monimutkaiset asiat yksinkertaisesti.
- DATA-LÄHTÖINEN: Jos data vahvistaa kilpailuedun tai aliarvostuksen, mainitse se.

JSON-RAKENNE (VASTAA VAIN TÄLLÄ):
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "PIKAKUVAUS: Mitä yritys tekee.",
    "global_context": "VAIHE 1: Arvostuksen perusteet.",
    "competitive_landscape": "VAIHE 3: Tuote, markkina ja kilpailuetu.",
    "reasoning": "VAIHE 2 & YHTEENVETO: Miksi hinta on nyt alempi kuin pitäisi (Markkinapelko, Hinnoittelematon muutos, tai Näkymättömyys) ja miksi tämä on ostopaikka.",
    "metrics_explanation": "NUMEROT: Keskeiset luvut (FCF, marginaalit) jotka tukevat strategiaa.",
    "recommendation": "AINA 'OSTA' TAI 'TARKKAILE'",
    "confidence": "Yhteensopivuus strategiaan prosenteissa (esim. '100' tai '90')",
    "timeframe": "1-3 vuotta",
    "risks": "Keskeisimmät riskit (esim. arvostus tai kopioitavuus)."
  }
]
TÄRKEÄÄ: Älä koskaan suosittele 'MYY'. Jos osake ei aidosti sovi tähän 3-vaiheiseen strategiaan, jätä se pois tuloksista.
"""



def get_client():
    return get_anthropic_client()

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "placeholder":
        print(f"[VAROITUS] Anthropic-avain puuttuu tai on 'placeholder' ({_get_masked_key('ANTHROPIC_API_KEY')})")
        return None
    return anthropic.Anthropic(api_key=key)


def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 8192, model: str = "claude-sonnet-4-6") -> str:
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
    print(f"  [STRATEGIASUODATIN] Analysoidaan {len(research_data)} osaketta uuden laadullisen strategian läpi...")
    
    # Tiivistetään data jotta se mahtuu promptiin
    data_summary = ""
    for d in research_data:
        ticker = d.get('ticker')
        cons = d.get('consensus', {})
        fins = d.get('financials', {})
        insider = "Kyllä" if d.get('insider') else "Ei tietoa"
        data_summary += f"- {ticker}: Price ${cons.get('current_price')}, Target ${cons.get('target_mean')}, FCF ${fins.get('free_cash_flow')}, Insider: {insider}\n"

    prompt = f"""TEHTÄVÄ: Käy läpi nämä osakkeet tiukan 3-vaiheisen sijoitusstrategiamme läpi:
    1. Arvostus (Kasvunäkymät vs. hinta)
    2. Aliarvostuksen syy (Markkinapelko, Hinnoittelematon muutos, Näkymättömyys)
    3. Tuote & Kilpailuetu (Markkinaosuus, Kopioinnin esteet, NRR)
    
    TUTKIMUSDATA:
    {data_summary}
    
    UUTISET:
    {news_text[:2000]}
    
    Poimi listalta KORKEINTAAN 5-7 osaketta, jotka SOPIVAT TÄYDELLISESTI TÄHÄN STRATEGIAAN. Älä anna pisteitä. Valitse vain helmet.
    
    VASTAA VAIN JSON-TAULUKKONA (pelkät osaketunnukset, jotka valitsit):
    [
      {{"ticker": "XYZ", "reason": "Lyhyt lause miksi tämä sopii strategiaan täydellisesti"}},
      ...
    ]
    """
    
    content = _get_completion(prompt, system_msg="Olet ammattimainen Research Agent.", max_tokens=4000)
    try:
        if "[" in content:
            content = content[content.find("["):content.rfind("]")+1]
        data = json.loads(content)
        selected = [str(item['ticker']).upper().strip() for item in data if 'ticker' in item]
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
    """Suorittaa syvän 3-vaiheisen analyysin käyttäen kerättyä tutkimusdataa."""
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
    
    prompt = f"""ANALYSOI TÄMÄ YRITYS KÄYTTÄEN UUTTA 3-VAIHEISTA STRATEGIAA:
    Yritys: {ticker}
    
    TUTKIMUSDATA:
    {research_context}
    
    UUTISET:
    {news_text[:3000]}
    
    Noudata SYSTEM_PROMPT:n ohjeita täsmälleen. Perustele Vaihe 1, Vaihe 2 ja Vaihe 3 datalla.
    """
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT)
    
    try:
        # Puhdistetaan vastauksesta kaikki paitsi JSON
        start_idx = content.find("[")
        if start_idx == -1: start_idx = content.find("{")
        end_idx = content.rfind("]") if content.rfind("]") != -1 else content.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            content_clean = content[start_idx:end_idx+1]
            data = json.loads(content_clean)
            res = data[0] if isinstance(data, list) else data
            return _fix_recommendation(res)
        return None
    except Exception as e:
        print(f"  [JSON ERROR] {ticker}: {e}")
        return None

def verify_analysis_quality(ticker: str, analysis: dict, research_bundle: dict) -> bool:
    print(f"  [QUALITY GUARD] Tarkistetaan {ticker}...")
    
    prompt = f"""Olet laadunvalvoja. Tarkista onko tämä analyysi FAKTAPOHJAINEN ja noudattaako se uutta 3-vaiheista strategiaa.
    
    ANALYYSIN TIIVISTELMÄ:
    Suositus: {analysis.get('recommendation')}
    Perustelu (ote): {analysis.get('reasoning')[:500]}
    Kilpailuetu (ote): {analysis.get('competitive_landscape')[:500]}
    
    TODELLISET FAKTAT (Tutkimusdata):
    {json.dumps(research_bundle, ensure_ascii=False)[:2000]}
    
    TARKISTUSLISTA:
    1. Onko analyysissa tunnistettu aito syy aliarvostukselle (Vaihe 2)?
    2. Onko kilpailuetu oikeasti vahva ja olemassa (Vaihe 3)?
    3. Onko analyysi ristiriidassa kylmän datan kanssa?
    
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
        return True

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
