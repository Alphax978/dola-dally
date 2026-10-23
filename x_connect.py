#!/usr/bin/env python3
"""
x_connect.py: let our X app post as a different X account (e.g. a new @miraai_creates).

The app keys (X_API_KEY, X_API_SECRET) stay the same; the new account grants the app access once
with a PIN and its access token is saved to x_token.enc, encrypted with a key made from
X_API_SECRET, so it's safe in the public repo. post_to_x.py uses it instead of the
X_ACCESS_TOKEN/X_ACCESS_SECRET secrets when it exists.

  python3 x_connect.py --start       prints the link to open while signed in to the new account
  python3 x_connect.py --pin 1234567 finishes with the PIN X shows after you press Authorize
"""
import base64
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
REQUEST_FILE = os.path.join(ROOT, "x_request.enc")
TOKEN_FILE = os.path.join(ROOT, "x_token.enc")
API = "https://api.x.com"


def _env(k):
    v = os.environ.get(k, "").strip()
    if not v:
        sys.exit(f"{k} is missing")
    return v


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("dola-daily-x:" + _env("X_API_SECRET")).encode()).digest()))


def save(path, data):
    with open(path, "wb") as f:
        f.write(_fernet().encrypt(json.dumps(data).encode()))


def load(path):
    with open(path, "rb") as f:
        return json.loads(_fernet().decrypt(f.read()))


def saved_token():
    """(token, secret, screen_name) of the connected account, or None."""
    if not os.path.exists(TOKEN_FILE) or not os.environ.get("X_API_SECRET"):
        return None
    d = load(TOKEN_FILE)
    return d["token"], d["secret"], d.get("screen_name")


def summary(text):
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def start():
    from requests_oauthlib import OAuth1Session
    s = OAuth1Session(_env("X_API_KEY"), client_secret=_env("X_API_SECRET"), callback_uri="oob")
    r = s.fetch_request_token(f"{API}/oauth/request_token")
    save(REQUEST_FILE, {"token": r["oauth_token"], "secret": r["oauth_token_secret"], "at": time.time()})
    url = f"{API}/oauth/authorize?oauth_token={r['oauth_token']}"
    with open(os.path.join(ROOT, "x_connect_link.txt"), "w") as f:  # only the public half; useless without your approval
        f.write(url + "\n")
    summary(f"## Connect the new X account\n\n1. Make sure you're signed in to the NEW account on x.com.\n"
            f"2. Open: {url}\n3. Press **Authorize app** and copy the PIN it shows.\n4. Send the PIN to Claude.")


def finish(pin):
    from requests_oauthlib import OAuth1Session
    if not os.path.exists(REQUEST_FILE):
        sys.exit("Start first (run without a PIN).")
    req = load(REQUEST_FILE)
    s = OAuth1Session(_env("X_API_KEY"), client_secret=_env("X_API_SECRET"),
                      resource_owner_key=req["token"], resource_owner_secret=req["secret"], verifier=pin.strip())
    r = s.fetch_access_token(f"{API}/oauth/access_token")
    save(TOKEN_FILE, {"token": r["oauth_token"], "secret": r["oauth_token_secret"],
                      "screen_name": r.get("screen_name"), "user_id": r.get("user_id"),
                      "saved": time.strftime("%Y-%m-%d %H:%M")})
    os.remove(REQUEST_FILE)
    link = os.path.join(ROOT, "x_connect_link.txt")
    if os.path.exists(link):
        os.remove(link)
    summary(f"Connected: the automation now posts to X as @{r.get('screen_name')}")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--start":
        start()
    elif len(sys.argv) == 3 and sys.argv[1] == "--pin":
        finish(sys.argv[2])
    else:
        print(__doc__)
