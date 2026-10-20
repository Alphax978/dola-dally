import json, sys, os, tempfile
sys.path.insert(0, ".")
import prepare_frames as pf, models
from wm_detect import has_watermark
out = []
for url in pf.read_picks("picks.txt"):
    r = {"url": url}
    try:
        d = pf.details_for(url)(url)
        r.update(title=d["title"], video=d["video_url"], x_post=d["x_post"], model=models.detect(d, d["page_text"]))
        if d["video_url"]:
            p = os.path.join(tempfile.mkdtemp(), "v.mp4")
            open(p, "wb").write(pf.get(d["video_url"], binary=True, timeout=180))
            dur, w, h = pf.probe(p)
            wm, info = has_watermark(p)
            r.update(duration=dur, size=f"{w}x{h}", watermark=bool(wm), wm_info=str(info)[:200])
        r["used_before"] = url in json.load(open("used.json")) or (d["x_post"] in json.load(open("used.json")))
    except Exception as e:
        r["error"] = str(e)[:300]
    out.append(r)
json.dump(out, open("probe/picks_check.json", "w"), indent=1, ensure_ascii=False)
