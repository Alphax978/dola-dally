import json, re, urllib.request, collections
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
out = {}
s, idx = get("https://domer.io/sitemap.xml"); out["index"] = idx[:1500]
maps = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", idx)
out["maps"] = maps
for m in maps:
    if "prompt" in m:
        s, x = get(m)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
        out.setdefault("prompt_maps", {})[m] = {"status": s, "count": len(locs), "sample": locs[:8],
                                                "patterns": collections.Counter(re.sub(r"[^/]+$", "*", l) for l in locs).most_common(8)}
# open one seedance-2-5 style entry
samples = []
for m, v in out.get("prompt_maps", {}).items():
    samples += v["sample"]
for u in samples[:4]:
    s, h = get(u)
    out.setdefault("entries", []).append({"url": u, "status": s, "len": len(h),
        "title": (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:120],
        "mp4": list(dict.fromkeys(re.findall(r'https?://[^"\s\\]+\.mp4', h)))[:3],
        "x": list(dict.fromkeys(re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', h)))[:3],
        "model_mentions": list(dict.fromkeys(re.findall(r"Seedance\s*\d\.\d|Nano Banana[\w .]*|GPT Image \d", h)))[:5]})
json.dump(out, open("probe/domer2.json", "w"), indent=1)
