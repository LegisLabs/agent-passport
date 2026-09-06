import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from playwright.sync_api import sync_playwright
from walk_iteration2 import issue
BASE="http://127.0.0.1:8014"; bad=[]; errs=[]
def check(c,m): (print("  ✓",m) if c else (bad.append(m), print("  ✗",m)))
with sync_playwright() as pw:
    b=pw.chromium.launch(); page=b.new_page(); page.on("pageerror", lambda e: errs.append(str(e)))
    page.request.post(BASE+"/api/reset"); issue(page)
    page.goto(BASE+"/bank"); page.wait_for_selector("#chain-toggle")
    check(not page.locator("#chain-toggle").is_checked() and page.locator("#chain-beats-wrap").is_hidden(), "chain off by default, boundary beats hidden")
    page.check("#chain-toggle"); check(page.locator("#chain-beats-wrap").is_visible() and page.locator("#chain-beats button").count()==4, "toggle reveals four boundary beats")
    page.locator("#invoice-buttons button").nth(1).click(); page.wait_for_selector('#invoice-steps [data-step="d"]:not([hidden])', timeout=60000)
    check(page.locator("#inv-chain").is_visible() and "c.b" in page.locator("#inv-chain").inner_text().lower() and "s_action ⊆ s_1 ⊆ s_0" in page.locator("#inv-chain").inner_text().lower(), "poisoned invoice with chain shows the invariant and checks")
    v=page.locator("#inv-verdict").inner_text().lower(); check("deny" in v and "c.b" in v, f"poisoned+chain verdict: {v.splitlines()[0]}")
    exp=[("ALLOW","c.c ✓"),("DENY","c.c ✗"),("DENY","c.b ✗"),("DENY","c.b ✗")]
    for i,(d,mark) in enumerate(exp):
        n=page.locator("#term-lines li:has(.t-verdict)").count(); page.locator("#chain-beats button").nth(i).click()
        page.wait_for_function(f"document.querySelectorAll('#term-lines li .t-verdict').length > {n}")
        li=page.locator("#term-lines li:has(.t-verdict)").last; v=li.locator(".t-verdict").inner_text(); t=li.inner_text().lower()
        check(v==d and mark in t, f"chain beat {i+1}: {v} · {mark in t}")
    page.screenshot(path="/tmp/agent-passport-shots/i2-04-chain.png", full_page=True)
    m=b.new_context(viewport={"width":390,"height":844}).new_page(); m.goto(BASE+"/bank"); m.wait_for_timeout(800)
    check(m.evaluate("document.documentElement.scrollWidth")<=390, "bank 390px no overflow")
    b.close()
print("errors:", errs or "none"); print("CHAIN PROBLEMS:", bad or "none")
