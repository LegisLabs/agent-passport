Browser walk-throughs (Playwright, not run by pytest). They drive the real UI in fixture mode and print ✓/✗ per check.

```bash
python3 -m venv /tmp/pw && /tmp/pw/bin/pip install playwright && /tmp/pw/bin/playwright install chromium
PAY_DATA_DIR=/tmp/ap-walk EXTRACTION_MODE=fixture VOUCH_MODE=fixture PAYMENT_RAIL=local .venv/bin/uvicorn pay.main:app --port 8014 &
mkdir -p /tmp/agent-passport-shots
/tmp/pw/bin/python tests/ui/walk_iteration2.py   # review assistant, invoice demo, exception loop, labels, 390px
/tmp/pw/bin/python tests/ui/walk_beats.py        # the eight bank beats in order
/tmp/pw/bin/python tests/ui/walk_chain.py        # delegation chain toggle and boundary beats
```
Each script resets the demo database it points at.
