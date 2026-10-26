import json, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:120], ""
out = {}
for key, ident in (("school-hallway-fight-sequence-6871", "6871"), ("f388804a-d2ce-4ec2-80e2-d0f1613d2014", "f388804a")):
    s, h = get(f"https://domer.io/ai-video-generator?template={key}")
    u = h.replace('\\"', '"').replace("\\u002F", "/")
    hits = [m.start() for m in re.finditer(re.escape(ident), u)]
    out[key] = {"status": s, "len": len(h), "id_hits": len(hits),
                "contexts": [u[max(0, i - 400): i + 700] for i in hits[:3]],
                "mp4": list(dict.fromkeys(re.findall(r"https://storage\.brightvectorlabs\.com/[^\"\s]+?\.mp4", u)))[:6],
                "x_posts": list(dict.fromkeys(re.findall(r"https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+", u)))[:4]}
    for cand in (f"https://domer.io/prompts/{key}", f"https://domer.io/prompts/seedance-{ident}", f"https://domer.io/prompts/seedance-2-5-{ident}"):
        s2, h2 = get(cand)
        out[key].setdefault("detail_pages", {})[cand] = [s2, len(h2), (re.search(r"<title>(.*?)</title>", h2) or [None, ""])[1][:100]]
json.dump(out, open("probe/domer_tpl.json", "w"), indent=1, ensure_ascii=False)
