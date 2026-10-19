import json, re, urllib.request
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
out = {}
s, out["robots"] = get("https://pollo.ai/robots.txt"); out["robots"] = out["robots"][:3000]
reqs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000})
    pg.on("request", lambda r: reqs.append([r.method, r.url[:300], (r.post_data or "")[:300]]) if r.resource_type in ("xhr", "fetch") and "pollo" in r.url else None)
    pg.goto("https://pollo.ai/prompts/seedance-2-5", wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(3000)
    body = pg.inner_text("body")
    out["total_mentions"] = re.findall(r"[\d,.]+\s*K?\+?\s*(?:prompts|videos|results)", body, re.I)[:10]
    counts = []
    for i in range(10):
        links = set(re.findall(r'href="(/prompts?/[^"#?]+)"', pg.content()))
        counts.append(len(links)); pg.mouse.wheel(0, 8000); pg.wait_for_timeout(2000)
    html = pg.content()
    out["scroll_link_counts"] = counts
    out["links_sample"] = sorted(set(re.findall(r'href="(/prompts?/[^"#?]+)"', html)))[:40]
    out["mp4"] = len(set(re.findall(r'https://[^"\s]+\.mp4', html)))
    out["xposts"] = len(set(re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', html)))
    out["pager"] = sorted(set(re.findall(r'href="([^"]*[?&]page=\d+[^"]*)"', html)))[:10]
    out["buttons"] = [t.strip() for t in pg.locator("button").all_inner_texts() if t.strip()][:40]
    for path in ("/terms", "/terms-of-service", "/terms-of-use"):
        try:
            pg.goto("https://pollo.ai" + path, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(2000)
            t = pg.inner_text("body")
            if len(t) > 3000:
                open("probe/pollo_terms.txt", "w").write(t); out["terms_url"] = path; break
        except Exception as e:
            out["terms_err_" + path] = str(e)[:100]
    b.close()
out["xhr"] = reqs[:60]
json.dump(out, open("probe/pollo.json", "w"), indent=1)
