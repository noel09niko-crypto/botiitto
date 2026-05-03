import os
from dotenv import load_dotenv
load_dotenv()
from src.ai_analyzer import _get_completion, SYSTEM_PROMPT
print("Getting completion...")
content = _get_completion("Luo analyysi testidatasta. DATA: AAPL", system_msg=SYSTEM_PROMPT, max_tokens=8000)
print("CONTENT IS:")
print(content)
