"""Settings from environment. Everything has a safe default for local runs."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "agent_passport.db"))
KEYS_DIR = Path(os.environ.get("KEYS_DIR", DATA_DIR / "keys"))
RULEPACK_PATH = Path(os.environ.get("RULEPACK_PATH", ROOT / "rulepacks" / "hmrc-sa-2026.09.json"))
FIXTURES_DIR = ROOT / "fixtures"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# "gemini" uses the API with fixture fallback on failure; "fixture" never calls the API.
EXTRACTION_MODE = os.environ.get("EXTRACTION_MODE", "gemini" if GEMINI_API_KEY else "fixture")

ISSUER = "uk-tax-authority-demo"
ISSUER_NAME = "UK Tax Authority (demo)"
OFFICER = "M. Whitcombe"
APP_VERSION = "0.1.0"
