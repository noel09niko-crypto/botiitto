#!/usr/bin/env python3
"""
Investing Bot - Analysoi markkinauutiset ja antaa 5 sijoitussuositusta.
"""

import os
import sys
import time
import schedule
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from src.news_fetcher import fetch_all_news, format_news_for_prompt
from src.stock_analyzer import get_market_snapshot, get_top_movers, format_movers_for_prompt, WATCHLIST, get_research_bundle
from src.ai_analyzer import analyze_market, quick_news_scan, get_client, analyze_single_stock
from src.database import add_scenario, init_db

load_dotenv(override=True)
console = Console()


def check_env():
    anth_key = os.environ.get("ANTHROPIC_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    if not anth_key and not groq_key:
        console.print("[red]VIRHE: Sekä ANTHROPIC_API_KEY että GROQ_API_KEY puuttuvat![/red]")
        sys.exit(1)
        
    if anth_key:
        console.print("[green]✓ Claude (Anthropic) käytössä ensisijaisena.[/green]")
    elif groq_key:
        console.print("[yellow]! Claude puuttuu, käytetään Groqia fallbackina.[/yellow]")
    
    return anth_key or groq_key


def print_header():
    console.print(Panel(
        Text("INVESTING BOT\nMarkkinaanalyysi & Sijoitussuositukset", justify="center", style="bold green"),
        subtitle=f"[dim]{datetime.now().strftime('%d.%m.%Y %H:%M')}[/dim]",
        border_style="green",
    ))


def run_analysis():
    print_header()
    client = get_client()

    # 1. Hae uutiset
    console.print("\n[cyan]Haetaan päivän uutiset...[/cyan]")
    articles = fetch_all_news(max_age_hours=24)
    console.print(f"[green]✓ {len(articles)} artikkelia löydetty[/green]")

    if not articles:
        console.print("[yellow]Varoitus: Ei uutisia saatavilla. Jatketaan vain kurssidatalla.[/yellow]")

    news_text = format_news_for_prompt(articles, max_articles=60)

    # 2. Nopea uutisskannaaus - etsi mainitut osakkeet
    mentioned_tickers = []
    if articles:
        console.print("\n[cyan]Skannataan uutisista mainitut osakkeet...[/cyan]")
        mentioned_tickers = quick_news_scan(news_text, client)
        if mentioned_tickers:
            console.print(f"[green]✓ Uutisissa mainitut: {', '.join(mentioned_tickers)}[/green]")

    # 3. Hae kurssit
    console.print("\n[cyan]Haetaan kurssitiedot...[/cyan]")
    console.print("[dim](Tämä voi kestää 30-60 sekuntia)[/dim]")

    all_tickers = list(dict.fromkeys(mentioned_tickers + WATCHLIST))
    snapshot = get_market_snapshot(all_tickers)

    if not snapshot:
        console.print("[red]Ei kurssidataa saatavilla. Tarkista internet-yhteys.[/red]")
        return

    console.print(f"[green]✓ {len(snapshot)} osakkeen data haettu[/green]")

    movers = get_top_movers(snapshot, top_n=15)
    movers_text = format_movers_for_prompt(movers)

    # Näytä quick-view liikkujista
    console.print("\n[bold yellow]TOP LIIKKUJAT TÄNÄÄN:[/bold yellow]")
    console.print(movers_text)

    # Kerää top-movers tickerit lisätietoja varten
    top_tickers = (
        [s["ticker"] for s in movers["gainers"][:5]]
        + [s["ticker"] for s in movers["losers"][:5]]
        + mentioned_tickers[:5]
    )
    top_tickers = list(dict.fromkeys(top_tickers))

    # 4. Claude-analyysi
    console.print("\n[cyan]Claude analysoi markkinatilannetta...[/cyan]")
    console.print("[dim](Tämä voi kestää 20-40 sekuntia)[/dim]")
    
    results_as_dicts = []
    for ticker in top_tickers:
        # Nyt käytetään uutta research_bundlea jos mahdollista
        bundle = get_research_bundle(ticker)
        res_dict = analyze_single_stock(ticker, bundle, news_text)
        if res_dict:
            results_as_dicts.append(res_dict)
            # Tallennetaan suoraan tietokantaan!
            add_scenario(res_dict)
            console.print(f"[green]✓ {ticker} analysoitu ja tallennettu tietokantaan.[/green]")

    if not results_as_dicts:
        console.print("[red]Analyysi epäonnistui: ei saatu tuloksia AI:lta.[/red]")
        return

    # Luodaan teksti-yhteenveto raporttia varten
    analysis_text = ""
    for r in results_as_dicts:
        analysis_text += f"--- {r.get('title', 'Tuntematon')} ({r.get('tickers', 'N/A')}) ---\n"
        analysis_text += f"SUOSITUS: {r.get('recommendation', 'TARKKAILE')} | PISTEET: {r.get('confidence', '0/19')}\n"
        analysis_text += f"YHTEENVETO: {r.get('summary', '')}\n"
        analysis_text += f"PERUSTELU:\n{r.get('reasoning', '')}\n\n"

    # 5. Tulosta analyysi
    console.print("\n")
    console.print(Panel(
        analysis_text,
        title="[bold green]5 SIJOITUSSUOSITUSTA[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))

    # Tallenna tulos tiedostoon
    output_file = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Investing Bot Analyysi - {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
        f.write("=" * 60 + "\n\n")
        f.write("TOP LIIKKUJAT:\n")
        f.write(movers_text + "\n\n")
        f.write("=" * 60 + "\n\n")
        f.write("SIJOITUSSUOSITUKSET:\n\n")
        f.write(analysis_text)

    console.print(f"\n[dim]Analyysi tallennettu: {output_file}[/dim]")
    console.print("\n[bold]Seuraava analyysi: " + _next_run_time() + "[/bold]")


def _next_run_time() -> str:
    interval = int(os.environ.get("INTERVAL_HOURS", "4"))
    from datetime import timedelta
    next_run = datetime.now() + timedelta(hours=interval)
    return next_run.strftime("%H:%M")


def run_scheduled():
    interval = int(os.environ.get("INTERVAL_HOURS", "4"))
    console.print(f"\n[green]Botti käynnissä. Analyysi ajetaan {interval} tunnin välein.[/green]")
    console.print("[dim]Lopeta: Ctrl+C[/dim]\n")

    run_analysis()

    schedule.every(interval).hours.do(run_analysis)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    check_env()

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_analysis()
    else:
        run_scheduled()


if __name__ == "__main__":
    main()
