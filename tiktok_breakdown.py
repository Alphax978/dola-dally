#!/usr/bin/env python3
"""
tiktok_breakdown.py: turn a clip of any length into a 1-minute+ "prompt breakdown" video for TikTok, 9:16:

  1. hook       the most striking moment, with the hook in big text            (voiceover)
  2. original   the full clip, credited                                         (original sound + voice intro)
  3. breakdown  key moments replayed on top, the prompt words that made them below, key words in yellow (voiceover)
  4. outro      "full prompt in the caption, follow for more"                  (voiceover)

The script for steps 1-4 is breakdowns/<day>-<slot>.json, written each morning with the prompt (by the Claude
routine or Gemini). If it's missing or incomplete, parts are made automatically from the prompt's SHOT lines.
The finished video is always at least MIN_SECONDS long (more parts are added, then the outro is held), and
long scripts are trimmed toward MAX_SECONDS.

Voiceover: Kokoro, a free open-source voice that runs on the GitHub machine (espeak-ng if Kokoro can't load).

  python3 tiktok_breakdown.py DAY SLOT|SLUG OUT.mp4
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
BG, YEL, WHITE, GREY = (12, 12, 16), (255, 214, 10), (245, 245, 245), (165, 165, 175)
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
HANDLE = "@miraai.creates"
MIN_SECONDS = 62.0     # TikTok's Creator Rewards count videos over 1 minute
MAX_SECONDS = 88.0     # trim extra breakdown parts beyond this (never below 3 parts)
CLIP_TOP = 290         # breakdown screens: the replay box starts here...
TOP_BOX_H = 860        # ...and is at most this tall (tall 9:16 clips are fitted inside)
CENTER_BOX_H = 1240    # hook / original screens: the clip is at most this tall


def font(size, bold=True):
    return ImageFont.truetype(FONT_DIR + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)


def run(cmd, limit=600):
    """Run a tool; give up after `limit` seconds so a stuck tool can never freeze the posting run."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=limit)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")
    return r.stdout


def probe(path):
    j = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", path]))
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return float(j["format"]["duration"]), v["width"], v["height"], any(s["codec_type"] == "audio" for s in j["streams"])


def fit(w, h, box_w, box_h):
    """Size that fits (w, h) inside the box, even numbers."""
    s = min(box_w / w, box_h / h)
    return max(2, round(w * s / 2) * 2), max(2, round(h * s / 2) * 2)


# ---------- voice ----------

_kokoro = None
_noted = set()


def _note(msg):
    print(msg, flush=True)
    if os.environ.get("GITHUB_ACTIONS") and msg not in _noted:
        _noted.add(msg)
        print(f"::notice title=Breakdown::{msg}", flush=True)


NUM = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
      "seventeen eighteen nineteen twenty".split()


def spoken(text):
    """Make numbers and abbreviations read naturally (2.5 -> two point five, FPV -> F P V)."""
    word = lambda n: NUM[int(n)] if int(n) < len(NUM) else n
    text = re.sub(r"\b(\d{1,2})\.(\d)\b", lambda m: f"{word(m.group(1))} point {word(m.group(2))}", text)
    text = re.sub(r"\bFPV\b", "F P V", text)
    return re.sub(r"\b(\d{1,2})\b(?![:.]\d)", lambda m: word(m.group(1)), text)


