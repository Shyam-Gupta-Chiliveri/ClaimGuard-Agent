import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("N8N_WEBHOOK_URL", None)
