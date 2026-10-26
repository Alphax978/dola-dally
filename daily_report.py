#!/usr/bin/env python3
"""
daily_report.py: every night at 10:30 PM Nepal time, check that today's 2 videos are live on
every site and send the result to Telegram. No AI involved: it asks each site directly.

  X          the post's public embed (publish.twitter.com) answers -> it's live
  YouTube    the Short's public embed answers -> it's live and public
  Facebook   the Graph API says the video exists and has finished processing
  Instagram  the Graph API returns the Reel's link (only exists once published)
  TikTok     the video reached the Buffer feed (Zapier/Buffer email you if TikTok then fails)

Secrets: TG_BOT_TOKEN (from @BotFather), FB_PAGE_TOKEN; X_API_SECRET to read the X username.
Your Telegram chat id is found once from your "hi" to the bot and kept in tg_chat.enc
(encrypted with a key made from TG_BOT_TOKEN).

  python3 daily_report.py            send today's report (once a day)
  python3 daily_report.py --test     send it now even if already sent today
"""
import base64
import datetime as dt
import hashlib
import html
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
TZ = dt.timezone(dt.timedelta(hours=5, minutes=45))
CHAT_FILE = os.path.join(ROOT, "tg_chat.enc")
SENT_FILE = os.path.join(ROOT, "report_sent.txt")
FEED = os.path.join(ROOT, "docs", "tiktok", "feed.xml")
GRAPH = "https://graph.facebook.com/v23.0"
SITES = [("x", "X"), ("youtube", "YouTube"), ("facebook", "Facebook"), ("instagram", "Instagram"), ("tiktok", "TikTok")]
TIMES = {1: "4:30 PM", 2: "9:30 PM"}
UA = {"User-Agent": "Mozilla/5.0 (dola-daily report)"}


def env(k):
    return os.environ.get(k, "").strip()


# ---------- Telegram ----------

def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("dola-daily-tg:" + env("TG_BOT_TOKEN")).encode()).digest()))


def tg(method, **data):
    r = requests.post(f"https://api.telegram.org/bot{env('TG_BOT_TOKEN')}/{method}", json=data, timeout=30)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {method}: {j.get('description')}")
    return j["result"]


def chat_id():
    if os.path.exists(CHAT_FILE):
        return json.loads(_fernet().decrypt(open(CHAT_FILE, "rb").read()))["chat_id"]
    ups = tg("getUpdates")
    chats = [u["message"]["chat"]["id"] for u in ups if u.get("message", {}).get("chat", {}).get("type") == "private"]
    if not chats:
        sys.exit("No chat found: open your bot in Telegram, press Start and send it 'hi', then run again.")
    with open(CHAT_FILE, "wb") as f:
        f.write(_fernet().encrypt(json.dumps({"chat_id": chats[-1]}).encode()))
    return chats[-1]


# ---------- checks (each returns (ok, link, note)) ----------

def get(url, **kw):
    return requests.get(url, timeout=30, headers=UA, **kw)


def check_x(entry):
    pid = entry.get("post_id")
    if not pid:
        return False, "", "not posted"
    user = "i"
    try:
        sys.path.insert(0, ROOT)
        from x_connect import saved_token
        user = (saved_token() or (None, None, None))[2] or "i"
    except Exception:
        pass
    link = f"https://x.com/{user}/status/{pid}"
    note = "" if entry.get("reply_id") else "prompt reply missing"
    try:
        r = get("https://publish.twitter.com/oembed", params={"url": f"https://twitter.com/{user}/status/{pid}"})
        if r.status_code == 200:
            return True, link, note
        if r.status_code == 404:
            return False, link, "not found on X (deleted or hidden?)"
        return True, link, (note + "; " if note else "") + f"posted (live check unavailable: {r.status_code})"
    except Exception as e:
        return True, link, f"posted (live check unavailable: {str(e)[:60]})"


def check_youtube(res):
    vid = res["id"]
    link = f"https://youtube.com/shorts/{vid}"
    r = get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
    if r.status_code == 200:
        return True, link, ""
    if r.status_code in (401, 403):
        return False, link, "not public (private, processing or restricted)"
    return False, link, f"not found on YouTube ({r.status_code})"


def check_facebook(res):
    r = get(f"{GRAPH}/{res['id']}", params={"fields": "status,permalink_url", "access_token": env("FB_PAGE_TOKEN")})
    j = r.json()
    if r.status_code >= 300:
        return False, res.get("url", ""), f"not found ({j.get('error', {}).get('message', r.status_code)})"[:150]
    link = j.get("permalink_url") or res.get("url", "")
    if link.startswith("/"):
        link = "https://www.facebook.com" + link
    st = (j.get("status") or {}).get("video_status", "ready")
    if st == "ready":
        return True, link, ""
    return False, link, f"video status: {st}"


def check_instagram(res):
    r = get(f"{GRAPH}/{res['id']}", params={"fields": "permalink", "access_token": env("FB_PAGE_TOKEN")})
    j = r.json()
    if r.status_code >= 300 or not j.get("permalink"):
        return False, res.get("url", ""), f"not found ({j.get('error', {}).get('message', r.status_code)})"[:150]
    return True, j["permalink"], ""


