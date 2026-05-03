import os
from dotenv import load_dotenv
load_dotenv()
from src.background_worker import run_scenario_generation
print("Running force scan...")
run_scenario_generation(force=True)
