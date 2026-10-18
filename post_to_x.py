#!/usr/bin/env python3
"""
post_to_x.py: posts the day's original YouMind video to X (credit to the creator is added by hand in a comment),
with our replica prompt as a reply. Runs on GitHub Actions (see .github/workflows/post_x.yml).

  python3 post_to_x.py --slot 1              post video 1 of today (if not posted yet)
  python3 post_to_x.py --slot 2 --wait-until 13:30   wait until 1:30 PM Nepal time, then post video 2
  python3 post_to_x.py --slot 1 --dry-run    do everything except talking to X

Reads prompts/x/<date>-<slot>.json (written by the morning Claude routine) and
days/<date>/<slug>/meta.json (written by prepare_frames.py). Records what it posted
in posted.json so nothing is posted twice.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET   (OAuth 1.0a, from developer.x.com)
Each video gets exactly two posts: the video (hook, "Prompt: ⤵️") and one reply with the
full prompt. Without X Premium a long reply is refused, so it falls back to a short prompt.
Right after X, the same video goes to YouTube, the Facebook Page and Instagram (cross_post.py).
Running --slot N for a video already on X only fills in platforms that are missing or failed.
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
    tail = f"\n\nPrompt: ⤵️"
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


SLOTS = {1: "16:30", 2: "21:30"}  # Nepal time: Europe's afternoon, then US late morning


def mark_used(url):
    """Add a posted video to used.json so it's never picked again."""
    p = os.path.join(ROOT, "used.json")
    used = json.load(open(p)) if os.path.exists(p) else []
    if url and url not in used:
        used.append(url)
        json.dump(used[-2000:], open(p, "w"), indent=1)