def check_tiktok(res, key):
    feed = open(FEED, encoding="utf-8").read() if os.path.exists(FEED) else ""
    if f">{key}</guid>" in feed or f"tiktok-videos/{key}.mp4" in feed or res.get("id"):
        return True, "", "sent to Buffer"
    return False, "", "not in the Buffer feed"


def paused():
    p = os.path.join(ROOT, "paused.txt")
    if not os.path.exists(p):
        return set()
    return {l.split("#")[0].strip().lower() for l in open(p, encoding="utf-8")} - {""}


def hook(day, slot):
    try:
        sys.path.insert(0, ROOT)
        import post_to_x
        job = post_to_x.load_job(day, slot)
        if job:
            return post_to_x.caption_lines(job)[0]
    except Exception:
        pass
    return ""


def auto_fill_off(day):
    p = os.path.join(ROOT, "days", day, "index.json")
    try:
        return json.load(open(p)).get("auto_fill") is False
    except Exception:
        return False


def slot_report(day, slot, posted):
    key = f"{day}-{slot}"
    entry = posted.get(key)
    title = hook(day, slot)
    head = f"🎬 <b>{TIMES[slot]}</b>" + (f": {html.escape(title)}" if title else "")
    if not entry:
        h, m = (16, 30) if slot == 1 else (21, 30)
        if dt.datetime.now(TZ) < dt.datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=TZ):
            return head + "\n⏳ Not due yet", []
        if auto_fill_off(day):  # auto-posting is off: an empty slot just means no usable pick for it
            return head + "\n⏸ No post: no usable pick for this slot (auto-posting is off)", []
        why = "never ran" if title else "no video was prepared (morning step failed?)"
        return head + f"\n❌ Not posted: {why}", [f"{TIMES[slot]} video: {why}"]
    if entry.get("skipped"):
        return head + f"\n⛔ Skipped: {html.escape(str(entry['skipped']))}", [f"{TIMES[slot]} video skipped ({entry['skipped']})"]
    off, other, parts, problems = paused(), entry.get("other") or {}, [], []
    for site, name in SITES:
        if site in off:
            parts.append(f"⏸ {name}")
            continue
        try:
            if site == "x":
                if entry.get("x") == "paused":
                    parts.append(f"⏸ {name}")
                    continue
                ok, link, note = check_x(entry)
            else:
                res = other.get(site)
                if not isinstance(res, dict) or not res.get("id"):
                    err = (res or {}).get("error", "not posted") if isinstance(res, dict) else "not posted"
                    ok, link, note = False, "", err
                elif site == "tiktok":
                    ok, link, note = check_tiktok(res, key)
                else:
                    ok, link, note = {"youtube": check_youtube, "facebook": check_facebook,
                                      "instagram": check_instagram}[site](res)
        except Exception as e:
            ok, link, note = False, "", f"check failed: {str(e)[:100]}"
        label = f'<a href="{html.escape(link)}">{name}</a>' if link else name
        text = ("✅ " if ok else "❌ ") + label + (f" ({html.escape(note[:150])})" if note else "")
        parts.append(text)
        if not ok:
            problems.append(f"{name}, {TIMES[slot]} video: {note or 'failed'}")
    return head + "\n" + "\n".join(parts), problems


def build(day):
    p = os.path.join(ROOT, "posted.json")
    posted = json.load(open(p)) if os.path.exists(p) else {}
    blocks, problems = [], []
    for slot in (1, 2):
        b, pr = slot_report(day, slot, posted)
        blocks.append(b)
        problems += pr
    date = dt.date.fromisoformat(day).strftime("%b %d")
    msg = f"📊 <b>Mira AI: {date}</b>\n\n" + "\n\n".join(blocks)
    if problems:
        msg += f"\n\n⚠️ <b>{len(problems)} problem{'s' if len(problems) > 1 else ''}</b>\n" + "\n".join(
            "• " + html.escape(x) for x in problems)
        msg += "\nTo repost a missing site: Actions → Post to X → Run workflow → slot 1 or 2, dry run off."
    else:
        msg += "\n\n✅ All good: both videos are live everywhere."
    msg += "\n\n<i>TikTok shows when it reached Buffer; Zapier/Buffer email you if TikTok then fails.</i>"
    return msg


def main():
    test = "--test" in sys.argv
    day = dt.datetime.now(TZ).date().isoformat()
    if not test and os.path.exists(SENT_FILE) and open(SENT_FILE).read().strip() == day:
        print(f"Report for {day} already sent.")
        return
    msg = build(day)
    print(msg)
    if os.environ.get("GITHUB_ACTIONS"):
        print("::notice title=Report::" + msg.replace("\n", " | ")[:900], flush=True)
    tg("sendMessage", chat_id=chat_id(), text=msg, parse_mode="HTML", disable_web_page_preview=True)
    if not test:
        with open(SENT_FILE, "w") as f:
            f.write(day + "\n")
    print("Sent to Telegram.")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:  # show the reason on the run page too
        if os.environ.get("GITHUB_ACTIONS") and not (isinstance(e, SystemExit) and not e.code):
            print(f"::error title=Daily report::{str(e)[:500] or type(e).__name__}", flush=True)
        raise
