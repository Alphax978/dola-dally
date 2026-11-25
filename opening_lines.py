"""The rotating line shown above the clip in the YouTube/Facebook/Instagram/TikTok video,
and used as line 1 of the X post. Each video always gets the same line; the two daily videos never share one."""
import datetime

OPENING_LINES = [  # shown above the clip; one per video, rotating day by day
    "This AI video is a masterpiece.",
    "This AI video is pure art.",
    "Hard to believe AI made this.",
    "This AI video looks unreal.",
    "This AI video is next level.",
    "This AI video is a work of art.",
    "This AI video is breathtaking.",
    "This AI video is incredible.",
    "This AI video is beautifully made.",
]


EMOJIS = ["🔥", "⚡", "🤯", "💥", "✨", "🎬", "😱", "👀"]  # added to caption line 1, rotating too


def caption_line(day, key):
    """Caption line 1 on every site: the rotating line + a rotating emoji, e.g. "This AI video looks unreal 🔥".
    (The line shown on the TikTok video itself has no emoji: the video font can't draw them.)"""
    n = datetime.date.fromisoformat(day).toordinal() * 2 + (int(key) if str(key).isdigit() else 0)
    return opening_line(day, key).rstrip(".") + " " + EMOJIS[n % len(EMOJIS)]


def opening_line(day, key):
    """day: YYYY-MM-DD, key: 1 or 2 (that day's video)."""
    n = datetime.date.fromisoformat(day).toordinal() * 2 + (int(key) if str(key).isdigit() else 0)
    return OPENING_LINES[n % len(OPENING_LINES)]
