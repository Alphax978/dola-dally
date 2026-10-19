import json, re, urllib.request, collections, sys
sys.path.insert(0, ".")
from prepare_frames import page_text
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
        return r.read().decode("utf-8", "replace")
out = {}
x = get("https://domer.io/sitemap-prompt-0.xml")
locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
en = [l for l in locs if re.match(r"https://domer\.io/prompts/[^/]+$", l)]
out["slug_kinds"] = collections.Counter(re.sub(r"[-_]?\d+$", "", l.rsplit("/", 1)[1]) for l in en).most_common(20)
out["sitemaps"] = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", get("https://domer.io/sitemap.xml"))
nums = sorted(int(l.rsplit("-", 1)[1]) for l in en if re.search(r"/prompts/seedance-\d+$", l))
out["seedance_ids"] = [len(nums), nums[:3], nums[-3:]]
for u in ["https://domer.io/prompts/seedance-7388", "https://domer.io/prompts/seedance-8020"]:
    h = get(u)
    i = h.find("/7388.mp4") if "7388" in u else h.find("/8020.")
    out[u] = {"meta": re.findall(r'<meta[^>]+(?:description|og:)[^>]*>', h)[:8],
              "around_mp4": h[max(0, i - 1500): i + 300],
              "ld": re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)[:3],
              "text": page_text(h, 8000)}
json.dump(out, open("probe/domer4.json", "w"), indent=1)
