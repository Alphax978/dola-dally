import json, re, urllib.request, concurrent.futures as cf
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR " + str(e)
links = lambda s: sorted(set(re.findall(r'/video-prompts/[a-z0-9-]+', s)))
cats = "product-v food-drink-v crowd-group text-logo-v vehicle-v animal-pet cityscape-urban abstract-vfx-v architecture-interior nature-landscape sports-action person-character stop-motion chinese-ink 2d-animation 3d-cartoon documentary surreal-dreamlike vintage-retro anime cyberpunk-scifi fantasy-magical cinematic-realistic game-cinematic channel-intro explainer-tutorial ugc-talking-head brand-commercial music-video short-film social-lifestyle cinematic-showcase".split()
pages = ["https://youmind.com/seedance-2-5-prompts", "https://youmind.com/seedance-2-5-prompts/explore",
         "https://youmind.com/seedance-2-0-prompts", "https://youmind.com/seedance-2-0-prompts/explore",
         "https://youmind.com/prompts/video"] + [f"https://youmind.com/prompts/video/{c}" for c in cats]
pages += [p + q for p in pages[:5] for q in ("?page=2", "?page=3")]
out = {}
with cf.ThreadPoolExecutor(8) as ex:
    res = dict(zip(pages, ex.map(get, pages)))
allv = set()
for p, h in res.items():
    l = links(h); allv |= set(l)
    out[p] = {"n": len(l), "err": h[:80] if h.startswith("ERR") else "", "sample": l[:3],
              "pager": sorted(set(re.findall(r'href="([^"]*(?:page|cursor|offset)=[^"]*)"', h)))[:5],
              "mentions_2_5": h.count("Seedance 2.5"), "mentions_2_0": h.count("Seedance 2.0")}
out["TOTAL_UNIQUE"] = len(allv)
# which model is each video? check a few video pages
sample = sorted(allv)[:0]
ids = sorted(int(re.search(r'-(\d+)$', v).group(1)) for v in allv if re.search(r'-(\d+)$', v))
out["id_range"] = [ids[0], ids[-1], len(ids)] if ids else []
vp = sorted(allv, key=lambda v: int(re.search(r'-(\d+)$', v).group(1)) if re.search(r'-(\d+)$', v) else 0)
picks = vp[:3] + vp[len(vp)//2:len(vp)//2+3] + vp[-3:]
for v in picks:
    h = get("https://youmind.com" + v)
    m = re.findall(r'Seedance ?\d\.\d|Kling[^"<]{0,10}|Veo ?\d|Sora ?\d|Hailuo|Wan ?\d\.\d', h)
    out["model " + v] = sorted(set(m))[:8]
json.dump(out, open("probe/result2.json", "w"), indent=1)
print(json.dumps({k: (v["n"] if isinstance(v, dict) else v) for k, v in out.items()}, indent=0)[:4000])
