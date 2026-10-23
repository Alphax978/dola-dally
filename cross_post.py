#!/usr/bin/env python3
"""
cross_post.py: after a video goes out on X, post the same video to YouTube (Shorts),
the Facebook Page and Instagram (Reels). Used by post_to_x.py.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions). A platform whose
secrets are missing is simply skipped.
  YouTube:   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  Facebook:  FB_PAGE_ID, FB_PAGE_TOKEN
  Instagram: IG_USER_ID (+ FB_PAGE_TOKEN, the Page linked to the Instagram account)

  python3 cross_post.py --check      checks every account's keys without posting anything
"""
import json
import os
import re
import subprocess
import time

import requests

GRAPH = "https://graph.facebook.com/v23.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v23.0"
HASHTAGS = "#AIvideo #Seedance #AIart #AIgenerated #texttovideo"


def env(name):
    return os.environ.get(name, "").strip()


PAUSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paused.txt")


def paused():
    """Platforms switched off in paused.txt (one per line: x, youtube, facebook, instagram, tiktok)."""
    if not os.path.exists(PAUSE_FILE):
        return set()
    return {l.split("#")[0].strip().lower() for l in open(PAUSE_FILE, encoding="utf-8")} - {""}


def enabled():
    out = [n for n in _connected() if n not in paused()]
    return out


def _connected():
    out = []
    if env("YT_CLIENT_ID") and env("YT_CLIENT_SECRET") and env("YT_REFRESH_TOKEN"):
        out.append("youtube")
    if env("FB_PAGE_ID") and env("FB_PAGE_TOKEN"):
        out.append("facebook")
    if env("IG_USER_ID") and env("FB_PAGE_TOKEN"):
        out.append("instagram")
    import tiktok
    if tiktok.mode() == "buffer" or tiktok.configured():
        out.append("tiktok")
    return out


class PostError(Exception):
    pass


def ok(r, what):
    if r.status_code >= 300:
        raise PostError(f"{what}: {r.status_code} {r.text[:400]}")
    return r.json() if r.content else {}


# ---------- texts ----------

def credit_line(handle, x_post):
    # No "@handle" here: on YouTube/Facebook/Instagram it would tag a different person.
    if handle:
        return f"🎬 Original by {handle} on X: {x_post}" if x_post else f"🎬 Original by {handle} on X"
    return "🎬 Original from the YouMind Seedance 2.5 gallery"


def clean_hook(caption):
    """Caption lines (hook, model line) kept as separate paragraphs; no links."""
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in re.sub(r"https?://\S+", "", caption or "").splitlines()]
    return "\n\n".join(l for l in lines if l)


def cut(text, limit, measure=len):
    if measure(text) <= limit:
        return text
    while text and measure(text + "…") > limit:
        text = text[:-20].rsplit(" ", 1)[0] if " " in text[-40:] else text[:-20]
    return text.rstrip(" ,.;:-\n") + "…"


def texts(hook, credit, prompt, prompt_short):
    """Title + descriptions for each platform."""
    hook = clean_hook(hook)
    credit = f"\n\n{credit}" if credit else ""  # empty: no credit line (credits are added by hand in comments)
    title = cut(re.sub(r"[<>]", "", hook.split("\n")[0]) or "AI video of the day", 90)  # first line only
    nb = lambda s: len(s.encode("utf-8"))
    # YouTube: description max 5000 bytes, no angle brackets
    yt_head = f"{hook}{credit}\n\nPrompt to recreate it:\n"
    yt_tail = f"\n\n{HASHTAGS} #Shorts"
    yt_prompt = cut(prompt, 4900 - nb(yt_head) - nb(yt_tail), nb)
    youtube = re.sub(r"[<>]", "", yt_head + yt_prompt + yt_tail)
    # Facebook: long text is fine
    facebook = f"{hook}{credit}\n\nPrompt to recreate it ⤵️\n{prompt}\n\n{HASHTAGS}"
    # Instagram: max 2200 characters, 30 hashtags
    ig_head = f"{hook}{credit}\n\nPrompt ⤵️\n"
    ig_tail = f"\n\n{HASHTAGS}"
    room = 2200 - len(ig_head) - len(ig_tail)
    body = prompt if len(prompt) <= room else cut(prompt_short or prompt, room)
    instagram = ig_head + body + ig_tail
    return {"title": title, "youtube": youtube, "facebook": facebook, "instagram": instagram}


# ---------- 9:16 version for Shorts / Reels ----------

def size(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation", "-of", "json", path],
                       capture_output=True, text=True).stdout
    st = json.loads(o)["streams"][0]
    w, h = st["width"], st["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in st.get("side_data_list", []) if "rotation" in d), 0)
    return (h, w) if rot in (90, 270) else (w, h)


# One high-quality H.264 encode, shared by X and the 9:16 version.
QUALITY = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "10M", "-bufsize", "20M",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-fpsmax", "60", "-movflags", "+faststart"]


def probe(path):
    """(width, height, video codec, pixel format, audio codec or None)."""
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt",
                        "-of", "json", path], capture_output=True, text=True).stdout
    st = json.loads(o).get("streams", [])
    v = next((x for x in st if x.get("codec_type") == "video"), {})
    a = next((x for x in st if x.get("codec_type") == "audio"), None)
    w, h = size(path)
    return w, h, v.get("codec_name"), v.get("pix_fmt"), (a or {}).get("codec_name")


