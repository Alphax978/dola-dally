import json, re, urllib.request, gzip
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
def get(u):
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return r.status, r.geturl(), b.decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:120], u, ""
out = {}
s, u, robots = get("https://youmind.com/robots.txt"); out["robots"] = robots[:3000]
maps = re.findall(r"(?i)sitemap:\s*(\S+)", robots) or ["https://youmind.com/sitemap.xml"]
seen, vids, queue = set(), set(), list(maps)
while queue and len(seen) < 60:
    m = queue.pop(0)
    if m in seen: continue
    seen.add(m)
    s, u, x = get(m)
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
    v = [l for l in locs if "/video-prompts/" in l]
    vids |= set(v)
    out.setdefault("maps", []).append([m, s, len(locs), len(v)])
    queue += [l for l in locs if l.endswith(".xml") or "sitemap" in l.split("/")[-1]]
out["video_urls"] = len(vids)
out["video_sample"] = sorted(vids)[:5]
# by-id lookup
for test in ["https://youmind.com/video-prompts/x-12641", "https://youmind.com/video-prompts/12641"]:
    s, u, h = get(test)
    out["id " + test] = [s, u, re.search(r"<title>(.*?)</title>", h).group(1)[:80] if "<title>" in h else ""]
json.dump(out, open("probe/result4.json", "w"), indent=1)
json.dump(sorted(vids), open("probe/sitemap_videos.json", "w"))
print(json.dumps({k: v for k, v in out.items() if k != "robots"}, indent=1)[:3000])
