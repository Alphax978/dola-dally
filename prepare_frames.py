#!/usr/bin/env python3
"""
prepare_frames.py: runs on GitHub Actions every morning.

Picks random videos from the YouMind Seedance 2.5 gallery, downloads them, and saves
timestamped frame grids so Claude can study each video shot by shot without a browser.

Output (committed to the repo):
  days/<YYYY-MM-DD>/index.json            list of the videos prepared today
  days/<YYYY-MM-DD>/<slug>/meta.json      title, links, duration, size, cut times
  days/<YYYY-MM-DD>/<slug>/frames_N.jpg   frame grids, one frame every 0.5s, timestamped
  days/<YYYY-MM-DD>/<slug>/text_N.jpg     bottom-of-frame strips, every 1s, for subtitles/text
  used.json                               every video already prepared, so none repeats
"""
import datetime as dt
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

GALLERY = "https://youmind.com/seedance-2-5-prompts/explore"
HOW_MANY = 2          # one for today plus one backup in case the first has to be skipped
KEEP_DAYS = 7         # delete older days to keep the repo small
MAX_SECONDS = 31      # Dola makes 15s clips and allows 3 Pro generations a day: 2 parts max
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
TZ = dt.timezone(dt.timedelta(hours=5, minutes=45))  # Nepal


def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


GENERIC = {"seedance", "prompt", "prompts", "video", "ai", "2", "5", "20", "25"}


def words(s):
    return set(w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 1 and w not in GENERIC)


def gallery_items():
    page = get(GALLERY)
    links = re.findall(r'https?://youmind\.com/video-prompts/[a-z0-9-]+|/video-prompts/[a-z0-9-]+', page)
    out = []
    for l in links:
        u = l if l.startswith("http") else "https://youmind.com" + l
        if u not in out:
            out.append(u)
    return out


def page_text(page, limit=15000):
    """Readable text of a YouMind page (holds the creator's prompt), for Claude to read later.

    Visible text first, then any long text found in the page's embedded data, in case the
    prompt is only rendered by JavaScript.
    """
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    visible = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()
    extra = []

    def collect(t, depth=0):
        t = t.strip()
        if depth < 4 and t[:1] in "{[":
            try:
                v = json.loads(t)
            except Exception:
                v = None
            if v is not None:
                stack = [v]
                while stack:
                    o = stack.pop()
                    if isinstance(o, dict):
                        stack.extend(o.values())
                    elif isinstance(o, list):
                        stack.extend(o)
                    elif isinstance(o, str) and len(o) >= 150:
                        collect(o, depth + 1)
                return
        if (len(t) >= 150 and " " in t and not t.startswith(("http", "data:"))
                and t not in visible and t not in extra):
            extra.append(t)

    for m in re.finditer(r'"((?:[^"\\]|\\.){150,})"', page):
        try:
            collect(json.loads('"' + m.group(1) + '"'))
        except Exception:
            continue
    out = "VISIBLE PAGE TEXT:\n" + visible
    if extra:
        out += "\n\nLONGER TEXT FROM THE PAGE DATA:\n" + "\n\n".join(extra)
    return out[:limit]


def item_details(url):
    page = get(url)
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    title = html.unescape(title.group(1)).split(" - ")[0].split(" | ")[0].strip() if title else ""
    media = set(re.findall(r'https://cms-assets\.youmind\.com/media/[A-Za-z0-9._%\-]+', page))
    media = [m for m in media if not re.search(r"\.(jpg|jpeg|png|webp|gif|svg)$", m, re.I)]
    # The page's own video file is named after the page title; related videos are named after theirs.
    tw = words(title)
    best, score = None, -1
    for m in media:
        name = urllib.parse.unquote(m.rsplit("/", 1)[-1])
        name = re.sub(r"^\d+_[a-z0-9]+_", "", name)
        s = len(tw & words(name))
        if s > score:
            best, score = m, s
    x = re.search(r'https://(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+', page)
    return {
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "title": title,
        "video_url": best if score > 0 else None,
        "x_post": x.group(0) if x else None,
        "page_text": page_text(page),
    }


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    o = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", path]).stdout
    j = json.loads(o)
    s = j["streams"][0]
    return float(j["format"]["duration"]), s["width"], s["height"]


def cut_times(path):
    o = run(["ffmpeg", "-i", path, "-vf", "select='gt(scene,0.25)',showinfo", "-an", "-f", "null", "-"]).stderr
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", o)]


