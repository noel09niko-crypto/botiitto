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


SYSTEM_PROMPT = """Olet sijoitusalan avustaja. Tehtäväsi on tiivistää ja järjestää yhtiöstä saatu raakadata selkeään suomenkieliseen muotoon.

JSON-RAKENNE (VASTAA VAIN TÄLLÄ):
[
  {
    "title": "YHTIÖN NIMI",
    "tickers": "TICKER",
    "summary": "Lyhyt tiivistelmä yhtiön liiketoiminnasta.",
    "global_context": "Yleinen markkinatilanne.",
    "reasoning": "Syy miksi yhtiötä tutkitaan.",
    "competitive_landscape": "Kilpailutilanne.",
    "metrics_explanation": "Tunnusluvut selitettynä.",
    "company_history": "Yhtiön historia ja johto.",
    "recommendation": "OSTA tai TARKKAILE",
    "confidence": "Prosenttiluku 0-100",
    "timeframe": "Ei määritelty",
    "risks": "Keskeisimmät riskit."
  }
]
"""



def get_client():
    return get_anthropic_client()

def get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "placeholder":
        print(f"[VAROITUS] Anthropic-avain puuttuu tai on 'placeholder' ({_get_masked_key('ANTHROPIC_API_KEY')})")
        return None
    return anthropic.Anthropic(api_key=key)


def _get_completion(prompt: str, system_msg: str = None, max_tokens: int = 8192, model: str = "claude-sonnet-4-5-20250929", temperature: float = 0.1) -> str:
    """Yleiskäyttöinen apufunktio AI-kyselyille."""
    anth_client = get_anthropic_client()
    if anth_client:
        try:
            resp = anth_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
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
    
    prompt = f"""ANALYSOI {ticker}. Tee yhteenveto seuraavasta datasta.

TUTKIMUSDATA:
{research_context}

MAAILMANTAPAHTUMAT:
{world_news_text[:2000]}

YRITYSUUTISET:
{news_text[:2000]}
"""
    
    content = _get_completion(prompt, system_msg=SYSTEM_PROMPT)
    
    try:
        start_idx_array = content.find("[")
        start_idx_obj = content.find("{")
        
        if start_idx_array != -1 and (start_idx_obj == -1 or start_idx_array < start_idx_obj):
            start_idx = start_idx_array
            end_idx = content.rfind("]")
        else:
            start_idx = start_idx_obj
            end_idx = content.rfind("}")
            
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content_clean = content[start_idx:end_idx+1]
            data = json.loads(content_clean)
            res = data[0] if isinstance(data, list) else data
            return _fix_recommendation(res)
        return None
    except Exception as e:
        print(f"  [JSON ERROR] {ticker}: {e}")
        return None


