import re, html, urllib.request, json
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
def text(h):
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()
out = {}
for name, u in [("robots", "https://reelcine.org/robots.txt"), ("terms", "https://reelcine.org/terms"),
                ("sitemap", "https://reelcine.org/sitemap.xml"), ("entry", "https://reelcine.org/video-prompt/4628"),
                ("entry_low", "https://reelcine.org/video-prompt/2")]:
    s, h = get(u)
    out[name] = {"status": s, "len": len(h)}
    if name == "robots": out[name]["body"] = h[:4000]
    elif name == "terms": out[name]["body"] = text(h)[:20000]
    elif name == "sitemap": out[name]["body"] = h[:1500]; out[name]["video_prompt_urls"] = len(re.findall(r"/video-prompt/\d+", h))
    else: out[name]["mp4"] = re.findall(r'https://assets-prompts\.reelcine\.org/[^"\\ ]+\.mp4', h)[:2]; out[name]["x"] = re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', h)[:2]
json.dump(out, open("probe/reelcine.json", "w"), indent=1)