def voices(lines, folder):
    """Speak every line in one go; returns {text: (wav path, seconds)}. Kokoro runs in its own process
    (VOICE_PY = the Python of its own environment, if set); any line it can't do gets the espeak-ng voice."""
    out, jobs = {}, []
    for i, text in enumerate(dict.fromkeys(t for t in lines if t)):
        jobs.append({"text": spoken(text), "out": os.path.join(folder, f"voice{i:02d}.wav"), "key": text})
    jf = os.path.join(folder, "voices.json")
    json.dump(jobs, open(jf, "w", encoding="utf-8"), ensure_ascii=False)
    py = os.environ.get("VOICE_PY") or sys.executable
    try:
        r = subprocess.run([py, os.path.join(ROOT, "voice.py"), jf], capture_output=True, text=True, timeout=600)
        if r.returncode:
            tail = [l.strip() for l in (r.stderr or r.stdout or "failed").strip().splitlines() if l.strip()][-14:]
            _note("Voice error details: " + " | ".join(tail)[-1500:])
            raise RuntimeError(tail[-1][:250])
        fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
        _note(f"Voice: Kokoro (af_heart), {len(jobs) - len(fails)} of {len(jobs)} lines")
        for f in fails[:3]:
            _note(f"Voice line given the backup voice: {f[5:300]}")
    except Exception as e:
        # never publish a robotic-voice video: stop here, and the platforms get their normal clips instead
        _note(f"Voice unavailable ({str(e)[:250]}): no breakdown video this time, normal clips are posted")
        raise RuntimeError(f"voice unavailable: {str(e)[:200]}")
    for j in jobs:
        if not os.path.exists(j["out"]):
            run(["espeak-ng", "-v", "en-us", "-s", "165", "-w", j["out"], j["text"]])
        out[j["key"]] = (j["out"], float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", j["out"]])))
    return out


# ---------- automatic parts from the prompt (used when the script is missing or too short) ----------

CAMERA = ["extreme close-up", "medium close-up", "close-up", "medium shot", "wide shot", "low-angle", "low angle",
          "high angle", "top-down", "overhead", "over-the-shoulder", "handheld", "tracking", "push-in", "pulls back",
          "pull back", "dolly", "crane", "whip pan", "locked-off", "slow motion", "slow-motion", "FPV", "macro",
          "aerial", "drone", "stutter-edit", "flash cuts", "MUST SHOW", "orbit", "time-lapse", "silhouette"]
KEEP_CAPS = {"FPV", "POV", "CGI", "VFX", "LED", "MUST", "SHOW", "TV", "DJ", "UFO", "USA", "UK"}


def calm_caps(text):
    """'THE GIRL raises...' -> 'the girl raises...' (names are written in capitals inside our prompts)."""
    return re.sub(r"\b[A-Z][A-Z'\-]{1,}(?:\s+[A-Z][A-Z'\-]{1,})*\b",
                  lambda m: m.group(0) if set(m.group(0).split()) & KEEP_CAPS else m.group(0).lower(), text)


def first_sentences(text, limit):
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        if out and len(out) + len(s) + 1 > limit:
            break
        out = (out + " " + s).strip()
    if not out or len(out) > limit:  # one long sentence: cut at a word and mark it
        cut = (out or text)[:limit].rsplit(" ", 1)[0].rstrip(",;:-— ")
        return cut + "…"
    return out


def auto_parts(prompt, duration):
    """Breakdown parts from the prompt's SHOT lines: (start, end, number, title, text)."""
    parts = []
    for m in re.finditer(r"SHOT\s+(\d+)\s*\((\d+):(\d+(?:\.\d+)?)\s*-\s*(\d+):(\d+(?:\.\d+)?)\)\s*[—-]+\s*([^\n]*)",
                         prompt or ""):
        a = int(m.group(2)) * 60 + float(m.group(3))
        b = min(duration, int(m.group(4)) * 60 + float(m.group(5)))
        body = m.group(6).strip()
        title, _, rest = body.partition(". ")
        text = calm_caps(rest or body)
        if b - a >= 0.3 and len(text) > 20 and "cut to black" not in body.lower():
            excerpt = first_sentences(text, 210)
            hl = [c for c in CAMERA if c.lower() in excerpt.lower()][:3]
            voice = f"Shot {m.group(1)}. " + first_sentences(excerpt, 140)
            parts.append({"n": int(m.group(1)), "from": round(a, 2), "to": round(b, 2), "excerpt": excerpt,
                          "highlight": hl, "voice": voice})
    if parts:
        return parts
    # no shot list: walk through the prompt's sections instead
    sections = [("The look", re.search(r"VIDEO PROMPT[^\n]*", prompt or "")),
                ("The character", re.search(r"CHARACTERS?:?\s*\n?([^\n]+)", prompt or "")),
                ("The sound", re.search(r"SOUND:?\s*([^\n]+)", prompt or ""))]
    sections = [(lab, calm_caps(m.group(m.lastindex or 0))) for lab, m in sections if m]
    step = duration / max(1, len(sections))
    return [{"label": lab, "from": round(i * step, 2), "to": round(min(duration, (i + 1) * step), 2),
             "excerpt": first_sentences(t, 210), "highlight": [c for c in CAMERA if c.lower() in t.lower()][:3],
             "voice": f"{lab}. " + first_sentences(t, 140)} for i, (lab, t) in enumerate(sections)]


def clean_parts(parts, duration):
    out = []
    for p in parts or []:
        try:
            a, b = max(0.0, float(p["from"])), min(duration, float(p["to"]))
        except Exception:
            continue
        excerpt = (p.get("excerpt") or "").strip()[:260]
        if b - a < 0.3 or not excerpt:
            continue
        voice = (p.get("voice") or "").strip() or first_sentences(excerpt, 140)
        out.append({**p, "from": a, "to": b, "excerpt": excerpt, "voice": voice,
                    "highlight": [h for h in p.get("highlight") or [] if isinstance(h, str)][:5]})
    return out


# ---------- text overlays (transparent PNGs, full frame) ----------

def canvas():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def centered(d, y, text, f, fill, stroke=4):
    """Text centered across the frame, with a dark outline so it reads on any picture."""
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill,
           stroke_width=stroke, stroke_fill=(0, 0, 0))


