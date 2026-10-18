#!/usr/bin/env python3
"""tiktok_test.py: post one of today's videos to TikTok in DIRECT mode (for testing and the app-review demo).
Until TikTok audits the app, the post is private (only you can see it).

  python3 tiktok_test.py [slot]     slot 1 or 2 of today (default 1); falls back to the newest saved video
"""
import glob, json, os, sys, tempfile

os.environ["TIKTOK_MODE"] = "direct"
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
    video = cross_post.vertical(p.get_video(job["meta"], tmp), tmp)
    caption = p.cross_texts(job)["instagram"]
    print("Posting as", tiktok.who(tiktok.access_token()))
    res = tiktok.post(video, caption)
print(json.dumps(res, indent=1))
print("Done. Open TikTok > Profile to see it.")
