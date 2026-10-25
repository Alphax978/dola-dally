#!/usr/bin/env python3
"""repost.py: post a finished video (e.g. a corrected breakdown) for one day's slot again, to chosen platforms.

  python3 repost.py DAY SLOT VIDEO_URL youtube,facebook,instagram,tiktok
The results are kept in posted.json under that slot's "repost" (the original posts stay recorded as they were).
"""
import os
import sys
import time
import tempfile
import urllib.request

import post_to_x as p
from cross_post import youtube, facebook, instagram, tiktok_post

day, slot, url, names = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4].split(",")
job = p.load_job(day, slot)
t = p.cross_texts(job)
t["key"] = f"{day}-{slot}-r{time.strftime('%H%M%S')}"  # a new ID every time, so Zapier treats it as a new video
h = p.creator_handle(job["meta"])
t["credit"] = f"🎬 Original by @{h} on X: {job['meta'].get('x_post')}" if h else ""
with tempfile.TemporaryDirectory() as tmp:
    video = os.path.join(tmp, "video.mp4")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": p.UA}), timeout=300) as r, \
            open(video, "wb") as f:
        f.write(r.read())
    results = {}
    for name in names:
        try:
            if name == "youtube":
                res = youtube(video, t)
            elif name == "facebook":
                res = facebook(video, t)
            elif name == "instagram":
                res = instagram(video, t, url, prefer_link=True)
            elif name == "tiktok":
                res = tiktok_post(video, t)
            else:
                continue
            results[name] = res
            msg = f"{name}: reposted {res.get('url', '')}{res.get('note', '')}"
        except Exception as e:
            results[name] = {"error": str(e)[:400]}
            msg = f"{name}: FAILED {str(e)[:400]}"
        print(msg, flush=True)
        print(f"::notice title=Repost::{msg[:600]}", flush=True)
key = f"{day}-{slot}"
posted = p.load_posted()
entry = posted.get(key) or {}
entry["repost"] = {**(entry.get("repost") or {}), **results}
p.save_posted(key, entry)
p.commit_posted(f"Reposted {key}")
