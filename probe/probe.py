import json, re, urllib.request, html as H
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        return ""
T = "5adfe2f7-4920-4010-a986-128d234e922d"
out = {}
for page in ("https://domer.io/prompts/models/seedance-2-5", "https://domer.io/explore/seedance-2-5"):
    h = get(page)
    i = h.find("template=" + T)
    card = h[i: i + 2500] if i >= 0 else ""
    out[page] = {"found": i >= 0,
                 "mp4": re.findall(r"https://storage\.brightvectorlabs\.com/prompts/seedance-2-5/[^\"'\s<>]+?\.mp4", card)[:2],
                 "img_alt": re.findall(r'alt="([^"]+)"', card)[:2],
                 "templates_on_page": len(set(re.findall(r"template=([A-Za-z0-9\-]+)", h)))}
title = next((v["img_alt"][0] for v in out.values() if v["img_alt"]), None)
h = get("https://domer.io/prompts/models/seedance-2-5")
allmp4 = list(dict.fromkeys(re.findall(r"https://storage\.brightvectorlabs\.com/prompts/seedance-2-5/[^\"'\s<>\\]+?\.mp4", h)))
tslug = re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-").lower()
mp4 = next((m for m in allmp4 if tslug and tslug in m.lower()), None)
i = h.find("template=" + T)
a = h.rfind("<article", 0, i)
b = h.find("</article>", i)
out["card_html"] = h[a:b + 10][:4000]
out["mp4_names"] = [m.rsplit("/", 1)[1] for m in allmp4]
templates = list(dict.fromkeys(re.findall(r"template=([A-Za-z0-9\-]+)", h)))
out["template_index"] = templates.index(T) if T in templates else None
if not mp4:
    mp4 = "none"
out["all_mp4_count"], out["title_slug"] = len(allmp4), tslug
out["mp4"], out["title"] = mp4, title
if mp4:
    fname = mp4.rsplit("/", 1)[1]
    ident = fname.split("_")[1] if fname.count("_") >= 2 else "zzzz-none"
    out["file_id"] = ident
    # YouMind: same collection; find the page whose video file has the same id
    robots = get("https://youmind.com/robots.txt")
    maps = re.findall(r"Sitemap:\s*(\S+)", robots)
    locs = []
    for m in maps:
        x = get(m)
        subs = re.findall(r"<loc>\s*(\S+?)\s*</loc>", x)
        for s in subs:
            if "/prompts/" in s and s.endswith(".xml"):
                locs += re.findall(r"<loc>\s*(\S+?)\s*</loc>", get(s))
            elif "video-prompts/" in s:
                locs.append(s)
    vids = sorted({re.sub(r"https://youmind\.com/[a-z]{2}(-[A-Z]{2})?/", "https://youmind.com/", l) for l in locs if "/video-prompts/" in l})
    out["youmind_pages"] = len(vids)
    words = set(re.findall(r"[a-z0-9]+", (title or "").lower())) - {"the", "a", "and", "of", "with", "in"}
    scored = sorted(vids, key=lambda u: -len(words & set(u.rsplit("/", 1)[1].split("-"))))[:4]
    out["candidates"] = []
    for u in scored:
        p = get(u)
        ms = set(re.findall(r"https://cms-assets\.youmind\.com/media/[^\"'\s<>]+?\.mp4", p))
        out["candidates"].append({"url": u, "same_file_id": any(ident and ident in m for m in ms),
                                  "x_post": (re.search(r"https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+", p) or [None])[0] if p else None})
json.dump(out, open("probe/domer25c.json", "w"), indent=1, ensure_ascii=False)
