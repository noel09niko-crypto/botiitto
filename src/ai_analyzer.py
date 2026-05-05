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


SYSTEM_PROMPT = """Olet kokenut sijoitusanalyytikko. Käytät AINOASTAAN seuraavaa 5-vaiheista sijoitusstrategiaa. Et käytä pisteitä. Etsit yhtiöitä jotka sopivat tähän profiiliin. Jos jokin vaihe on heikompi, muut vahvat vaiheet voivat kompensoida.

STRATEGIA (SANASTA SANAAN):

Vaihe 1 — Arvostus
Arvostuksessa arvioidaan kuinka paljon sijoittaja maksaa suhteessa yhtiön tulevaisuuden näkymiin ja siihen missä kehitysvaiheessa yhtiö tällä hetkellä on. Tavoitteena ei ole välttämättä ostaa halpaa — yhtiöstä voi maksaa korkeammankin hinnan jos tulevaisuuden kasvunäkymät ovat riittävän vahvat. Olennaista on ettei yhtiö ole yliarvostettu suhteessa tilanteeseen kokonaisuutena. Arvostus on läpileikkaava teema johon palataan analyysin myöhemmissäkin vaiheissa.

Vaihe 2 — Miksi hinta on alempi kuin pitäisi
Etsi syy miksi yhtiö on tällä hetkellä aliarvostettu. Syy on yksi tai useampi seuraavista.
Markkinapelko — jokin laaja ulkoinen tekijä kuten kriisi, sota, taantuma tai regulaatioepävarmuus on painanut kurssia alas vaikka liiketoiminta jatkuu normaalisti. Pelko voi kestää pitkään. Arvioi vaikuttaako ulkoinen paine oikeasti liiketoimintaan pitkällä aikavälillä — jos ei, hinta on perusteettomasti alhaalla.
Hinnoittelematon muutos — jokin tuleva tai käynnissä oleva tekijä parantaa yhtiön asemaa mutta markkina ei ole reagoinut täysimääräisesti. Uusi tuote, toimialan murros, hyödyttävä regulaatio, kilpailijan heikkeneminen tai muu rakenteellinen muutos joka näkyy tuloksessa vasta myöhemmin.
Näkymättömyys — yhtiöllä ei ole analyytikkoseurantaa, mediahuomiota tai institutionaalisia sijoittajia. Liiketoiminta on kunnossa mutta markkina ei ole löytänyt sitä vielä. Erityisen yleistä pienissä ja keskisuurissa yhtiöissä.

Kilpailuetu
Etsi yhtiöltä vähintään yksi asia jota on vaikea kopioida — verkostovaikutus, switching cost, brändi, patentit, data joka paranee käytön myötä, tai vuosien kehitystyö jota ei pysty ostamaan rahalla. Yhden vahvan kilpailuedun riittää. Useampi päällekkäin on bonus mutta ei vaatimus.
Kilpailuedun ei tarvitse olla ikuinen — riittää että se antaa yhtiölle tarpeeksi aikaa kasvaa ja vahvistaa asemaansa ennen kuin kilpailu kiristyy. Varhaisen vaiheen yhtiöllä kilpailuetu voi olla vasta rakentumassa — arvioi onko sille selkeä polku eikä vaadita että se on jo täysin muodostunut.

Vaihe 3 — Tuote
Botti arvioi onko tuote oikeasti poikkeuksellinen vai ainoastaan hyvä.
Markkina ensin — onko markkina vasta syntymässä, nopeasti kasvava vai jo kypsä. Paras tilanne on varhainen tai nopeasti kasvava markkina jossa yhtiö kasvaa markkinan mukana ilman kovaa taistelua osuuksista. Vielä parempi jos yhtiö itse määrittelee sen markkinan.
Onko yhtiö muutoksen tekijä vai uhri — aiheuttaja rakentaa uutta tapaa tehdä jotain halvemmin, nopeammin tai kokonaan uudella tavalla. Uhri puolustaa vanhaa mallia.
Tuotteen laatu — onko tuote selvästi parempi kuin vaihtoehdot. Onko tuote välttämätön vai mukavuus. Onko hinnoitteluvoima olemassa.
Adoptiovauhti ja asiakaskäyttäytyminen — leviääkö tuote orgaanisesti. NRR yli 110% on vahvin merkki. Varhaisessa vaiheessa arvioi onko polku marginaalien paranemiseen.
Este kopioinnille — omaa teknologiaa, dataa, patenttisuojaa tai vuosien kehitystyötä.

Vaihe 4 — Velka ja kassavirta
Velka ei ole automaattisesti paha. Vertaa toimialan normaaliin. Kehitysvaiheessa oleva yhtiö voi polttaa käteistä — normaalia jos raha menee kasvuun.
Velan syy ratkaisee. Kasvuinvestointi ok. Operatiivisten tappioiden paikkailu ei.
Kassavirta — varhaisessa vaiheessa kysymys on onko selkeä polku positiiviseen. Kypsällä yhtiöllä vapaan kassavirran pitää olla vahva ja kasvava.
Kassa ja likviditeetti — kehitysvaiheessa vähintään 18-24kk runway. Alle vuoden = lisärahoitusriski.
Tase — piilevä arvo on plussaa. Toistuvat osakeannit varoitusmerkki.

Vaihe 5 — Johto
Tausta ja kokemus — onko johdolla näyttöä. Perustajajohtaja vahva merkki mutta ei vaatimus.
Omistus ja sitoutuminen — omistaako johto yhtiötä. Insider-ostot vahvin signaali. Systemaattinen myyminen varoitusmerkki.
Rehellisyys — puhuuko johto avoimesti myös epäonnistumisista.
Ilmapiiri ja kulttuuri — korkea vaihtuvuus johtotasolla varoitusmerkki.
Omien osakkeiden osto — kypsällä yhtiöllä takaisinostot alhaisella hinnalla vahvistavat keissiä.

AIKAJÄNNE:
Strategia on rakennettu vähintään kolmen vuoden aikajänteelle. Ei arvailla lyhyen aikavälin liikkeitä. Kaiken analyysin pitää perustua nähtävissä oleviin asioihin — ei arvauksiin. Pieni tilapäinen vastoinkäyminen ei ole este jos liiketoiminta on kunnossa pitkällä tähtäimellä.

TIEDONHAKU:
Jos uutisia ei ole saatavilla jostain yhtiöstä, se EI ole syy hylätä osaketta. Hae tietoa muista lähteistä: taloudelliset tiedot, tase, kassavirta, tuotteet, yrityksen kuvaus, analyytikkoraportit. Hylkää vasta kun sinulla on oikeasti dataa joka estää oston.

KIRJOITUSTYYLI:
- AMMATTIMAINEN & TÖKKIVÄ: Lyhyitä, selkeitä lauseita.
- DATA-LÄHTÖINEN: Perustele kovat väitteet luvuilla tai tiedolla.
- Jokaisessa vaiheen perustelussa PITÄÄ näkyä kaikki kyseisen vaiheen kysymykset ja niiden vastaukset.

JSON-RAKENNE (VASTAA VAIN TÄLLÄ):
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "PIKAKUVAUS: Mitä yritys tekee ja miksi se on salkussa.",
    "global_context": "VAIHE 1: Arvostus. Analysoi hinta suhteessa tulevaisuuteen ja kehitysvaiheeseen.",
    "reasoning": "VAIHE 2: Aliarvostuksen syy. Markkinapelko / Hinnoittelematon muutos / Näkymättömyys. Kilpailuetu.",
    "competitive_landscape": "VAIHE 3: Tuote. Markkina, muutoksen tekijä/uhri, tuotteen laatu, adoptiovauhti, este kopioinnille.",
    "metrics_explanation": "VAIHE 4: Velka ja kassavirta. Runway, kassavirran polku, tase, varoitusmerkit.",
    "company_history": "VAIHE 5: Johto. Tausta, omistus, rehellisyys, kulttuuri.",
    "recommendation": "OSTA tai TARKKAILE",
    "confidence": "Yhteensopivuus strategiaan prosenteissa (esim. 85)",
    "timeframe": "3-5 vuotta",
    "risks": "Keskeisimmät rakenteelliset riskit (ei kvartaalitason)."
  }
]
TÄRKEÄÄ: Jos osake ei ole todellinen ostopaikka, jätä se pois. Etsi VAIN nousevia osakkeita.
"""



