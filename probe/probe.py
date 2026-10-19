import json, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:120], ""
out = {}
B = "https://domer.io/prompts/models/seedance-2-5"
s, h = get(B)
u = h.replace('\\"', '"')
i = u.find('"10456"'); out["around_id"] = u[max(0, i - 700): i + 900] if i >= 0 else "none"
for k in ("pages", "total", "page"):
    out["ctx_" + k] = [u[max(0, m.start() - 150): m.start() + 150] for m in re.finditer(r'"%s"\s*:' % k, u)][:3]
out["sources"] = sorted(set(re.findall(r'"source"\s*:\s*"([^"]+)"', u)))
out["item_ids"] = len(set(re.findall(r'"id"\s*:\s*"(\d{4,6})"', u)))
first = set(re.findall(r'seedance-2-5/bright/media/[^"\s]+?\.mp4', u))
for t in [B + "/2", B + "/page/2", B + "?p=2", B + "?page=2&limit=100", "https://domer.io/prompts/media/video?model=seedance-2-5"]:
    s2, h2 = get(t)
    m = set(re.findall(r'seedance-2-5/bright/media/[^"\s\\]+?\.mp4', h2))
    out[t] = [s2, len(m), len(m - first)]
json.dump(out, open("probe/domer8.json", "w"), indent=1, ensure_ascii=False)
