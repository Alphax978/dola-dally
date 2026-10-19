import json, re, urllib.request, html as H
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
out = {}
s, r = get("https://domer.io/robots.txt"); out["robots"] = [s, r[:3000]]
s, sm = get("https://domer.io/sitemap.xml"); out["sitemap"] = [s, len(sm), sm[:800]]
locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm)
out["sitemap_locs"] = len(locs); out["sitemap_sample"] = [l for l in locs if "prompt" in l][:15]
s, page = get("https://domer.io/prompts/models/seedance-2-5")
out["static"] = {"status": s, "len": len(page), "mp4": re.findall(r'https?://[^"\s]+\.mp4', page)[:3],
                 "x": re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', page)[:3],
                 "prompt_links": sorted(set(re.findall(r'href="(/prompts/[^"#]+)"', page)))[:20],
                 "pager": sorted(set(re.findall(r'href="([^"]*page=\d+[^"]*)"', page)))[:10]}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000})
    reqs = []
    pg.on("request", lambda q: reqs.append([q.method, q.url[:250]]) if q.resource_type in ("xhr", "fetch") and "domer" in q.url else None)
    pg.goto("https://domer.io/prompts/models/seedance-2-5", wait_until="networkidle", timeout=90000)
    counts = []
    for i in range(6):
        counts.append(len(set(re.findall(r'href="(/prompts/[^"#]+)"', pg.content())))); pg.mouse.wheel(0, 8000); pg.wait_for_timeout(1500)
    out["rendered"] = {"counts": counts, "links": sorted(set(re.findall(r'href="(/prompts/[^"#]+)"', pg.content())))[:30],
                       "mp4": re.findall(r'https?://[^"\s]+\.mp4', pg.content())[:3], "xhr": reqs[:30]}
    links = out["rendered"]["links"] or out["static"]["prompt_links"]
    det = [l for l in links if l.count("/") >= 3 and "models" not in l][:1]
    if det:
        pg.goto("https://domer.io" + det[0], wait_until="networkidle", timeout=90000)
        c = pg.content()
        out["detail"] = {"url": det[0], "mp4": re.findall(r'https?://[^"\s]+\.mp4', c)[:3],
                         "x": re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', c)[:3], "text": pg.inner_text("body")[:1500]}
    pg.goto("https://domer.io/terms-of-service", wait_until="networkidle", timeout=90000); pg.wait_for_timeout(2000)
    open("probe/domer_terms.txt", "w").write(pg.inner_text("body"))
    b.close()
json.dump(out, open("probe/domer.json", "w"), indent=1)
