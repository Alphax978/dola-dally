import json, re, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:150], ""
out = {}
for u in ["https://domer.io/explore/seedance-2-5", "https://domer.io/explore/seedance-2-5?page=2",
          "https://domer.io/prompts/models/seedance-2-5", "https://domer.io/prompts/models/seedance-2-5?page=2",
          "https://domer.io/robots.txt"]:
    s, h = get(u)
    mp4 = list(dict.fromkeys(re.findall(r'https?://[^"\s\\]+\.mp4', h)))
    out[u] = {"status": s, "len": len(h), "mp4_count": len(mp4), "mp4_sample": mp4[:4],
              "x_count": len(set(re.findall(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', h))),
              "entry_links": list(dict.fromkeys(re.findall(r'(?:href=\\?")(/(?:[a-z]{2}/)?(?:prompts|explore)/[^"\\?#]+)', h)))[:40],
              "page_params": list(dict.fromkeys(re.findall(r'[?&](?:page|cursor|offset|limit)=[^"&\\\s]*', h)))[:10],
              "api": list(dict.fromkeys(re.findall(r'["\'](/api/[^"\'\s\\]+|https://[a-z0-9.-]*api[a-z0-9.-]*/[^"\'\s\\]*)', h)))[:20],
              "totals": list(dict.fromkeys(re.findall(r'"(?:total|totalCount|count|hasMore|nextCursor|totalPages)\\?"\s*:\s*\\?"?[^,}\\"]+', h)))[:10],
              "head": h[:300] if "robots" in u else ""}
json.dump(out, open("probe/domer6.json", "w"), indent=1, ensure_ascii=False)
