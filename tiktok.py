#!/usr/bin/env python3
"""
tiktok.py: TikTok sign-in and posting for dola-daily (Content Posting API).

Secrets: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET (from developers.tiktok.com, sandbox or production).
The sign-in (refresh token) is kept in tiktok_token.enc, encrypted with a key made from
TIKTOK_CLIENT_SECRET, so it's safe in the public repo and survives TikTok's token rotation.

Modes (repo variable TIKTOK_MODE):
  buffer           public and automatic through Buffer (see buffer_feed.py)
  draft  (default) video goes to your TikTok inbox; you tap Post in the app (public right away)
  direct           posts straight to your profile; private until TikTok audits the app

  python3 tiktok.py --connect CODE    one time: swap the sign-in code for a saved token
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time

import requests

API = "https://open.tiktokapis.com/v2"
ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(ROOT, "tiktok_token.enc")
REDIRECT_URI = "https://alphax978.github.io/dola-dally/"


class TikTokError(Exception):
    pass


def env(name):
    return os.environ.get(name, "").strip()


def configured():
    return bool(env("TIKTOK_CLIENT_KEY") and env("TIKTOK_CLIENT_SECRET") and os.path.exists(TOKEN_FILE))


def mode():
    m = env("TIKTOK_MODE").lower()
    return m if m in ("direct", "buffer") else "draft"


# ---------- token storage ----------

def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(("dola-daily:" + env("TIKTOK_CLIENT_SECRET")).encode()).digest())
    return Fernet(key)


def _save(data):
    with open(TOKEN_FILE, "wb") as f:
        f.write(_fernet().encrypt(json.dumps(data).encode()))
    if os.environ.get("GITHUB_ACTIONS"):  # keep the newest token in the repo
        run = lambda *c: subprocess.run(["git", *c], cwd=ROOT, capture_output=True, text=True)
        run("config", "user.name", "dola-daily bot")
        run("config", "user.email", "dola-daily@users.noreply.github.com")
        run("add", "tiktok_token.enc")
        if run("diff", "--cached", "--quiet").returncode != 0:
            run("commit", "-m", "TikTok sign-in updated [skip ci]")
            for _ in range(3):
                run("pull", "--rebase", "-q")
                if run("push", "-q").returncode == 0:
                    break
                time.sleep(5)


def _load():
    with open(TOKEN_FILE, "rb") as f:
        return json.loads(_fernet().decrypt(f.read()))


def _token_call(data):
    r = requests.post(f"{API}/oauth/token/", timeout=30, data={
        "client_key": env("TIKTOK_CLIENT_KEY"), "client_secret": env("TIKTOK_CLIENT_SECRET"), **data},
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    j = r.json() if r.content else {}
    if r.status_code >= 300 or "access_token" not in j:
        raise TikTokError(f"TikTok sign-in failed: {r.status_code} {json.dumps(j)[:400]}")
    return j


def connect(code):
    """One time: exchange the code from the sign-in page for tokens and save them."""
    j = _token_call({"code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI})
    _save({"refresh_token": j["refresh_token"], "open_id": j.get("open_id"), "scope": j.get("scope"),
           "saved": time.strftime("%Y-%m-%d %H:%M")})
    return j["access_token"], j.get("scope", "")


def access_token():
    d = _load()
    j = _token_call({"grant_type": "refresh_token", "refresh_token": d["refresh_token"]})
    if j.get("refresh_token") and j["refresh_token"] != d["refresh_token"]:
        d.update(refresh_token=j["refresh_token"], saved=time.strftime("%Y-%m-%d %H:%M"))
        _save(d)
    return j["access_token"]


# ---------- API ----------

def call(token, method, path, body=None, params=None):
    r = requests.request(method, f"{API}{path}", params=params, json=body, timeout=60, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    j = r.json() if r.content else {}
    err = (j.get("error") or {})
    if r.status_code >= 300 or err.get("code") not in (None, "", "ok"):
        raise TikTokError(f"TikTok {path}: {r.status_code} {err.get('code')} {err.get('message', '')[:300]}")
    return j.get("data") or {}


def who(token):
    u = call(token, "GET", "/user/info/", params={"fields": "open_id,display_name"}).get("user", {})
    return u.get("display_name") or u.get("open_id") or "your account"


def _upload(upload_url, video):
    size = os.path.getsize(video)
    with open(video, "rb") as f:
        r = requests.put(upload_url, data=f, timeout=900, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if r.status_code >= 300:
        raise TikTokError(f"TikTok upload: {r.status_code} {r.text[:300]}")


def post(video, caption):
    """Send the video to TikTok (drafts inbox or direct post). Returns {'id', 'url', 'note'}."""
    size = os.path.getsize(video)
    if size > 64 * 1024 * 1024:
        raise TikTokError("video is over 64 MB; too big for a single upload")
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    token = access_token()
    if mode() == "direct":
        info = call(token, "POST", "/post/publish/creator_info/query/", body={})
        options = info.get("privacy_level_options") or ["SELF_ONLY"]
        privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else options[0]
        data = call(token, "POST", "/post/publish/video/init/", body={
            "post_info": {"title": caption[:2200], "privacy_level": privacy, "disable_comment": False,
                          "disable_duet": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000,
                          "is_aigc": True},
            "source_info": source})
    else:
        privacy = None
        data = call(token, "POST", "/post/publish/inbox/video/init/", body={"source_info": source})
    publish_id = data["publish_id"]
    _upload(data["upload_url"], video)
    status = ""
    for _ in range(40):  # TikTok processes the upload (usually under a minute)
        time.sleep(6)
        st = call(token, "POST", "/post/publish/status/fetch/", body={"publish_id": publish_id})
        status = st.get("status", "")
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            break
        if status == "FAILED":
            raise TikTokError(f"TikTok couldn't process the video: {st.get('fail_reason')}")
    if mode() == "direct":
        note = "" if privacy == "PUBLIC_TO_EVERYONE" else f" (posted as {privacy}: TikTok keeps it private until the app is audited)"
    else:
        note = " (in your TikTok inbox: open TikTok, tap the notification and Post; copy the caption at https://alphax978.github.io/dola-dally/tiktok.html)"
    return {"id": publish_id, "url": "", "status": status, "note": note}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--connect":
        tok, scope = connect(sys.argv[2].strip())
        print(f"Connected to TikTok as {who(tok)} (permissions: {scope})")
    else:
        print(__doc__)
