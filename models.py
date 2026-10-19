"""models.py: which AI video model made a clip, read from its source page (YouMind, ReelCine or Domer)."""
import os
import re

# Names we accept as a video model (YouMind's breadcrumb sometimes names a text model instead).
KNOWN = re.compile(r"^(Seedance|Veo|Kling|Sora|Hailuo|Wan|Runway|Pika|Vidu|MiniMax|Grok Imagine|LTX|Jimeng|Dreamina|"
                   r"PixVerse|Luma|Ray|Gen-\d|Midjourney|Higgsfield|Happy ?Horse|Gemini Omni)\b", re.I)


def _nice(name):
    name = re.sub(r"\s+", " ", name.replace("-", " ")).strip()
    m = re.match(r"(?i)seedance\s*(\d)\.?(\d)?", name)
    if m:
        return f"Seedance {m.group(1)}.{m.group(2) or 0}"
    return name[:1].upper() + name[1:]


def detect(meta, page_text=""):
    """Model name like 'Seedance 2.5', or None if the source doesn't say."""
    if meta.get("model"):
        return meta["model"]
    m = re.search(r"/(seedance-\d\.\d)/", meta.get("video_url") or "")  # ReelCine file path
    if m:
        return _nice(m.group(1))
    m = re.search(r"Video Prompt\s*›\s*(.+?)\s+VIDEO PROMPT", page_text)  # YouMind breadcrumb
    if m and KNOWN.match(m.group(1).strip()):
        return _nice(m.group(1))
    m = re.search(r"\b(Seedance\s*\d\.\d)\s+AI Video Prompt", page_text, re.I)  # YouMind title line
    if m:
        return _nice(m.group(1))
    return None


def detect_in_dir(meta, folder):
    p = os.path.join(folder, "creator_page.txt")
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return detect(meta, text)