def spoken_hook(line, teaser="Wait for the ending..."):
    """The opening voice: the caption line exactly, then the teaser."""
    line = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+", "", line).strip()  # emoji aren't read aloud
    if not line.endswith((".", "!", "?", "…")):
        line += "."
    return line + " " + teaser.rstrip(". …") + "."


def tc(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def footer(d):
    centered(d, 1820, f"{HANDLE}  ·  full prompt in caption", font(30, False), GREY)


def overlay_hook(top, bottom, clip_y, clip_h, path):
    im = canvas()
    d = ImageDraw.Draw(im)
    f = font(78)
    lines = wrap(d, top, f, W - 120)
    y = max(130, clip_y - 70 - len(lines) * 95)
    for line in lines:
        centered(d, y, line, f, WHITE, stroke=5)
        y += 95
    centered(d, min(1700, clip_y + clip_h + 60), bottom, font(54, False), YEL, stroke=5)
    footer(d)
    im.save(path)


def overlay_original(credit, clip_y, clip_h, path):
    im = canvas()
    d = ImageDraw.Draw(im)
    centered(d, max(120, clip_y - 110), "THE ORIGINAL", font(50), YEL, stroke=5)
    centered(d, min(1720, clip_y + clip_h + 50), credit, font(34, False), WHITE, stroke=4)
    footer(d)
    im.save(path)


def overlay_shot(part, clip_h, path):
    im = canvas()
    d = ImageDraw.Draw(im)
    centered(d, 95, "HERE'S THE PROMPT", font(60), WHITE)
    centered(d, 177, "that made this", font(40, False), GREY)
    y = CLIP_TOP + clip_h + 40
    d.rounded_rectangle((60, y, W - 60, y + 90), 20, fill=YEL)
    label = part.get("label") or f"SHOT {part.get('n', '')}".strip()
    centered(d, y + 22, f"{label.upper()}  ·  {tc(part['from'])} - {tc(part['to'])}", font(40), BG, stroke=0)
    excerpt = part["excerpt"]
    spans = []
    for h in part.get("highlight", []):
        spans += [(m.start(), m.end()) for m in re.finditer(re.escape(h), excerpt, re.I)]
    words = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", excerpt)]
    top, bottom = y + 140, 1770
    for size in (52, 48, 44, 40, 36, 32):  # the biggest text that fits the space under the clip
        fn, fb = font(size, False), font(size)
        layout, x, yy = [], 100, top
        for word, a, b in words:
            hl = any(a < e and b > s for s, e in spans)
            f = fb if hl else fn
            wlen = d.textlength(word, font=f)
            if x + wlen > W - 100:
                x, yy = 100, yy + int(size * 1.45)
            layout.append((x, yy, word, f, hl))
            x += wlen + d.textlength(" ", font=f)
        end = yy + int(size * 1.45)
        if end + 30 <= bottom:
            break
    d.rounded_rectangle((60, top - 36, W - 60, min(bottom, end + 30)), 28, fill=(30, 30, 38, 255))
    for x, yy, word, f, hl in layout:
        d.text((x, yy), word, font=f, fill=YEL if hl else WHITE)
    footer(d)
    im.save(path)


def overlay_outro(path):
    im = canvas()
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((90, 640, W - 90, 1280), 36, fill=(12, 12, 16, 225))
    centered(d, 720, "Full prompt", font(76), WHITE)
    centered(d, 815, "is in the caption", font(76), YEL)
    centered(d, 990, "Follow for a new AI video", font(44, False), WHITE)
    centered(d, 1050, "+ its prompt every day", font(44, False), WHITE)
    centered(d, 1150, HANDLE, font(52), YEL)
    im.save(path)


# ---------- video segments ----------

def segment(src, has_audio, start, length, out_dur, png, layout, size, out, voice=None, orig_vol=0.0, slow=1.0):
    """One 1080x1920 segment: the clip (optionally slowed, last frame held) + overlay + sound."""
    cw, ch = size
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-t", f"{length}", "-i", src,
           "-loop", "1", "-t", f"{out_dur}", "-i", png]
    if has_audio:
        cmd += ["-ss", f"{start}", "-t", f"{out_dur}", "-i", src]
    else:
        cmd += ["-f", "lavfi", "-t", f"{out_dur}", "-i", "anullsrc=r=48000:cl=stereo"]
    if voice:
        cmd += ["-i", voice]
    clip = (f"[0:v]setpts={slow}*(PTS-STARTPTS),fps={FPS},tpad=stop_mode=clone:stop_duration={out_dur},"
            f"trim=duration={out_dur},setpts=PTS-STARTPTS")
    if layout == "top":
        v = (f"{clip},scale={cw}:{ch},setsar=1[fg];color=c=0x0C0C10:s={W}x{H}:r={FPS}:d={out_dur}[bg];"
             f"[bg][fg]overlay={(W - cw) // 2}:{CLIP_TOP}:shortest=1[v0]")
    else:  # the clip centered on a blurred, darkened copy of itself
        v = (f"{clip},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=30:3,eq=brightness=-0.2,setsar=1[bg];[b]scale={cw}:{ch},setsar=1[fg];"
             f"[bg][fg]overlay={(W - cw) // 2}:{(H - ch) // 2}[v0]")
    v += ";[v0][1:v]overlay=0:0,format=yuv420p[v]"
    a = (f"[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={orig_vol},apad,"
         f"atrim=0:{out_dur}[o]")
    if voice:
        a += (f";[3:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay=350|350,apad,atrim=0:{out_dur}[vo];"
              f"[o][vo]amix=inputs=2:normalize=0:duration=first[a]")
    else:
        a += ";[o]anull[a]"
    cmd += ["-filter_complex", v + ";" + a, "-map", "[v]", "-map", "[a]", "-t", f"{out_dur}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", f"{FPS}", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", out]
    run(cmd)


def build(day, key, out_path, src=None, base=None):
    """key: 1 or 2 (that day's posted video) or a candidate's slug. src: the original file, if already downloaded.
    Returns the finished video's length in seconds."""
    job = {}
    if str(key).isdigit():
        job = json.load(open(os.path.join(base or ROOT, "prompts", "x", f"{day}-{key}.json"), encoding="utf-8"))
        slug = job["slug"]
    else:
        slug = key
    sp = os.path.join(base or ROOT, "breakdowns", f"{day}-{key}.json")
    script = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    if not script:
        _note("No breakdown script saved for this video: making one from the prompt")
    folder = os.path.join(ROOT, "days", day, slug)
    meta = json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8"))
    sys.path.insert(0, ROOT)
    import models
    model = models.detect_in_dir(meta, folder) or ""
    credit = f"Made with {model}" if model else "AI video"  # no creator name on screen: credits go in the comments

    tmp = tempfile.mkdtemp()
    if not src:
        src = os.path.join(tmp, "original.mp4")
        req = urllib.request.Request(meta["video_url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r, open(src, "wb") as f:
            f.write(r.read())
    dur, w, h, has_audio = probe(src)
    center = fit(w, h, W, CENTER_BOX_H)
    top = fit(w, h, W, TOP_BOX_H)
    cy = (H - center[1]) // 2

    # the script, checked and completed
    hook_line = (job.get("caption") or meta.get("title") or "").split("\n")[0]
    hk = script.get("hook") or {}
    # the opening text and the opening voice are always exactly the post's caption line 1
    hk = {"from": min(max(0.0, float(hk.get("from", dur * 0.3))), max(0.0, dur - 1)),
          "text_top": hook_line or hk.get("text_top"), "text_bottom": hk.get("text_bottom") or "Wait for the ending...",
          "voice": spoken_hook(hook_line or hk.get("voice") or "Watch this.", hk.get("text_bottom") or "Wait for the ending...")}
    intro = f"Here's the original, made with {model}." if model else "Here's the original."  # always this wording
    outro = script.get("outro_voice") or "The full prompt is in the caption. Follow Mira AI for a new one every day."
    parts = clean_parts(script.get("shots"), dur)
    used = {(round(p["from"], 1), round(p["to"], 1)) for p in parts}
    reserve = [p for p in auto_parts(job.get("prompt", ""), dur) if (round(p["from"], 1), round(p["to"], 1)) not in used]
    if not parts:  # no script: pick parts spread evenly across the clip
        k = min(len(reserve), 4 if dur >= 25 else 5 if dur >= 15 else 6)
        idx = sorted({round(i * (len(reserve) - 1) / max(1, k - 1)) for i in range(k)}) if k else []
        parts = [reserve[i] for i in idx]
        reserve = [p for i, p in enumerate(reserve) if i not in idx]
    # extra parts (only used if the video would be under a minute): spread out too, middle of the gaps first
    reserve.sort(key=lambda p: min([abs(p["from"] - q["from"]) for q in parts] or [0]), reverse=True)

    spoken_lines = voices([hk["voice"], intro, outro] + [p["voice"] for p in parts + reserve], tmp)

    def wav(name, text):
        return spoken_lines[text] if text in spoken_lines else voices([text], tmp)[text]

    hook_vo = wav("hook", hk["voice"])
    hook_dur = round(max(hook_vo[1] + 0.9, 3.5), 2)
    intro_vo = wav("intro", intro)
    outro_vo = wav("outro", outro)
    outro_dur = round(outro_vo[1] + 1.2, 2)

    def plan(p, i):
        if "_vo" not in p:
            p["_vo"] = wav(f"part{i}_{len(p['voice'])}", p["voice"])
        length = max(0.4, p["to"] - p["from"])
        p["_dur"] = round(max(p["_vo"][1] + 0.8, length), 2)
        p["_slow"] = round(min(p["_dur"] / length, 2.0), 3)
        return p["_dur"]

    total = lambda: hook_dur + dur + sum(p["_dur"] for p in parts) + outro_dur
    for i, p in enumerate(parts):
        plan(p, i)
    while total() < MIN_SECONDS and reserve:  # too short: add parts made from the prompt
        p = reserve.pop(0)
        plan(p, len(parts))
        parts.append(p)
        parts.sort(key=lambda q: q["from"])
    while total() > MAX_SECONDS and len(parts) > 3:  # too long: drop parts, keeping the first and the last
        drop = parts.pop(len(parts) - 2)
        if total() < MIN_SECONDS:
            parts.insert(len(parts) - 1, drop)
            break
    if total() < MIN_SECONDS:  # still short: hold the outro card longer
        outro_dur = round(outro_dur + (MIN_SECONDS - total()), 2)

    segs = []
    png = os.path.join(tmp, "hook.png")
    overlay_hook(hk["text_top"], hk["text_bottom"], cy, center[1], png)
    segs.append(("hook", hk["from"], min(hook_dur, dur - hk["from"]), hook_dur, png, "center", center,
                 hook_vo[0], 0.35, 1.0))
    png = os.path.join(tmp, "orig.png")
    overlay_original(credit, cy, center[1], png)
    segs.append(("orig", 0, dur, round(dur, 2), png, "center", center, intro_vo[0], 0.8, 1.0))
    for i, p in enumerate(parts):
        png = os.path.join(tmp, f"part{i}.png")
        overlay_shot(p, top[1], png)
        segs.append((f"part{i}", p["from"], max(0.4, p["to"] - p["from"]), p["_dur"], png, "top", top,
                     p["_vo"][0], 0.12, p["_slow"]))
    png = os.path.join(tmp, "outro.png")
    overlay_outro(png)
    segs.append(("outro", max(0, dur - 2.5), 0.1, outro_dur, png, "center", center, outro_vo[0], 0.0, 1.0))

    files = []
    for name, start, length, out_dur, png, layout, size, vo, vol, slow in segs:
        f = os.path.join(tmp, f"{len(files):02d}_{name}.mp4")
        segment(src, has_audio, start, length, out_dur, png, layout, size, f, vo, orig_vol=vol, slow=slow)
        files.append(f)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{x}'\n" for x in files))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", out_path])
    length = probe(out_path)[0]
    _note(f"Breakdown video: {length:.1f}s, {len(parts)} parts, from a {dur:.1f}s {w}x{h} clip")
    return length


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3], base=sys.argv[4] if len(sys.argv) > 4 else None)
