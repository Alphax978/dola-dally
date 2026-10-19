import json, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
        return r.read().decode("utf-8", "replace")
out = {}
for u in ["https://domer.io/explore/seedance-2-5", "https://domer.io/prompts/models/seedance-2-5"]:
    h = get(u)
    mp4 = list(dict.fromkeys(re.findall(r'https?:(?:\\?/){2}[^"\s\\]+?\.mp4', h.replace("\\u002F", "/"))))
    prom = [m for m in mp4 if "/prompts/" in m]
    i = h.find("seedance-2-5/")
    j = h.find("previewUrl")
    out[u] = {"all_mp4": len(mp4), "prompt_mp4": len(prom), "prompt_sample": prom[:5],
              "n_seedance25_path": h.count("seedance-2-5/"), "n_previewUrl": h.count("previewUrl"),
              "n_sourceUrl": h.count("sourceUrl"), "n_status": h.count("/status/"),
              "around_path": h[max(0, i - 600): i + 400] if i >= 0 else "",
              "around_preview": h[max(0, j - 800): j + 600] if j >= 0 else "",
              "hrefs": list(dict.fromkeys(re.findall(r'href="([^"]+)"', h)))[40:120],
              "keys": sorted(set(re.findall(r'\\"(has(?:More|Next)\w*|next\w*|total\w*|page\w*|cursor\w*)\\"', h)))}
json.dump(out, open("probe/domer7.json", "w"), indent=1, ensure_ascii=False)
