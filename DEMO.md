pkill -f "uvicorn pay.main"
cd ~/LegisLabs/CDIR && EXTRACTION_MODE=fixture VOUCH_MODE=fixture PAYMENT_RAIL=local .venv/bin/uvicorn pay.main:app --port 8014 --reload