def encode(src, out, vf):
    """Encode once with QUALITY; keeps the audio (AAC 128k), adds a silent track if there is none."""
    has_audio = probe(src)[4] is not None
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    if not has_audio:  # some players and platforms choke on video without an audio track
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0", "-vf", vf, *QUALITY,
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", out]
    subprocess.run(cmd, check=True)
    return out


def vertical(original, workdir):
    """The 9:16 version for YouTube/Facebook/Instagram/TikTok, made straight from the ORIGINAL file.

    Already 9:16: sent untouched when it's a normal H.264 file of at most 1080x1920 (only repackaged,
    no quality loss); otherwise re-encoded once to 1080x1920.
    Any other shape: the whole video, black bars above and below (zoom 100, nothing cropped), one encode.
    """
    w, h, vcodec, pix, acodec = probe(original)
    out = os.path.join(workdir, "vertical.mp4")
    fit = "scale=1080:1920:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    if h / w >= 1.7:  # already 9:16 (1.78), allow small differences
        if vcodec == "h264" and pix == "yuv420p" and w <= 1080 and h <= 1920:
            if acodec in ("aac", None):
                cmd = ["ffmpeg", "-v", "error", "-y", "-i", original]
                if acodec is None:  # add a silent track; the picture is copied, not re-encoded
                    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k"]
                else:
                    cmd += ["-map", "0:v:0", "-map", "0:a:0", "-c", "copy"]
                subprocess.run(cmd + ["-movflags", "+faststart", out], check=True)
                return out
        return encode(original, out, fit + ",format=yuv420p")
    return encode(original, out, fit + ",pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p")


# ---------- YouTube ----------

def yt_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}, timeout=30)
    return ok(r, "YouTube sign-in")["access_token"]


def youtube(video, t):
    token = yt_token()
    meta = {
        "snippet": {"title": t["title"], "description": t["youtube"], "categoryId": "1",  # Film & Animation
                    "tags": ["AI video", "Seedance", "Seedance 2.5", "AI art", "text to video", "AI prompts"]},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},  # YouTube's "altered or synthetic content" label
    }
    size = os.path.getsize(video)
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos",
                      params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                      data=json.dumps(meta), timeout=60)
    ok(r, "YouTube upload start")
    with open(video, "rb") as f:
        r = requests.put(r.headers["Location"], data=f,
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"}, timeout=900)
    data = ok(r, "YouTube upload")
    vid = data["id"]
    channel = (data.get("snippet") or {}).get("channelTitle")
    privacy = (data.get("status") or {}).get("privacyStatus")
    note = "" if privacy in (None, "public") else f" (YouTube set it to {privacy}: the API project may need YouTube's audit)"
    if channel:
        note = f" on {channel}" + note
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}", "note": note}


# ---------- Facebook Page ----------

def facebook(video, t):
    with open(video, "rb") as f:
        r = requests.post(f"{GRAPH_VIDEO}/{env('FB_PAGE_ID')}/videos",
                          data={"description": t["facebook"], "title": t["title"], "published": "true",
                                "access_token": env("FB_PAGE_TOKEN")},
                          files={"source": ("video.mp4", f, "video/mp4")}, timeout=900)
    vid = ok(r, "Facebook upload")["id"]
    return {"id": vid, "url": f"https://www.facebook.com/{env('FB_PAGE_ID')}/videos/{vid}"}


# ---------- Instagram Reels ----------

