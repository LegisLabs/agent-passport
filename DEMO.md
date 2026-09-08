pkill -f "uvicorn pay.main"
cd ~/LegisLabs/CDIR && EXTRACTION_MODE=fixture VOUCH_MODE=fixture PAYMENT_RAIL=local .venv/bin/uvicorn pay.main:app --port 8014 --reload
# baseline between takes: bash scripts/demo_reset.sh            (or the Reset demo link in the footer)
# browser walk:            BASE=http://127.0.0.1:8014 <playwright venv>/bin/python tests/ui/walk_bank_first.py
