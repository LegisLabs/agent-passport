"""Settings for Agent Passport, bank-first. Everything has a safe default for local runs.

Shares the repo .env with the tax demonstrator (same Gemini key, plus the vouch.finance
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
DB_PATH = Path(os.environ.get("PAY_DB_PATH", DATA_DIR / "agent_passport_bank.db"))
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

# Delegation chain (AI agent orchestrator -> execution agent). off | on. Per-request override allowed.
DELEGATION_CHAIN = os.environ.get("DELEGATION_CHAIN", "off")
DELEGATION_MAX_GBP = float(os.environ.get("DELEGATION_MAX_GBP", "4000"))

# The cast. Synthetic names. Four parties and one observer:
#   the register   an industry body keeps the register of AI products (identity and accountability, no quality judgement)
#   the provider   the AI company that files a registration
#   the bank       admits products to its list, holds the customer's mandate, checks every payment
#   the customer   the business whose money the AI agent moves; signs the mandate inside its bank's app
#   supervisory access   a regulator pulls evidence for an incident through normal supervisory processes
REGISTER_ID = "agent-passport-register-demo"
REGISTER_NAME = "Agent Passport Register (demo)"
REGISTER_OPERATOR = "Agent Passport implementation entity (demo), an industry body on the Open Banking model"
PROVIDER = "OpenPay Ltd"
PRODUCT_NAME = "PayGPT 6.0"
BANK_ID = "meridian-bank-demo"
BANK = "Meridian Bank (demo)"
BANK_OFFICER = "A. Ferreira"
BANK_TEAM = "Payments Risk"
CUSTOMER = "Northgate Joinery Ltd"
CUSTOMER_ID = "northgate-joinery-ltd"
SUPERVISOR = "Supervisory access (demo)"
APP_VERSION = "0.3.0"
