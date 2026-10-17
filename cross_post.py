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


def enabled():
    out = []
    if env("YT_CLIENT_ID") and env("YT_CLIENT_SECRET") and env("YT_REFRESH_TOKEN"):
        out.append("youtube")
    if env("FB_PAGE_ID") and env("FB_PAGE_TOKEN"):
        out.append("facebook")
    if env("IG_USER_ID") and env("FB_PAGE_TOKEN"):
        out.append("instagram")
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
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", caption or "")).strip()


def cut(text, limit, measure=len):
    if measure(text) <= limit:
        return text
    while text and measure(text + "…") > limit:
        text = text[:-20].rsplit(" ", 1)[0] if " " in text[-40:] else text[:-20]
    return text.rstrip(" ,.;:-\n") + "…"


def texts(hook, credit, prompt, prompt_short):
    """Title + descriptions for each platform."""
    hook = clean_hook(hook)
    title = cut(re.sub(r"[<>]", "", hook) or "AI video of the day", 90)
    nb = lambda s: len(s.encode("utf-8"))
    # YouTube: description max 5000 bytes, no angle brackets
    yt_head = f"{hook}\n\n{credit}\n\nPrompt to recreate it:\n"
    yt_tail = f"\n\n{HASHTAGS} #Shorts"
    yt_prompt = cut(prompt, 4900 - nb(yt_head) - nb(yt_tail), nb)
    youtube = re.sub(r"[<>]", "", yt_head + yt_prompt + yt_tail)
    # Facebook: long text is fine
    facebook = f"{hook}\n\n{credit}\n\nPrompt to recreate it ⤵️\n{prompt}\n\n{HASHTAGS}"
    # Instagram: max 2200 characters, 30 hashtags
    ig_head = f"{hook}\n\n{credit}\n\nPrompt ⤵️\n"
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


def vertical(video, workdir):
    """A 9:16 copy for YouTube/Facebook/Instagram (zoom 100: the whole video, black bars above and below,
    nothing cropped). Videos that are already 9:16 are returned unchanged."""
    w, h = size(video)
    if h / w >= 1.7:  # already 9:16 (1.78), allow small differences
        return video
    out = os.path.join(workdir, "vertical.mp4")
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", vf, "-map", "0:v", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out], check=True)
    return out


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

NICE = {"youtube": "YouTube", "facebook": "Facebook", "instagram": "Instagram"}
POSTERS = {"youtube": youtube, "facebook": facebook, "instagram": instagram}


def post_all(video, t, done=None, video_url=None, log=print):
    """Post to every platform that has secrets and isn't done yet. One failure doesn't stop the others."""
    done = dict(done or {})
    for name in enabled():
        if isinstance(done.get(name), dict) and done[name].get("id"):
            continue
        try:
            res = instagram(video, t, video_url) if name == "instagram" else POSTERS[name](video, t)
            done[name] = res
            log(f"{NICE[name]}: posted {res.get('url', '')}{res.get('note', '')}")
        except Exception as e:  # keep going with the next platform
            done[name] = {"error": str(e)[:500], "at": time.strftime("%Y-%m-%d %H:%M")}
            log(f"{NICE[name]}: FAILED: {str(e)[:500]}")
    return done


def check_accounts(log=print):
    """Confirm each platform's keys work, without posting. Returns True if all enabled ones are fine."""
    good = True
    names = enabled()
    for name in ("youtube", "facebook", "instagram"):
        if name not in names:
            log(f"{NICE[name]}: skipped (secrets not added)")
    for name in names:
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
            else:
                who = "@" + ok(requests.get(f"{GRAPH}/{env('IG_USER_ID')}", params={"fields": "username",
                               "access_token": env("FB_PAGE_TOKEN")}, timeout=30), "Instagram account")["username"]
            log(f"{NICE[name]}: keys OK, posting as {who}")
        except Exception as e:
            good = False
            log(f"{NICE[name]}: keys NOT working: {str(e)[:400]}")
    return good


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        sys.exit(0 if check_accounts() else 1)
    print(__doc__)
