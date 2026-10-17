import json, re, urllib.request
from playwright.sync_api import sync_playwright
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
G = "https://youmind.com/seedance-2-5-prompts/explore"
out = {}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e), ""
links = lambda s: sorted(set(re.findall(r'/video-prompts/[a-z0-9-]+', s)))
st, html = get(G)
out["static_count"] = len(links(html))
out["static_len"] = len(html)
# page-number guesses
for q in ["?page=2", "?p=2", "/2", "?offset=24", "?cursor=2"]:
    s, h = get(G + q)
    out[f"guess {q}"] = [s, len(links(h)), len(set(links(h)) - set(links(html)))]
# anything in the html that looks like an api or next-page hint
out["html_hints"] = sorted(set(re.findall(r'(?:"|\')(/api/[^"\']{0,120}|https://[a-z0-9.-]*youmind[^"\']{0,120}(?:api|graphql|search|list|page)[^"\']{0,80})(?:"|\')', html)))[:80]
out["next_data_keys"] = []
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
if m:
    d = json.loads(m.group(1)); out["next_data_keys"] = list(d.get("props", {}).get("pageProps", {}).keys())[:50]
    out["buildId"] = d.get("buildId")
reqs = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent=UA, viewport={"width": 1366, "height": 900})
    def on_req(r):
        if r.resource_type in ("xhr", "fetch"):
            reqs.append({"url": r.url[:400], "method": r.method, "post": (r.post_data or "")[:600]})
    pg.on("request", on_req)
    resp_bodies = []
    def on_resp(r):
        try:
            if r.request.resource_type in ("xhr", "fetch") and "json" in (r.headers.get("content-type") or ""):
                t = r.text()
                if "video-prompts" in t or "slug" in t:
                    resp_bodies.append({"url": r.url[:400], "body": t[:3000]})
        except Exception:
            pass
    pg.on("response", on_resp)
    pg.goto(G, wait_until="networkidle", timeout=90000)
    counts = []
    for i in range(12):
        pg.mouse.wheel(0, 6000); pg.wait_for_timeout(1800)
        counts.append(len(links(pg.content())))
    out["scroll_counts"] = counts
    out["after_scroll_links"] = links(pg.content())
    # buttons that load more
    out["buttons"] = [t.strip() for t in pg.locator("button").all_inner_texts() if t.strip()][:60]
    b.close()
out["xhr"] = reqs[:120]
out["json_with_videos"] = resp_bodies[:8]
json.dump(out, open("probe/result.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k not in ("xhr", "json_with_videos", "after_scroll_links")}, indent=1)[:3000])
