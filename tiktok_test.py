#!/usr/bin/env python3
"""tiktok_test.py: send one of today's videos to TikTok, to test a mode.

  python3 tiktok_test.py [slot] [mode]   slot 1 or 2 (default 1; falls back to the newest saved video)
                                         mode: direct (default; private until TikTok audits the app) or buffer
"""
import glob, json, os, sys, tempfile

os.environ["TIKTOK_MODE"] = sys.argv[2] if len(sys.argv) > 2 else "direct"
import post_to_x as p
import cross_post
import tiktok

slot = int(sys.argv[1]) if len(sys.argv) > 1 else 1
day = p.today()
job = p.load_job(day, slot)
if not job:  # no prompts today yet: use the newest saved one
    files = sorted(glob.glob(os.path.join(p.ROOT, "prompts", "x", "*.json")))
    if not files:
        sys.exit("No saved videos to test with yet.")
    name = os.path.basename(files[-1])[:-5]
    day, slot = name[:10], int(name[11:])
    job = p.load_job(day, slot)
print(f"Testing with {day} video {slot}: {job['meta']['title']}")
with tempfile.TemporaryDirectory() as tmp:
    p.get_video(job["meta"], tmp)
    video = cross_post.vertical(os.path.join(tmp, "original.mp4"), tmp)
    t = p.cross_texts(job)
    t["key"] = f"test-{day}-{slot}-{os.environ['TIKTOK_MODE']}"
    if tiktok.mode() == "buffer":
        import buffer_feed
        res = buffer_feed.publish(video, t["instagram"], t["key"], t["title"])
    else:
        print("Posting as", tiktok.who(tiktok.access_token()))
        res = tiktok.post(video, t["instagram"])
print(json.dumps(res, indent=1))
print("Done." + (" Zapier should pick it up from the feed within ~15 min." if tiktok.mode() == "buffer" else " Open TikTok > Profile to see it."))