def commit_posted(msg="Posted to X"):
    """Save posted.json to the repo right away, so nothing can be posted twice."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    run = lambda *c: subprocess.run(["git", *c], cwd=ROOT, capture_output=True, text=True)
    run("config", "user.name", "dola-daily bot")
    run("config", "user.email", "dola-daily@users.noreply.github.com")
    run("add", "posted.json", "used.json")
    if os.path.exists(os.path.join(ROOT, "docs", "tiktok", "captions.json")):
        run("add", "docs/tiktok/captions.json")
    if run("diff", "--cached", "--quiet").returncode == 0:
        return
    run("commit", "-m", msg)
    for _ in range(3):
        run("pull", "--rebase", "-q")
        if run("push", "-q").returncode == 0:
            return
        time.sleep(5)
    log("Warning: couldn't push posted.json")


def cross_texts(job):
    from cross_post import texts
    return texts(job.get("caption", ""), "",  # no credit in captions: credits are added by hand in comments
                 public_prompt(job["prompt"]), public_prompt(job.get("prompt_short") or job["prompt"]))


def needs_cross(entry):
    from cross_post import enabled
    other = entry.get("other") or {}
    return [n for n in enabled() if not (isinstance(other.get(n), dict) and other[n].get("id"))]


def cross_post(key, job, video, entry):
    """Post the same video to YouTube, Facebook and Instagram; never stops the X flow."""
    from cross_post import post_all, vertical
    try:
        try:
            tall = vertical(video, os.path.dirname(video))  # 9:16 with black bars, unless it already is 9:16
            log(f"[{key}] " + ("Made a 9:16 version (black bars) for YouTube/Facebook/Instagram" if tall != video
                               else "Already 9:16: posting it as is"))
        except Exception as e:  # never lose the post over the reframe
            log(f"[{key}] Couldn't make the 9:16 version ({e}); posting the original shape")
            tall = video
        texts = cross_texts(job)
        texts["key"] = key
        h = creator_handle(job["meta"])  # for the credit comments you post by hand
        texts["credit"] = (f"🎬 Original by @{h} on X: {job['meta'].get('x_post')}" if h
                           else "🎬 Original from the YouMind Seedance 2.5 gallery")
        log(f"[{key}] Credit for your comments: {texts['credit']}")
        entry["other"] = post_all(tall, texts, entry.get("other"), job["meta"].get("video_url"),
                                  log=lambda m: log(f"[{key}] {m}"))
    except Exception as e:
        log(f"[{key}] Cross-posting failed: {e}")
        return
    save_posted(key, entry)
    commit_posted("Posted to YouTube/Facebook/Instagram")


def post_slot(day, slot, dry_run=False, retry_cross=False):
    """Post one video + its prompt reply on X, then on YouTube/Facebook/Instagram.
    Returns 'posted', 'done-before', 'no-job', 'watermark' or 'dry'."""
    key = f"{day}-{slot}"
    entry = load_posted().get(key)
    if entry and not (retry_cross and entry.get("post_id") and needs_cross(entry)):
        return "done-before"
    job = load_job(day, slot)
    if not job:
        return "no-job"

    with tempfile.TemporaryDirectory() as tmp:
        video = get_video(job["meta"], tmp)
        if entry:  # already on X: only fill in the platforms that are missing or failed
            log(f"[{key}] Already on X; posting to: {', '.join(needs_cross(entry))}")
            if not dry_run:
                cross_post(key, job, video, entry)
            return "done-before"

        text = main_text(job)
        full, short = reply_texts(job)
        log(f"[{key}] Main post ({x_len(text)} chars):\n{text}")
        log(f"[{key}] Reply: full prompt {x_len(full)} chars (short fallback {x_len(short)} chars):\n{full[:300]}...")
        from wm_detect import has_watermark  # last check: never post a watermarked video
        wm, info = has_watermark(os.path.join(tmp, "original.mp4"))
        if wm:
            log(f"[{key}] NOT POSTED: the video has a watermark ({info}).")
            if not dry_run:
                save_posted(key, {"skipped": "watermark", "slug": job["slug"], "details": str(info)})
                mark_used(job["meta"].get("url"))
                commit_posted("Skipped a watermarked video")
            return "watermark"
        log(f"[{key}] Video ready: {os.path.getsize(video) // 1024} KB")
        if dry_run:
            t = cross_texts(job)
            log(f"[{key}] YouTube title: {t['title']}")
            log(f"[{key}] Instagram caption ({len(t['instagram'])} chars):\n{t['instagram'][:600]}...")
            log(f"[{key}] Dry run: not posting.")
            return "dry"
        s = session()
        media_id = upload_video(s, video)
        first = post(s, text, media_id=media_id)
        # record right away: even if the reply fails, the video must never be posted twice
        entry = {"post_id": first, "slug": job["slug"], "posted_at": dt.datetime.now(TZ).isoformat()}
        save_posted(key, entry)
        mark_used(job["meta"].get("url"))
        commit_posted()
        log(f"[{key}] Posted: https://x.com/i/status/{first}")
        time.sleep(2)
        r = s.post(f"{API}/tweets", json={"text": full, "reply": {"in_reply_to_tweet_id": first}})
        if r.status_code >= 300 and x_len(full) > 280:
            # Long posts need X Premium; fall back to the short prompt in the same single reply.
            log(f"[{key}] Full prompt was refused ({r.status_code}: {r.text[:200]}); posting the short version.")
            r = s.post(f"{API}/tweets", json={"text": short, "reply": {"in_reply_to_tweet_id": first}})
        if r.status_code < 300:
            entry["reply_id"] = r.json()["data"]["id"]
            save_posted(key, entry)
            commit_posted()
            log(f"[{key}] Done on X: video post + prompt reply.")
        else:
            log(f"[{key}] X prompt reply failed: {r.status_code} {r.text[:300]}")
        cross_post(key, job, video, entry)
    return "posted"


def due_time(day, slot):
    h, m = map(int, SLOTS[slot].split(":"))
    return dt.datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=TZ)


def auto(dry_run=False):
    """Post every video of today whose time has come and isn't posted yet, then stop.

    GitHub's schedule starts this at 16:30 and 21:30 Nepal time (often a bit late), with backups after.
    A run that starts up to 10 minutes early waits for the exact time.
    """
    day = today()
    if dry_run:
        from cross_post import check_accounts
        check_accounts(log=log)
        for slot in SLOTS:
            log(f"[{day}-{slot}] {post_slot(day, slot, dry_run=True)}")
        return
    posted = load_posted()
    for slot in SLOTS:
        if f"{day}-{slot}" in posted:
            continue
        if not load_job(day, slot):
            log(f"[{day}-{slot}] no prompts saved for this video yet")
            continue
        wait = (due_time(day, slot) - dt.datetime.now(TZ)).total_seconds()
        if wait > 600:
            log(f"[{day}-{slot}] not due until {SLOTS[slot]} Nepal time")
            continue
        if wait > 0:
            log(f"[{day}-{slot}] waiting {wait / 60:.0f} min for {SLOTS[slot]}")
            time.sleep(wait)
        log(f"[{day}-{slot}] {post_slot(day, slot)}")
    log("Done.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true", help="post today's videos at their set times")
    ap.add_argument("--slot", type=int, choices=sorted(SLOTS), help="post this video now")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--day", default=None, help="YYYY-MM-DD (default: today in Nepal)")
    a = ap.parse_args()
    if a.auto:
        auto(a.dry_run)
    elif a.slot:
        result = post_slot(a.day or today(), a.slot, a.dry_run, retry_cross=True)
        log(result)
        if result == "watermark":
            sys.exit(1)
    else:
        ap.error("use --auto or --slot N")


if __name__ == "__main__":
    main()
