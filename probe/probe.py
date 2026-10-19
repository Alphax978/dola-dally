import json, random, prepare_frames as p
out = {"max_id": p.reelcine_max_id(), "entries": []}
for n in random.sample(range(1, out["max_id"] + 1), 5):
    try:
        d = p.reelcine_details(f"https://reelcine.org/video-prompt/{n}")
        size = len(p.get(d["video_url"], binary=True, timeout=120)) if d["video_url"] else 0
        out["entries"].append({k: v for k, v in d.items() if k != "page_text"} | {"mp4_bytes": size, "text_chars": len(d["page_text"])})
    except Exception as e:
        out["entries"].append({"n": n, "error": str(e)[:200]})
json.dump(out, open("probe/reelcine_live.json", "w"), indent=1)
