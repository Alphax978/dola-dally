import json, re
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(user_agent=UA)
    pg.goto("https://reelcine.org/terms", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(4000)
    t = pg.inner_text("body")
    b.close()
open("probe/reelcine_terms.txt", "w").write(t)
print(len(t))
