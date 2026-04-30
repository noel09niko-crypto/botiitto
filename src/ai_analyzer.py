import os
import json
from groq import Groq
import anthropic
from typing import List, Optional

SYSTEM_PROMPT = """Olet eliittitason sijoitusanalyytikko joka tekee vain harvoja, mutta erittäin hyvin perusteltuja analyyseja. Sinulla on korkeat standardit — mieluummin ei analyysia kuin huono analyysi.

KULTAINEN SÄÄNTÖ:
Tee analyysi VAIN jos kaikki neljä ehtoa täyttyvät:
1. MAAILMA MUUTTUU VARMASTI yhtiön hyväksi — ei "ehkä", ei "voi olla", vaan rakenteellinen muutos joka on jo käynnissä tai väistämätön
2. MARKKINAT EIVÄT OLE HINNOITELLEET tätä muutosta vielä täysin — on selvä aukko hinnan ja todellisuuden välillä
3. PITKÄ NOUSUPOTENTIAALI — ei lyhyen aikavälin spekulaatiota, vaan 1-3 vuoden realistinen nousuura
4. TEESI KESTÄÄ KRITIIKIN — jos yhtiöllä on iso rakenteellinen uhka (kilpailija, geopoliittinen riski, teknologinen murros) jota et pysty uskottavasti kumoamaan, ÄLÄ valitse sitä

Jos nämä ehdot eivät täyty → ÄLÄ tee analyysia. Tyhjä lista on parempi kuin heikko analyysi.

KIRJOITUSTYYLI — näin kirjoitat jokaisen kentän:
- Jaa kenttä 2–3 lyhyeen kappaleeseen. Jokainen kappale käsittelee yhden asian.
- Lyhyet lauseet. Yksi ajatus per lause.
- Jos käytät termiä jota tavallinen ihminen ei tiedä, selitä se heti seuraavassa lauseessa. Esimerkki: "RSI on 53. RSI mittaa onko osake ylikuumentunut — yli 70 tarkoittaa ylikuumentunutta."
- Ei hypeä. Ei "historiallinen" tai "vallankumouksellinen". Fakta riittää.
- Jokainen lause ansaitsee paikkansa. Jos lauseen voi poistaa ilman että tieto häviää, poista se.

ESIMERKKI hyvästä "Mistä nousu syntyy" -kentästä:
"Osake nousi 7% ja kaupankäyntivolyymi tuplaantui. Se tarkoittaa, että suuret sijoitusrahastot ostivat — ei pienet yksityissijoittajat. Silti kurssi ei ole vielä ylikuumentunut: RSI on 53, kun monet teknologiaosakkeet ovat tällä hetkellä 80–90 tasolla.

Kasvu ei riipu uusista asiakkaista. Yhtiö laskuttaa nykyisiä asiakkaita käytön mukaan — mitä enemmän he käyttävät, sitä enemmän yhtiö tienaa. Asiakaspohja on jo olemassa. Kasvu tulee automaattisesti."

MITÄ ETSITÄÄN:
- Yhtiöt joiden tailwind on massiivinen ja varma (AI-infrastruktuuri, energiamuutos, demografinen muutos, geopolitiikan voittajat)
- Aliarvostettuja nimiä jotka eivät ole "kuumia" — iso raha ei ole vielä herännyt
- Yhtiöt joilla on monopoliasema, verkkopelot (network effects) tai korkeat vaihtokustannukset
- Vältetään: ylikuumennettuja AI-hypeosakkeitajotka ovat jo nousseet 200%, spekulatiivisia mikrokapeja ilman liikevaihtoa

VASTAA JSON-MUODOSSA — vain jos analyysi täyttää korkeat standardit:
[
  {
    "title": "YHTIÖN NIMI: Iskevä otsikko joka kertoo koko tarinan yhdessä lauseessa",
    "tickers": "TICKER",
    "summary": "KUKA TÄMÄ ON: 2 kappaletta. Ensimmäinen: mitä yhtiö tekee yhdellä konkreettisella lauseella. Toinen: mikä tekee siitä erityisen tai erilaisen kuin kilpailijat.",
    "global_context": "ISO KUVA: 2 kappaletta. Ensimmäinen: mikä iso muutos maailmassa on käynnissä. Toinen: miten juuri tämä yhtiö hyötyy siitä enemmän kuin muut.",
    "reasoning": "MISTÄ NOUSU SYNTYY: 2 kappaletta. Ensimmäinen: mikä signaali tai fakta kertoo että markkinat ovat hinnoitelleet väärin. Toinen: mikä konkreettinen asia muuttuu 6-18kk sisällä.",
    "metrics_explanation": "NUMEROT PUHUVAT: 2 kappaletta. Ensimmäinen: 1-2 tärkeintä lukua selitettynä tavalliselle ihmiselle. Toinen: mitä nämä luvut tarkoittavat — onko yhtiö halpa vai kallis.",
    "time_horizon": "MIKÄ VOI MENNÄ PIELEEN: 2-3 lyhyttä kappaletta. Jokainen kappale = yksi riski selitettynä. Ole rehellinen.",
    "company_history": "EXIT-STRATEGIA: 2 kappaletta. Ensimmäinen: millä hinnalla tai tapahtumalla myydään. Toinen: mitä merkkiä seurataan ennen kuin se tapahtuu.",
    "recommendation": "OSTA",
    "risk_level": "Matala, Keskisuuri tai Korkea",
    "confidence": 85,
    "sector": "Toimiala",
    "invalidation_risks": "Lyhyt lista — milloin alkuperäinen teesi on rikki"
  }
]

KRIITTISET SÄÄNNÖT:
1. "recommendation" on AINA "OSTA" — teet vain ostocaseja. Jos et voi suositella ostamista rehellisesti, älä tee analyysia.
2. "tickers"-kenttään yksi ainoa pörssitunnus. ÄLÄ laita useita.
3. "title"-kenttä koskee VAIN tätä yhtiötä. ÄLÄ mainitse kilpailijoita.
4. Jos et löydä tarpeeksi hyviä kohteita, palauta tyhjä lista []. Se on oikea vastaus.
5. Vastaa pelkällä validilla JSON-taulukolla. Älä kirjoita mitään muuta.
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

def generate_scenarios(news_text: str, movers_text: str, client=None) -> List[dict]:
    user_message = f"Luo 1-3 syvällistä analyysia hyödyntäen omia laajempia tekoälyn päättelytaitojasi sekä näitä tuoreita tietoja:\n\nDATA:\n{movers_text}\n\nVIIMEISIMMÄT UUTISET (Käytä näitä ponnahduslautana omalle laajemmalle historialliselle ja tulevaisuutta ennakoivalle ajattelullesi):\n{news_text[:4000]}"
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
    
    KÄYTTÄJÄN TIUKKA EHTO: Sijoitushorisontti on PITKÄ (+6 kk). 
    JOS ALKUPERÄINEN PERUSTELU PÄTEE YHÄ: Sitä EI SAA poistaa! Vaikka uutisia ei olisi, tai tulisi pientä heilahtelua, äla poista, jos alkuperäinen iso tarina on vielä hengissä.
    JOS ALKUPERÄINEN PERUSTELU ON MURTUMASSA: Sitten sen saa poistaa (INVALID).
    
    ASETA STATUS:
    - 'VALID': Jos alkuperäinen teesi on yhä elossa. Uutishiljaisuus on OK.
    - 'UPDATE': Jos on tullut jotain uutta olennaista tietoa, joka vahvistaa tai muuttaa hieman lukemia.
    - 'INVALID': VAIN jos on selkeitä todisteita, että ALKUPERÄINEN PERUSTELU ON ROMAHTANUT tai sijoituscase kuollut.
    
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