def get_client():
    return get_anthropic_client()

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "placeholder":
        print(f"[VAROITUS] Anthropic-avain puuttuu tai on 'placeholder' ({_get_masked_key('ANTHROPIC_API_KEY')})")
        return None
    return anthropic.Anthropic(api_key=key)


def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 8192, model: str = "claude-sonnet-4-20250514") -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille."""
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
    """Varmistaa että suositus on aina OSTA tai TARKKAILE."""
    rec = str(scenario.get("recommendation", "OSTA")).upper()
    if "OSTA" in rec:
        scenario["recommendation"] = "OSTA"
    else:
        scenario["recommendation"] = "TARKKAILE"
    return scenario

def generate_scenarios(news_text: str, movers_text: str, client=None, watchlist_hint: str = "", world_news_text: str = "") -> List[dict]:
    """Pyytää tekoälyä arvioimaan koko seurantalistan ja poimimaan parhaat pitkän aikavälin keissit."""
    
    user_message = f"""TEHTÄVÄ:
    Käy läpi seurantalista ja kaikki saatavilla oleva tieto. Etsi VAIN nousevia osakkeita joissa on aito ostopaikka 3+ vuoden aikajänteellä.
    
    MAAILMANTAPAHTUMAT (käytä tätä ymmärtääksesi markkinoiden tilannetta ja pelkoja):
    {world_news_text[:3000]}
    
    SEURANTALISTA:
    {watchlist_hint}

    MARKKINADATA:
    {movers_text}

    YRITYSUUTISET:
    {news_text[:4000]}

    MUISTA: Älä hylkää osaketta vain koska uutisia ei ole. Etsi aliarvostuksen syy strategian mukaan. Mieti miten maailmantapahtumat vaikuttavat eri sektoreihin ja yhtiöihin.
    """
    content = _get_completion(user_message, system_msg=SYSTEM_PROMPT, max_tokens=8192)
    
    try:
        if "```" in content:
            content = content.split("```json")[-1].split("```")[0] if "```json" in content else content.split("```")[1].split("```")[0]
        
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            content = content[start:end]
        elif "{" in content:
            content = "[" + content[content.find("{"):content.rfind("}")+1] + "]"
        
        data = json.loads(content)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list): return [_fix_recommendation(s) for s in v]
            return [_fix_recommendation(data)]
        return [_fix_recommendation(s) for s in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
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

def filter_watchlist_with_sonnet(research_bundles: List[dict], news_text: str, movers_text: str = "", world_news_text: str = "") -> List[str]:
    print(f"  [STRATEGIASUODATIN] Analysoidaan {len(research_bundles)} osaketta 5-vaiheisen strategian läpi...")
    
    data_summary = ""
    for d in research_bundles:
        ticker = d.get('ticker')
        cons = d.get('consensus', {})
        fins = d.get('financials', {})
        biz = d.get('business_summary', '')[:150]
        insider = "Kyllä" if d.get('insider') else "Ei tietoa"
        news_titles = ", ".join([n.get('title') or '' for n in d.get('news', [])[:3]])
        data_summary += f"- {ticker}: Price ${cons.get('current_price')}, Target ${cons.get('target_mean')}, Rec: {cons.get('recommendation')}, FCF ${fins.get('free_cash_flow')}, D/E: {fins.get('debt_to_equity')}, Insider: {insider}, Kuvaus: {biz}, Uutiset: {news_titles}\n"

    prompt = f"""TEHTÄVÄ: Käy läpi nämä osakkeet 5-vaiheisen strategian läpi. Etsi VAIN nousevia osakkeita — aliarvostettuja tai sellaisia joissa on hinnoittelematon muutos tai katalyytti jonka markkina ei ole vielä huomioinut.

    ÄLÄ katso vain lukuja. Mieti MIKSI hinta on alhaalla (strategian Vaihe 2). Onko markkinapelkoa, hinnoittelematonta muutosta tai näkymättömyyttä?

    MAAILMANTAPAHTUMAT (konteksti):
    {world_news_text[:2000]}
    
    TUTKIMUSDATA:
    {data_summary}
    
    YRITYSUUTISET:
    {news_text[:2000]}

    MARKKINALIIKKEET:
    {movers_text[:1000]}
    
    Poimi KORKEINTAAN 7 osaketta jotka sopivat strategiaan. Jos uutisia ei ole, se EI ole syy hylätä — arvioi talouslukujen, tuotteiden ja yrityksen kuvauksen perusteella.
    
    VASTAA VAIN JSON:
    [
      {{"ticker": "XYZ", "reason": "Lyhyt syy miksi sopii strategiaan"}}
    ]
    """
    
    content = _get_completion(prompt, system_msg="Olet ammattimainen Research Agent. Etsi VAIN nousevia osakkeita.", max_tokens=4000)
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

def analyze_single_stock(ticker: str, research_bundle: dict, news_text: str, world_news_text: str = "") -> Optional[dict]:
    """Suorittaa syvän 5-vaiheisen analyysin. Jokainen vaihe ja sen kaikki kysymykset käydään läpi."""
    print(f"  [SYVÄANALYYSI] {ticker}...")
    
    fins = research_bundle.get('financials', {})
    cons = research_bundle.get('consensus', {})
    insider = research_bundle.get('insider', [])
    biz_summary = research_bundle.get('business_summary', "Ei kuvausta.")
    news_list = research_bundle.get('news', [])
    news_titles = "\n".join([f"  - {n.get('title', '')}" for n in news_list])
    
    research_context = f"""
    YRITYKSEN KUVAUS: {biz_summary}
    TUNNUSLUVUT: FCF: {fins.get('free_cash_flow')}, P/E (Fwd): {fins.get('forward_pe')}, P/E (Trail): {fins.get('trailing_pe')}, Debt/Equity: {fins.get('debt_to_equity')}, Op.Margins: {fins.get('operating_margins')}, Rev.Growth: {fins.get('revenue_growth')}, ROE: {fins.get('return_on_equity')}, EBITDA: {fins.get('ebitda')}
    ANALYYTIKOT: Tavoitehinta: ${cons.get('target_mean')} (Nykyhinta: ${cons.get('current_price')}), Suositus: {cons.get('recommendation')}, Analyytikkoja: {cons.get('number_of_analysts')}
    SISÄPIIRI (Viimeisimmät): {json.dumps(insider, ensure_ascii=False)[:500]}
    YRITYKSEN OMAT UUTISET:
    {news_titles}
    """
    
    prompt = f"""ANALYSOI {ticker} KÄYTTÄEN KAIKKIA 5 VAIHETTA. 