def frame_grids(path, out_dir, dur, w, h):
    """One frame every 0.5s, 6 per row, 30 per image, each stamped with its time."""
    tile_w = 400
    stamp = "drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.65"
    per_img = 30
    n = int(dur * 2) + 1
    files = []
    for k in range((n + per_img - 1) // per_img):
        start = k * per_img / 2
        f = os.path.join(out_dir, f"frames_{k + 1}.jpg")
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-i", path, "-vf",
             f"fps=2,setpts=PTS+{start}/TB,scale={tile_w}:-2,{stamp},tile=6x5", "-frames:v", "1",
             "-q:v", "4", f])
        if os.path.exists(f):
            files.append(os.path.basename(f))
    return files


def text_strips(path, out_dir, dur, w, h):
    """Bottom 22% of the frame, every 1s, large enough to read subtitles and on-screen text."""
    stamp = "drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.65"
    per_img = 16
    n = int(dur) + 1
    files = []
    for k in range((n + per_img - 1) // per_img):
        start = k * per_img
        f = os.path.join(out_dir, f"text_{k + 1}.jpg")
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-i", path, "-vf",
             f"fps=1,setpts=PTS+{start}/TB,crop=iw:ih*0.22:0:ih*0.78,scale=800:-2,{stamp},tile=2x8",
             "-frames:v", "1", "-q:v", "4", f])
        if os.path.exists(f):
            files.append(os.path.basename(f))
    return files


def main():
    today = dt.datetime.now(TZ).date().isoformat()
    root = os.path.dirname(os.path.abspath(__file__))
    day_dir = os.path.join(root, "days", today)
    used_path = os.path.join(root, "used.json")
    used = json.load(open(used_path)) if os.path.exists(used_path) else []

    items = gallery_items()
    print(f"Gallery: {len(items)} videos")
    if not items:
        sys.exit("Couldn't read the YouMind gallery (no video links found).")
    fresh = [u for u in items if u not in used] or items
    random.shuffle(fresh)

    index_path = os.path.join(day_dir, "index.json")
    if os.path.exists(index_path) and json.load(open(index_path)).get("videos"):
        # Already done today (e.g. the schedule ran late after the routine started a run itself).
        print(f"Frames for {today} already exist; nothing to do.")
        return

    os.makedirs(day_dir, exist_ok=True)
    prepared = []
    for url in fresh:
        if len(prepared) >= HOW_MANY:
            break
        try:
            d = item_details(url)
            if not d["video_url"]:
                print(f"  skip (no video file found): {url}")
                continue
            out_dir = os.path.join(day_dir, d["slug"])
            os.makedirs(out_dir, exist_ok=True)
            vid = os.path.join(out_dir, "video.mp4")
            with open(vid, "wb") as f:
                f.write(get(d["video_url"], binary=True, timeout=180))
            dur, w, h = probe(vid)
            if dur > MAX_SECONDS:
                os.remove(vid)
                os.rmdir(out_dir)
                used.append(url)  # too long for 2 Dola parts; never pick it again
                print(f"  skip (too long, {dur:.0f}s): {d['title']}")
                continue
            d.update(duration=round(dur, 2), width=w, height=h, cuts=cut_times(vid),
                     frame_grids=frame_grids(vid, out_dir, dur, w, h),
                     text_strips=text_strips(vid, out_dir, dur, w, h))
            os.remove(vid)  # keep only the images in the repo
            with open(os.path.join(out_dir, "creator_page.txt"), "w", encoding="utf-8") as f:
                f.write(d.pop("page_text"))
            json.dump(d, open(os.path.join(out_dir, "meta.json"), "w"), indent=2, ensure_ascii=False)
            prepared.append({"slug": d["slug"], "title": d["title"], "url": url,
                             "duration": d["duration"], "dir": f"days/{today}/{d['slug']}"})
            used.append(url)
            print(f"  ok: {d['title']} ({d['duration']}s, {len(d['cuts'])} cuts)")
        except Exception as e:  # one bad video shouldn't stop the run
            print(f"  failed: {url}: {e}")

    json.dump({"date": today, "videos": prepared}, open(os.path.join(day_dir, "index.json"), "w"),
              indent=2, ensure_ascii=False)
    json.dump(used[-500:], open(used_path, "w"), indent=1)

    # tidy up old days
    days = os.path.join(root, "days")
    cutoff = (dt.datetime.now(TZ).date() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for name in os.listdir(days):
        if name < cutoff:
            shutil.rmtree(os.path.join(days, name), ignore_errors=True)

    print(f"Prepared {len(prepared)} video(s) for {today}")
    if not prepared:
        sys.exit(1)


if __name__ == "__main__":
    main()
