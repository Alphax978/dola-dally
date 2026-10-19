import json, random, sys, time, urllib.request
sys.path.insert(0, ".")
import prepare_frames as pf, models
out = {}
items = pf.domer_items(); out["count"] = len(items)
random.seed(7)
for u in random.sample(items, 5) + ["https://domer.io/prompts/seedance-7388"]:
    d = pf.domer_details(u); time.sleep(1)
    ok = None
    if d["video_url"]:
        req = urllib.request.Request(d["video_url"], method="HEAD", headers={"User-Agent": pf.UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            ok = [r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length")]
    out.setdefault("tests", []).append({k: d[k] for k in ("url", "slug", "title", "video_url", "x_post", "model")}
        | {"detected": models.detect(d, d["page_text"]), "head": ok, "text_start": d["page_text"][:400]})
json.dump(out, open("probe/domer5.json", "w"), indent=1, ensure_ascii=False)