def instagram(video, t, video_url=None):
    ig, token = env("IG_USER_ID"), env("FB_PAGE_TOKEN")
    base = {"media_type": "REELS", "caption": t["instagram"], "share_to_feed": "true", "access_token": token}
    try:  # upload our own (re-encoded) file
        c = ok(requests.post(f"{GRAPH}/{ig}/media", data={**base, "upload_type": "resumable"}, timeout=60),
               "Instagram container")
        size = os.path.getsize(video)
        with open(video, "rb") as f:
            ok(requests.post(c["uri"], data=f, timeout=900, headers={
                "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}), "Instagram upload")
        container = c["id"]
    except PostError:
        if not video_url:
            raise
        # fallback: let Instagram fetch the original file itself
        container = ok(requests.post(f"{GRAPH}/{ig}/media", data={**base, "video_url": video_url}, timeout=60),
                       "Instagram container (from link)")["id"]
    for _ in range(60):  # Instagram processes the video first (usually under a minute)
        st = ok(requests.get(f"{GRAPH}/{container}", params={"fields": "status_code,status", "access_token": token},
                             timeout=30), "Instagram status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise PostError(f"Instagram couldn't process the video: {st.get('status')}")
        time.sleep(10)
    else:
        raise PostError("Instagram took too long to process the video")
    media = ok(requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": container, "access_token": token},
                             timeout=60), "Instagram publish")["id"]
    try:
        link = requests.get(f"{GRAPH}/{media}", params={"fields": "permalink", "access_token": token},
                            timeout=30).json().get("permalink")
    except Exception:
        link = None
    return {"id": media, "url": link or ""}


# ---------- all together ----------

def save_tiktok_caption(caption, key, credit=""):
    """Drafts can't carry a caption: keep the last few on the site's copy page (docs/tiktok.html)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "tiktok", "captions.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        items = json.load(open(p, encoding="utf-8"))
    except Exception:
        items = []
    items = [i for i in items if i.get("key") != key]
    items.insert(0, {"key": key or time.strftime("%Y-%m-%d %H:%M"), "caption": caption, "credit": credit})
    json.dump(items[:6], open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def tiktok_post(video, t):
    import tiktok
    caption = t["instagram"]  # same caption as Instagram (hook, prompt, hashtags; max 2,200)
    save_tiktok_caption(caption, t.get("key"), t.get("credit", ""))  # caption + credit on the copy page
    if tiktok.mode() == "buffer":
        import buffer_feed
        return buffer_feed.publish(video, caption, t.get("key") or time.strftime("%Y-%m-%d-%H%M"), t["title"])
    return tiktok.post(video, caption)


NICE = {"youtube": "YouTube", "facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok"}
POSTERS = {"youtube": youtube, "facebook": facebook, "instagram": instagram, "tiktok": tiktok_post}


def post_all(video, t, done=None, video_url=None, log=print, wide=None, tiktok_video=None):
    """Post to every platform that has secrets and isn't done yet. One failure doesn't stop the others.

    video: the 9:16 version (YouTube, Instagram, TikTok). wide: the original-shape version for Facebook,
    which fills the player on PC as well as phones (falls back to `video` if not given).
    tiktok_video: a function that makes TikTok's own version (the 1-minute+ prompt breakdown); it only runs
    when TikTok's turn comes, so the other platforms aren't kept waiting. If it fails, TikTok gets `video`."""
    done = dict(done or {})
    for name in enabled():
        if isinstance(done.get(name), dict) and done[name].get("id"):
            continue
        try:
            if name == "instagram":
                res = instagram(video, t, video_url)
            elif name == "facebook":
                res = facebook(wide or video, t)
            elif name == "tiktok" and tiktok_video:
                try:
                    tv = tiktok_video()
                except Exception as e:
                    log(f"TikTok: couldn't make the breakdown version ({str(e)[:300]}); sending the normal clip")
                    tv = video
                res = POSTERS[name](tv or video, t)
            else:
                res = POSTERS[name](video, t)
            done[name] = res
            log(f"{NICE[name]}: posted {res.get('url', '')}{res.get('note', '')}")
        except Exception as e:  # keep going with the next platform
            done[name] = {"error": str(e)[:500], "at": time.strftime("%Y-%m-%d %H:%M")}
            log(f"{NICE[name]}: FAILED: {str(e)[:500]}")
    return done


def check_accounts(log=print):
    """Confirm each platform's keys work, without posting. Returns True if all enabled ones are fine."""
    good = True
    names = _connected()  # paused platforms are checked too, so new keys can be tested before switching them on
    off = paused()
    for name in ("youtube", "facebook", "instagram", "tiktok"):
        if name not in names:
            log(f"{NICE[name]}: skipped ({'not connected yet' if name == 'tiktok' else 'secrets not added'})")
    for name in names:
        tag = " [PAUSED in paused.txt]" if name in off else ""
        try:
            if name == "youtube":
                # the key may only upload (youtube.upload scope), so it can't read the channel name
                info = ok(requests.get("https://oauth2.googleapis.com/tokeninfo",
                                       params={"access_token": yt_token()}, timeout=30), "YouTube key")
                scopes = info.get("scope", "")
                if "youtube.upload" not in scopes and "auth/youtube " not in scopes + " ":
                    raise PostError(f"signed in, but this key can't upload videos (scopes: {scopes})")
                who = "your channel (upload permission confirmed)"
            elif name == "facebook":
                who = ok(requests.get(f"{GRAPH}/{env('FB_PAGE_ID')}", params={"fields": "name",
                         "access_token": env("FB_PAGE_TOKEN")}, timeout=30), "Facebook Page")["name"]
            elif name == "tiktok":
                import tiktok
                if tiktok.mode() == "buffer":
                    who = "Buffer (via https://alphax978.github.io/dola-dally/tiktok/feed.xml) (mode: buffer)"
                else:
                    who = f"{tiktok.who(tiktok.access_token())} (mode: {tiktok.mode()})"
            else:
                who = "@" + ok(requests.get(f"{GRAPH}/{env('IG_USER_ID')}", params={"fields": "username",
                               "access_token": env("FB_PAGE_TOKEN")}, timeout=30), "Instagram account")["username"]
            log(f"{NICE[name]}: keys OK, posting as {who}{tag}")
        except Exception as e:
            good = False
            log(f"{NICE[name]}: keys NOT working: {str(e)[:400]}{tag}")
    return good


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        sys.exit(0 if check_accounts() else 1)
    print(__doc__)
