import json, re, urllib.request
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
G = "https://youmind.com/seedance-2-5-prompts/explore"
with urllib.request.urlopen(urllib.request.Request(G, headers={"User-Agent": UA}), timeout=60) as r:
    open("probe/explore.html", "w").write(r.read().decode("utf-8", "replace"))
out = {"requests": [], "bodies": []}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000})
    pg.on("request", lambda r: out["requests"].append([r.method, r.resource_type, r.url[:300], (r.post_data or "")[:800]])
          if r.resource_type in ("xhr", "fetch") and "youmind.com" in r.url else None)
    def resp(r):
        try:
            if r.request.resource_type in ("xhr", "fetch") and "youmind.com" in r.url and r.status == 200:
                t = r.text()
                if len(t) > 500:
                    out["bodies"].append([r.url[:300], len(t), t[:4000]])
        except Exception:
            pass
    pg.on("response", resp)
    pg.goto(G, wait_until="networkidle", timeout=90000)
    try:
        pg.get_by_text("Reject advertising cookies").click(timeout=3000)
    except Exception:
        pass
    n0 = len(out["requests"])
    counts = []
    for i in range(15):
        cards = pg.locator("a[href*='/video-prompts/']")
        c = cards.count(); counts.append(c)
        if c:
            cards.nth(c - 1).scroll_into_view_if_needed()
        pg.keyboard.press("End"); pg.mouse.wheel(0, 8000)
        for t in ("Load more", "Show more", "More"):
            try:
                pg.get_by_text(t, exact=True).first.click(timeout=500)
            except Exception:
                pass
        pg.wait_for_timeout(2500)
    out["counts"] = counts
    out["requests_after_load"] = out["requests"][n0:]
    out["final_links"] = sorted(set(re.findall(r'/video-prompts/[a-z0-9-]+', pg.content())))
    out["scrollables"] = pg.evaluate("""() => [...document.querySelectorAll('*')].filter(e => {const s=getComputedStyle(e);
        return (s.overflowY=='auto'||s.overflowY=='scroll') && e.scrollHeight>e.clientHeight+50}).map(e => e.tagName+'.'+(e.className||'').toString().slice(0,80)+' '+e.scrollHeight)""")
    pg.screenshot(path="probe/after_scroll.png", full_page=False)
    b.close()
json.dump(out, open("probe/result3.json", "w"), indent=1)
print(out["counts"], len(out["final_links"]), len(out["requests_after_load"]))
