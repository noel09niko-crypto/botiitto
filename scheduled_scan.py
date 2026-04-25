#!/usr/bin/env python3
"""Itsenäinen ajastettu skannaus – ei vaadi palvelinta."""
import os
import sys

# Aseta polut
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

from src.background_worker import run_scenario_generation

if __name__ == "__main__":
    print(f"[CRON] Käynnistetään ajastettu skannaus...")
    try:
        run_scenario_generation()
        print(f"[CRON] Skannaus valmis.")
    except Exception as e:
        print(f"[CRON] Virhe: {e}")
