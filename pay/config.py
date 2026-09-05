"""Settings for the payments vertical. Everything has a safe default for local runs.

Shares the repo .env with the HMRC app (same Gemini key, plus the vouch.finance
sandbox key). Data lives in its own folder so both apps can run side by side.
"""
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

DATA_DIR = Path(os.environ.get("PAY_DATA_DIR", Path(os.environ.get("DATA_DIR", ROOT / "data")) / "pay"))
DB_PATH = Path(os.environ.get("PAY_DB_PATH", DATA_DIR / "agent_passport_pay.db"))
KEYS_DIR = Path(os.environ.get("PAY_KEYS_DIR", DATA_DIR / "keys"))
RULEPACK_PATH = Path(os.environ.get("PAY_RULEPACK_PATH", ROOT / "rulepacks" / "payments-2026.09.json"))
FIXTURES_DIR = ROOT / "fixtures" / "pay"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# "gemini" uses the API with fixture fallback on failure; "fixture" never calls the API.
EXTRACTION_MODE = os.environ.get("EXTRACTION_MODE", "gemini" if GEMINI_API_KEY else "fixture")

# vouch.finance sandbox. fixture = canned responses; live = https://cdir.vouch.finance/api/v1
VOUCH_MODE = os.environ.get("VOUCH_MODE", "fixture")
VOUCH_API_KEY = os.environ.get("HACKATHON_ORG_API_KEY", "")
VOUCH_BASE_URL = os.environ.get("API_BASE_URL", "https://cdir.vouch.finance/api/v1").rstrip("/")
# local = the bank executes; vouch = also settle each ALLOW on the vouch rail (needs a seeded kit)
PAYMENT_RAIL = os.environ.get("PAYMENT_RAIL", "local")

# The cast. Synthetic names; jurisdiction-neutral authority.
ISSUER = "payments-authority-demo"
ISSUER_NAME = "National Payments Supervisor (demo)"
OFFICER = "A. Ferreira"
OPERATOR = "PayRail Ltd"
CUSTOMER = "Northgate Joinery Ltd"
BANK = "Northgate's bank (demo)"
AGENT_NAME = "Agent 247"
APP_VERSION = "0.2.0"
