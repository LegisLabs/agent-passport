from playwright.sync_api import sync_playwright
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from walk_iteration2 import issue
BASE="http://127.0.0.1:8014"
exp=[("ALLOW","all nine"),("DENY","r.6"),("DENY","r.7"),("ESCALATE","r.9"),("DENY","r.8"),("DENY","r.4"),("DENY","r.6"),("ALLOW","all nine")]
bad=[]
with sync_playwright() as pw:
    b=pw.chromium.launch(); page=b.new_page()
    page.request.post(BASE+"/api/reset"); issue(page)
    page.goto(BASE+"/bank"); page.wait_for_selector("#beats button")
    for i,(d,r) in enumerate(exp):
        n=page.locator("#term-lines li:has(.t-verdict)").count()
        page.locator("#beats button").nth(i).click()
        page.wait_for_function(f"document.querySelectorAll('#term-lines li .t-verdict').length > {n}")
        page.wait_for_function("!document.querySelector('#beats button[data-running]')", timeout=60000)
        li=page.locator("#term-lines li:has(.t-verdict)").last; v=li.locator(".t-verdict").inner_text(); t=li.inner_text().lower()
        ok = v==d and r in t; print(("  ✓" if ok else "  ✗"), f"beat {i+1}: {v} (expected {d} {r})"); ok or bad.append(i+1)
    b.close()
print("BEATS PROBLEMS:", bad or "none")
