import json, re, urllib.request, collections, random
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
out = {}
s, x = get("https://domer.io/sitemap-prompt-0.xml")
locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
en = [l for l in locs if re.match(r"https://domer\.io/prompts/[^/]+$", l)]
out["en_entries"] = len(en); out["en_sample"] = en[:15]
out["langs"] = collections.Counter((re.match(r"https://domer\.io/([a-z]{2})/", l) or [None, "en"])[1] for l in locs).most_common()
random.seed(1)
for u in random.sample(en, min(8, len(en))):
    s, h = get(u)
    mp4 = [m for m in dict.fromkeys(re.findall(r'https?://[^"\s\\]+\.mp4', h)) if "/prompts/" in m][:2]
    out.setdefault("entries", []).append({"url": u, "status": s,
        "title": (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:120],
        "mp4": mp4, "img": [m for m in dict.fromkeys(re.findall(r'https?://storage\.brightvectorlabs\.com/prompts/[^"\s\\]+\.(?:jpg|jpeg|png|webp)', h))][:1],
        "x": list(dict.fromkeys(re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', h)))[:2],
        "models": list(dict.fromkeys(re.findall(r"Seedance\s*\d(?:\.\d)?|Nano Banana[ \w.]{0,6}|GPT Image \d(?:\.\d)?|Grok Imagine|MiniMax H\d", h)))[:5]})
json.dump(out, open("probe/domer3.json", "w"), indent=1)
