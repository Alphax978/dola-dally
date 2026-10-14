#!/usr/bin/env python3
"""
write_prompts.py: runs on GitHub Actions right after prepare_frames.py.

Takes today's first prepared video (frame grids + text strips + meta.json), adds the
creator's prompt from its YouMind page, and asks Claude (Anthropic API) to write
replica prompts. Saves:
  days/<date>/prompts.json   machine-readable, read by the laptop script
  days/<date>/prompts.md     the same, easy to read

Needs the ANTHROPIC_API_KEY secret. Without it, this step is skipped (exit 0).
"""
import base64
import datetime as dt
import glob
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
TZ = dt.timezone(dt.timedelta(hours=5, minutes=45))  # Nepal
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"

RULES = """You recreate short AI videos so they can be regenerated in Dola AI (ByteDance Seedance 2.5).
You are given timestamped frame grids of the original video (one frame every 0.5 s, each stamped
with its time), bottom-of-frame strips (one per second, showing any subtitles), metadata with the
scene-cut times, and the text of the original creator's page.

GOAL: a faithful replica. Keep the characters, setting, story, shots, timing, camera moves, look,
sound and payoff as close to the original as possible. Fill in what the original leaves vague
(camera moves, framing, light, sound) so the result is precise and works on the first try.
Describe characters from what you actually see in the frames. Where frames and the creator's text
disagree, follow the frames.
ONLY EXCEPTION: if the original features copyrighted or franchise characters, or real
people/celebrities, replace each with an original character in the same role (new face, hair,
build, costume, colors, emblems, name) and keep everything else identical; never mention them.
Leave out burned-in subtitles and on-screen text; keep spoken lines as dialogue instead.

LENGTH RULES (Dola usually allows 15 s per clip, sometimes 30 s):
- Original 15 s or shorter: one prompt ("single").
- Original longer than 15 s (up to 30 s): write BOTH
  - "full_30s": one prompt for the whole video (its real length, max 30.0 s), timecodes from 00:00;
  - "part1" and "part2": the same video split at a real cut into two parts of 15.0 s or less each
    (trim a fraction of a second from the longest shot if needed), timecodes restarting at 00:00,
    each repeating the full style block and full character block word for word.
  All three must describe the same characters, look, shots and sound, worded identically where possible.

EVERY PROMPT uses exactly this format:
use seedance 2.5 for this

VIDEO PROMPT — <SINGLE | FULL 30s | PART 1 of 2 | PART 2 of 2> — N seconds, <aspect ratio>, <look: realism/style, lens, color grade, light>, <camera feel>, <pacing>.

CHARACTERS
<NAME>: <age, skin, hair, face, clothing, one or two signature details visible in every shot>
(LOCATION: ... if relevant)

SHOT 1 (00:00.0-00:01.5) — <title>. <what happens, framing, camera move (push-in, dolly, tracking,
crane, whip pan, locked-off, low angle...), speed, physical cause and effect>
...

SOUND: <named sounds; "upbeat instrumental beat" or similar instead of any real song; "no music"
when there is none; short spoken lines in double quotes in the original's language>

Also write an X caption: under 280 characters, at most 2 hashtags, mentioning Dola AI.

Reply with ONLY a JSON object, no other text:
{"title": "<short title>", "duration": <seconds>, "aspect_ratio": "<e.g. 16:9>",
 "characters_swapped": <true|false>,
 "single": "<prompt or null>", "full_30s": "<prompt or null>",
 "part1": "<prompt or null>", "part2": "<prompt or null>",
 "caption": "<X caption>"}"""


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def page_text(url, limit=8000):
    """The YouMind page as plain text (contains the creator's prompt)."""
    try:
        raw = get(url)
    except Exception as e:
        return f"(could not load the page: {e})"
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def image_block(path):
    data = base64.standard_b64encode(open(path, "rb").read()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def ask_claude(key, content, max_tokens=12000):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": RULES,
        "messages": [{"role": "user", "content": content}],
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Anthropic API error {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    usage = resp.get("usage", {})
    print(f"Claude used {usage.get('input_tokens')} input + {usage.get('output_tokens')} output tokens")
    return text


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def check(p):
    """Make sure the reply has the prompts the laptop script needs."""
    if p.get("single"):
        return
    for k in ("full_30s", "part1", "part2"):
        if not p.get(k):
            raise ValueError(f"missing '{k}' for a video longer than 15 s")


def to_markdown(p, meta):
    out = [f"# {p.get('title') or meta.get('title')}", "",
           f"Original: {meta.get('url')} · {meta.get('x_post') or ''}",
           f"{p.get('duration')} s · {p.get('aspect_ratio')}"
           + (" · characters swapped for originals" if p.get("characters_swapped") else ""), ""]
    blocks = [("Prompt", "single"), ("Option A — one 30s clip", "full_30s"),
              ("Option B — Part 1", "part1"), ("Option B — Part 2", "part2")]
    for label, key in blocks:
        if p.get(key):
            out += [f"## {label}", "", "```", p[key].strip(), "```", ""]
    out += ["## X post", "", p.get("caption", "")]
    return "\n".join(out)


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ANTHROPIC_API_KEY not set; skipping prompt writing.")
        return
    today = os.environ.get("DAY") or dt.datetime.now(TZ).date().isoformat()
    root = os.path.dirname(os.path.abspath(__file__))
    day_dir = os.path.join(root, "days", today)
    index_path = os.path.join(day_dir, "index.json")
    if not os.path.exists(index_path):
        sys.exit(f"No frames for {today}; nothing to write.")
    videos = json.load(open(index_path)).get("videos", [])
    if not videos:
        sys.exit("index.json lists no videos.")

    last_error = None
    for v in videos:  # first video, then the backup if the first one fails
        vdir = os.path.join(root, v["dir"])
        meta = json.load(open(os.path.join(vdir, "meta.json")))
        frames = sorted(glob.glob(os.path.join(vdir, "frames_*.jpg")))
        strips = sorted(glob.glob(os.path.join(vdir, "text_*.jpg")))
        content = [{"type": "text", "text": "METADATA:\n" + json.dumps(meta, ensure_ascii=False, indent=1)}]
        content.append({"type": "text", "text": "FRAME GRIDS (time stamped top-left of each frame):"})
        content += [image_block(f) for f in frames]
        content.append({"type": "text", "text": "BOTTOM STRIPS (subtitles / on-screen text), one per second:"})
        content += [image_block(f) for f in strips]
        content.append({"type": "text", "text": "ORIGINAL CREATOR'S PAGE (text):\n" + page_text(meta["url"])})
        content.append({"type": "text", "text": "Write the prompts now. Reply with the JSON object only."})
        for attempt in range(2):
            try:
                p = parse_json(ask_claude(key, content))
                check(p)
                p.update(source_url=meta.get("url"), x_post=meta.get("x_post"), slug=v["slug"],
                         original_duration=meta.get("duration"), date=today, model=MODEL)
                json.dump(p, open(os.path.join(day_dir, "prompts.json"), "w"), indent=2, ensure_ascii=False)
                open(os.path.join(day_dir, "prompts.md"), "w").write(to_markdown(p, meta))
                print(f"Prompts written for: {p.get('title')} ({v['slug']})")
                return
            except Exception as e:
                last_error = e
                print(f"  attempt {attempt + 1} for {v['slug']} failed: {e}")
    sys.exit(f"Couldn't write prompts: {last_error}")


if __name__ == "__main__":
    main()
