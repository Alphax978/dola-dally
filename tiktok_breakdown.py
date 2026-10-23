#!/usr/bin/env python3
"""
tiktok_breakdown.py: turn a 15-30 s clip into a 60-75 s "prompt breakdown" video for TikTok, 9:16:

  1. hook       the most striking moment, with the hook in big text            (voiceover)
  2. original   the full clip, credited                                         (original sound + voice intro)
  3. breakdown  key shots replayed on top, the prompt words that made them below, key words in yellow (voiceover)
  4. outro      "full prompt in the caption, follow for more"                  (voiceover)

The script for steps 1-4 is breakdowns/<day>-<slot>.json. Voiceover: Kokoro, a free open-source voice
that runs on the GitHub machine (falls back to espeak-ng if Kokoro can't load).

  python3 tiktok_breakdown.py DAY SLOT OUT.mp4
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
BG, YEL, WHITE, GREY = (12, 12, 16), (255, 214, 10), (245, 245, 245), (165, 165, 175)
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
HANDLE = "@miraai.creates"


def font(size, bold=True):
    return ImageFont.truetype(FONT_DIR + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")
    return r.stdout


def probe(path):
    j = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", path]))
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return float(j["format"]["duration"]), v["width"], v["height"], any(s["codec_type"] == "audio" for s in j["streams"])


# ---------- voice ----------

_kokoro = None
_noted = set()


def _note(msg):
    print(msg, flush=True)
    if os.environ.get("GITHUB_ACTIONS") and msg not in _noted:
        _noted.add(msg)
        print(f"::notice title=Breakdown::{msg}", flush=True)


def say(text, out_wav):
    """Speak `text` into a wav; returns its length in seconds."""
    global _kokoro
    try:
        if _kokoro is None:
            from kokoro import KPipeline
            _kokoro = KPipeline(lang_code="a")
        import numpy as np
        import soundfile as sf
        audio = np.concatenate([a for _, _, a in _kokoro(text, voice="af_heart", speed=1.0)])
        sf.write(out_wav, audio, 24000)
        _note("Voice: Kokoro (af_heart)")
    except Exception as e:
        _note(f"Voice: espeak-ng fallback (Kokoro unavailable: {str(e)[:200]})")
        run(["espeak-ng", "-v", "en-us", "-s", "165", "-w", out_wav, text])
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out_wav]))


# ---------- text overlays (transparent PNGs, full frame) ----------

def canvas():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def centered(d, y, text, f, fill, stroke=4):
    """Text centered across the frame, with a dark outline so it reads on any picture."""
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill,
           stroke_width=stroke, stroke_fill=(0, 0, 0))


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
    y = clip_y - 70 - len(lines) * 95
    for line in lines:
        centered(d, y, line, f, WHITE)
        y += 95
    centered(d, clip_y + clip_h + 60, bottom, font(54, False), YEL)
    footer(d)
    im.save(path)


def overlay_original(credit, clip_y, clip_h, path):
    im = canvas()
    d = ImageDraw.Draw(im)
    centered(d, clip_y - 110, "THE ORIGINAL", font(50), YEL)
    centered(d, clip_y + clip_h + 50, credit, font(34, False), WHITE)
    footer(d)
    im.save(path)


def overlay_shot(shot, excerpt, highlight, clip_y, clip_h, path):
    im = canvas()
    d = ImageDraw.Draw(im)
    centered(d, 100, "HERE'S THE PROMPT", font(60), WHITE)
    centered(d, 182, "that made this", font(40, False), GREY)
    y = clip_y + clip_h + 50
    d.rounded_rectangle((60, y, W - 60, y + 90), 20, fill=YEL)
    centered(d, y + 22, f"SHOT {shot['n']}  ·  {tc(shot['from'])} - {tc(shot['to'])}", font(40), BG, stroke=0)
    # mark highlighted character spans, then draw word by word
    spans = []
    for h in highlight:
        spans += [(m.start(), m.end()) for m in re.finditer(re.escape(h), excerpt, re.I)]
    words = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", excerpt)]
    size = 52
    fn, fb = font(size, False), font(size)
    top = y + 140
    layout, x, yy, maxw = [], 100, top, W - 100  # lay the words out first, to size the card to the text
    for word, a, b in words:
        hl = any(a < e and b > s for s, e in spans)
        f = fb if hl else fn
        wlen = d.textlength(word, font=f)
        if x + wlen > maxw:
            x, yy = 100, yy + int(size * 1.45)
        layout.append((x, yy, word, f, hl))
        x += wlen + d.textlength(" ", font=f)
    d.rounded_rectangle((60, top - 36, W - 60, yy + int(size * 1.45) + 30), 28, fill=(30, 30, 38, 255))
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

def segment(src, has_audio, start, length, out_dur, png, layout, out, voice=None, orig_vol=0.0, slow=1.0):
    """Render one 1080x1920 segment: clip (optionally slowed, last frame held) + overlay + sound."""
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
        v = (f"{clip},scale={W}:-2[fg];color=c=0x0C0C10:s={W}x{H}:r={FPS}:d={out_dur}[bg];"
             f"[bg][fg]overlay=0:{CLIP_TOP}:shortest=1[v0]")
    else:  # clip centered on a blurred, darkened copy of itself
        v = (f"{clip},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=30:3,eq=brightness=-0.2[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2[v0]")
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


CLIP_TOP = 300


def build(day, slot, out_path):
    job = json.load(open(os.path.join(ROOT, "prompts", "x", f"{day}-{slot}.json"), encoding="utf-8"))
    script = json.load(open(os.path.join(ROOT, "breakdowns", f"{day}-{slot}.json"), encoding="utf-8"))
    meta = json.load(open(os.path.join(ROOT, "days", day, job["slug"], "meta.json"), encoding="utf-8"))
    sys.path.insert(0, ROOT)
    import models
    model = models.detect_in_dir(meta, os.path.join(ROOT, "days", day, job["slug"])) or "AI"
    handle = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status", meta.get("x_post") or "")
    credit = f"Made with {model}" + (f"  ·  by @{handle.group(1)}" if handle else "")

    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "original.mp4")
    req = urllib.request.Request(meta["video_url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(src, "wb") as f:
        f.write(r.read())
    dur, w, h, has_audio = probe(src)
    clip_h = round(W * h / w / 2) * 2
    clip_y_center = (H - clip_h) // 2
    parts = []

    def wav(name, text):
        p = os.path.join(tmp, name + ".wav")
        return p, say(text, p)

    # 1. hook
    hk = script["hook"]
    vo, vlen = wav("hook", hk["voice"])
    out_dur = round(max(vlen + 0.9, 3.5), 2)
    png = os.path.join(tmp, "hook.png")
    overlay_hook(hk["text_top"], hk["text_bottom"], clip_y_center, clip_h, png)
    p = os.path.join(tmp, "p1.mp4")
    segment(src, has_audio, hk["from"], out_dur, out_dur, png, "center", p, vo, orig_vol=0.35)
    parts.append(p)

    # 2. original
    vo, vlen = wav("intro", script["intro_voice"])
    png = os.path.join(tmp, "orig.png")
    overlay_original(credit, clip_y_center, clip_h, png)
    p = os.path.join(tmp, "p2.mp4")
    segment(src, has_audio, 0, dur, round(dur, 2), png, "center", p, vo, orig_vol=0.8)
    parts.append(p)

    # 3. breakdown
    for i, shot in enumerate(script["shots"]):
        vo, vlen = wav(f"shot{i}", shot["voice"])
        length = max(0.4, shot["to"] - shot["from"])
        out_dur = round(max(vlen + 0.8, length), 2)
        slow = round(min(out_dur / length, 2.0), 3)
        png = os.path.join(tmp, f"shot{i}.png")
        overlay_shot(shot, shot["excerpt"], shot.get("highlight", []), CLIP_TOP, clip_h, png)
        p = os.path.join(tmp, f"p3_{i}.mp4")
        segment(src, has_audio, shot["from"], length, out_dur, png, "top", p, vo, orig_vol=0.12, slow=slow)
        parts.append(p)

    # 4. outro
    vo, vlen = wav("outro", script["outro_voice"])
    out_dur = round(vlen + 1.2, 2)
    png = os.path.join(tmp, "outro.png")
    overlay_outro(png)
    p = os.path.join(tmp, "p4.mp4")
    segment(src, has_audio, max(0, dur - 2.5), 0.1, out_dur, png, "center", p, vo, orig_vol=0.0)
    parts.append(p)

    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{x}'\n" for x in parts))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", out_path])
    total = probe(out_path)[0]
    print(f"Breakdown video: {out_path} ({total:.1f} s)")
    return total


if __name__ == "__main__":
    build(sys.argv[1], int(sys.argv[2]), sys.argv[3])
