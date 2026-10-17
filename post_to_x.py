#!/usr/bin/env python3
"""
post_to_x.py: posts the day's original YouMind video to X, credited to its creator,
with our replica prompt as a reply. Runs on GitHub Actions (see .github/workflows/post_x.yml).

  python3 post_to_x.py --slot 1              post video 1 of today (if not posted yet)
  python3 post_to_x.py --slot 2 --wait-until 13:30   wait until 1:30 PM Nepal time, then post video 2
  python3 post_to_x.py --slot 1 --dry-run    do everything except talking to X

Reads prompts/x/<date>-<slot>.json (written by the morning Claude routine) and
days/<date>/<slug>/meta.json (written by prepare_frames.py). Records what it posted
in posted.json so nothing is posted twice.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET   (OAuth 1.0a, from developer.x.com)
Each video gets exactly two posts: the video (hook, credit, "Prompt: ⤵️") and one reply with the
full prompt. Without X Premium a long reply is refused, so it falls back to a short prompt.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TZ = dt.timezone(dt.timedelta(hours=5, minutes=45))  # Nepal
API = "https://api.x.com/2"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
CHUNK = 4 * 1024 * 1024


def log(msg):
    print(f"[{dt.datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


def today():
    return dt.datetime.now(TZ).date().isoformat()


# ---------- what to post ----------

def load_job(day, slot):
    path = os.path.join(ROOT, "prompts", "x", f"{day}-{slot}.json")
    if not os.path.exists(path):
        return None
    job = json.load(open(path, encoding="utf-8"))
    meta_path = os.path.join(ROOT, "days", day, job["slug"], "meta.json")
    job["meta"] = json.load(open(meta_path, encoding="utf-8"))
    return job


def creator_handle(meta):
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/", meta.get("x_post") or "")
    return m.group(1) if m else None


def x_len(text):
    """X counts every character as 1, except most emoji/CJK as 2; be conservative."""
    return sum(2 if ord(c) > 0x2FFF else 1 for c in text)


def main_text(job):
    handle = creator_handle(job["meta"])
    credit = f"Original by @{handle}" if handle else "Original from the YouMind Seedance 2.5 gallery"
    tail = f"\n\n🎬 {credit}\n\nPrompt: ⤵️"
    caption = re.sub(r"https?://\S+", "", job.get("caption", "")).strip()  # links cost extra on X
    while caption and x_len(caption + tail) > 280:
        caption = caption[: max(0, len(caption) - 10)].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"
    return (caption + tail).strip()


def public_prompt(text):
    """The prompt as people should see it: without our Dola-only first line."""
    lines = text.strip().splitlines()
    if lines and lines[0].strip().lower().startswith("use seedance"):
        lines = lines[1:]
    text = "\n".join(lines).strip()
    return re.sub(r"^(VIDEO PROMPT)\s*—\s*(?:SINGLE|FULL 30s|PART \d of \d)\s*—", r"\1 —", text)


def reply_texts(job):
    """One reply: the full prompt (needs X Premium for long posts), and a short fallback."""
    full = public_prompt(job["prompt"])[:24000]  # long-post limit is 25,000
    short = public_prompt(job.get("prompt_short") or job["prompt"])
    while x_len(short) > 280:
        short = short[: len(short) - 10].rsplit(" ", 1)[0] + "…"
    return full, short


# ---------- video ----------

def get_video(meta, workdir):
    raw = os.path.join(workdir, "original.mp4")
    req = urllib.request.Request(meta["video_url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(raw, "wb") as f:
        f.write(r.read())
    out = os.path.join(workdir, "post.mp4")
    # X-safe: H.264 + AAC, at most 1280 px on the long side, even dimensions, faststart.
    vf = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))',setsar=1,format=yuv420p"
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                "stream=index", "-of", "csv=p=0", raw], capture_output=True, text=True).stdout.strip()
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", raw]
    if not has_audio:  # X plays silent clips fine, but some players choke on no audio track
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest"]
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    return out


# ---------- X API (OAuth 1.0a user context) ----------

def session():
    from requests_oauthlib import OAuth1Session
    keys = [os.environ.get(k, "").strip() for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(keys):
        sys.exit("X keys missing: add X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET as repo secrets.")
    return OAuth1Session(keys[0], client_secret=keys[1], resource_owner_key=keys[2], resource_owner_secret=keys[3])


def check(r, what):
    if r.status_code >= 300:
        sys.exit(f"X API error during {what}: {r.status_code} {r.text[:500]}")
    return r.json() if r.content else {}


def upload_video(s, path):
    size = os.path.getsize(path)
    data = check(s.post(f"{API}/media/upload/initialize",
                        json={"media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}),
                 "upload initialize")
    media_id = data["data"]["id"]
    with open(path, "rb") as f:
        i = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            check(s.post(f"{API}/media/upload/{media_id}/append", data={"segment_index": str(i)},
                         files={"media": ("chunk", chunk, "application/octet-stream")}), f"upload chunk {i}")
            i += 1
    info = check(s.post(f"{API}/media/upload/{media_id}/finalize"), "upload finalize").get("data", {})
    for _ in range(60):  # up to ~10 minutes of processing
        state = (info.get("processing_info") or {}).get("state")
        if state in (None, "succeeded"):
            return media_id
        if state == "failed":
            sys.exit(f"X couldn't process the video: {info.get('processing_info')}")
        time.sleep(max(2, (info.get("processing_info") or {}).get("check_after_secs", 5)))
        info = check(s.get(f"{API}/media/upload", params={"command": "STATUS", "media_id": media_id}),
                     "upload status").get("data", {})
    sys.exit("X took too long to process the video.")


def post(s, text, media_id=None, reply_to=None):
    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    if reply_to:
        body["reply"] = {"in_reply_to_tweet_id": reply_to}
    return check(s.post(f"{API}/tweets", json=body), "post")["data"]["id"]


# ---------- bookkeeping ----------

def posted_path():
    return os.path.join(ROOT, "posted.json")


def load_posted():
    p = posted_path()
    return json.load(open(p)) if os.path.exists(p) else {}


def save_posted(key, info):
    d = load_posted()
    d[key] = info
    json.dump(dict(list(d.items())[-200:]), open(posted_path(), "w"), indent=1)


def wait_until(hhmm):
    h, m = map(int, hhmm.split(":"))
    now = dt.datetime.now(TZ)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target > now:
        secs = (target - now).total_seconds()
        if secs > 5.5 * 3600:  # GitHub jobs stop at 6 hours
            log(f"{hhmm} is too far away to wait for here; the evening schedule will post it.")
            sys.exit(0)
        log(f"Waiting until {hhmm} Nepal time ({secs / 60:.0f} min)...")
        time.sleep(secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, choices=[1, 2], required=True)
    ap.add_argument("--wait-until", help="HH:MM Nepal time to wait for before posting")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--day", default=None, help="YYYY-MM-DD (default: today in Nepal)")
    a = ap.parse_args()

    day = a.day or today()
    key = f"{day}-{a.slot}"
    if key in load_posted():
        log(f"Video {a.slot} for {day} is already posted; nothing to do.")
        return
    job = load_job(day, a.slot)
    if not job:
        log(f"No prompts/x/{key}.json yet; nothing to post.")
        return
    if a.wait_until and not a.dry_run:
        wait_until(a.wait_until)
        if key in load_posted():
            return

    text = main_text(job)
    full, short = reply_texts(job)
    log(f"Main post ({x_len(text)} chars):\n{text}")
    log(f"Reply: full prompt {x_len(full)} chars (short fallback {x_len(short)} chars):\n{full[:300]}...")

    with tempfile.TemporaryDirectory() as tmp:
        video = get_video(job["meta"], tmp)
        log(f"Video ready: {os.path.getsize(video) // 1024} KB")
        if a.dry_run:
            log("Dry run: not posting.")
            return
        s = session()
        media_id = upload_video(s, video)
    first = post(s, text, media_id=media_id)
    log(f"Posted: https://x.com/i/status/{first}")
    time.sleep(2)
    r = s.post(f"{API}/tweets", json={"text": full, "reply": {"in_reply_to_tweet_id": first}})
    if r.status_code >= 300 and x_len(full) > 280:
        # Long posts need X Premium; fall back to the short prompt in the same single reply.
        log(f"Full prompt was refused ({r.status_code}: {r.text[:200]}); posting the short version.")
        r = s.post(f"{API}/tweets", json={"text": short, "reply": {"in_reply_to_tweet_id": first}})
    reply_id = check(r, "prompt reply")["data"]["id"]
    save_posted(key, {"post_id": first, "reply_id": reply_id, "slug": job["slug"],
                      "posted_at": dt.datetime.now(TZ).isoformat()})
    log("Done: video post + prompt reply.")


if __name__ == "__main__":
    main()