Jokaisessa vaiheessa KÄYT LÄPI KAIKKI sen sisällä olevat kysymykset ja kohdat. Perustelussa PITÄÄ NÄKYÄ vastaus jokaiseen kohtaan.

TUTKIMUSDATA:
{research_context}

MAAILMANTAPAHTUMAT (miten nämä vaikuttavat tähän yhtiöön?):
{world_news_text[:2000]}

YRITYSUUTISET:
{news_text[:2000]}

MUISTA:
- Etsi NOUSEVIA osakkeita, ei laskevia
- Jos tietoa puuttuu, käytä saatavilla olevaa dataa äläkä hylkää
- Mieti miten maailmantapahtumat vaikuttavat juuri tähän yhtiöön
- 3+ vuoden aikajänne
"""
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT)
    
    try:
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
    
    prompt = f"""Tarkista onko tämä analyysi FAKTAPOHJAINEN ja kattaako se kaikki 5 vaihetta kunnolla.

    ANALYYSI:
    Vaihe 1 (Arvostus): {analysis.get('global_context', '')[:400]}
    Vaihe 2 (Aliarvostus): {analysis.get('reasoning', '')[:400]}
    Vaihe 3 (Tuote): {analysis.get('competitive_landscape', '')[:400]}
    Vaihe 4 (Talous): {analysis.get('metrics_explanation', '')[:400]}
    Vaihe 5 (Johto): {analysis.get('company_history', '')[:400]}
    
    FAKTAT:
    {json.dumps(research_bundle, ensure_ascii=False)[:2000]}
    
    TARKISTA:
    1. Perustuuko dataan eikä arvauksiin?
    2. Onko aliarvostuksen syy looginen?
    3. Onko 3+ vuoden aikajänne?
    4. Ristiriita datan kanssa?
    
    VASTAA JSON: {{"status": "PASS"/"FAIL", "reason": "Miksi?"}}"""
    
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

def validate_scenario(scenario: dict, latest_news: str, world_news_text: str = "", client=None) -> dict:
    """Tarkistaa vanhan skenaarion: PÄIVITÄ jos tietoa muuttunut, POISTA vasta kun ostopaikka on ohi."""
    prompt = f"""ARVIOI ANALYYSIN JATKO:
    Kohde: {scenario.get('title')} ({scenario.get('tickers')})
    
    Alkuperäinen perustelu:
    Arvostus: {scenario.get('global_context', '')[:300]}
    Aliarvostus: {scenario.get('reasoning', '')[:300]}
    Tuote: {scenario.get('competitive_landscape', '')[:300]}
    Talous: {scenario.get('metrics_explanation', '')[:300]}
    Johto: {scenario.get('company_history', '')[:300]}
    
    SÄÄNNÖT:
    - Analyysit EIVÄT vaihdu joka päivä. Pitkä horisontti (3+ vuotta).
    - POISTA (INVALID) vasta kun ostopaikka on ohi: osake ei enää nouse, et pysty enää perustelemaan ostoa.
    - PÄIVITÄ (UPDATE) jos uutta tietoa on tullut, perustelu vanhentunut, mutta osake on yhä hyvä osto. Anna päivitetty teksti.
    - PIDÄ (VALID) jos mikään ei ole muuttunut merkittävästi. Uutishiljaisuus = VALID.
    
    MAAILMANTAPAHTUMAT:
    {world_news_text[:1500]}
    
    YRITYSUUTISET:
    {latest_news[:1500]}
    
    VASTAA JSON:
    Jos VALID: {{"status": "VALID", "reason": "Lyhyt perustelu"}}
    Jos UPDATE: {{"status": "UPDATE", "reason": "Mikä muuttui", "updated_reasoning": "Uusi Vaihe 2 teksti", "updated_global_context": "Uusi Vaihe 1 teksti", "updated_metrics": "Uusi Vaihe 4 teksti"}}
    Jos INVALID: {{"status": "INVALID", "reason": "Miksi ostopaikka on ohi"}}"""
    content = _get_completion(prompt, max_tokens=1500)
    try:
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        return json.loads(content)
    except:
        return {"status": "VALID", "reason": "Tarkistus epäonnistui — pidetään voimassa."}

def rewrite_scenario(scen: dict, client) -> Optional[dict]:
    """Uudelleenkirjoittaa olemassa olevan analyysin."""
    prompt = f"""UUDELLEENKIRJOITA TÄMÄ ANALYYSI käyttäen 5-vaiheista strategiaa.
    
    ALKUPERÄINEN:
    Otsikko: {scen.get('title')}
    Ticker: {scen.get('tickers')}
    Yhteenveto: {scen.get('summary')}
    Kilpailutilanne: {scen.get('competitive_landscape')}
    Konteksti: {scen.get('global_context')}
    Perustelu: {scen.get('reasoning')}
    Numerot: {scen.get('metrics_explanation')}
    
    Palauta samassa JSON-muodossa kuin SYSTEM_PROMPT ohjeistaa.
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
    """Wrapper-funktio main.py:tä varten."""
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
        output += f"SUOSITUS: {r.get('recommendation', 'TARKKAILE')}\n"
        output += f"YHTEENVETO: {r.get('summary', '')}\n"
        output += f"PERUSTELU:\n{r.get('reasoning', '')}\n\n"
        
    return output
