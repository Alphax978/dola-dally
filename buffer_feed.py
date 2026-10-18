#!/usr/bin/env python3
"""
buffer_feed.py: TikTok through Buffer (TIKTOK_MODE=buffer).

GitHub can't post publicly to TikTok until TikTok audits our app, but Buffer can. So:
  1. the 9:16 video is uploaded to a GitHub Release (a public direct download link, outside the repo history)
  2. a new item (caption + video link) is added to docs/tiktok/feed.xml, published at
     https://alphax978.github.io/dola-dally/tiktok/feed.xml
  3. a Zapier Zap (RSS by Zapier -> Buffer) sees the new item and has Buffer post it to TikTok.
"""
import datetime as dt
import html
import os
import time

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(ROOT, "docs", "tiktok", "feed.xml")
SITE = "https://alphax978.github.io/dola-dally/"
TAG = "tiktok-videos"
KEEP_DAYS = 7


class FeedError(Exception):
    pass


def _gh():
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        raise FeedError("needs GITHUB_REPOSITORY and GITHUB_TOKEN (runs on GitHub Actions)")
    return repo, {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _release(repo, h):
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{TAG}", headers=h, timeout=30)
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"https://api.github.com/repos/{repo}/releases", headers=h, timeout=30, json={
        "tag_name": TAG, "target_commitish": "main", "name": "TikTok videos",
        "body": "9:16 videos for TikTok (via Buffer). Old files are removed automatically."})
    if r.status_code >= 300:
        raise FeedError(f"couldn't create the release: {r.status_code} {r.text[:300]}")
    return r.json()


def upload(video, name):
    """Upload the video to the release; returns its public download link. Removes files older than KEEP_DAYS."""
    repo, h = _gh()
    rel = _release(repo, h)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=KEEP_DAYS)
    for a in rel.get("assets", []):
        old = dt.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00")) < cutoff
        if a["name"] == name or old:
            requests.delete(a["url"], headers=h, timeout=30)
    with open(video, "rb") as f:
        r = requests.post(f"https://uploads.github.com/repos/{repo}/releases/{rel['id']}/assets",
                          params={"name": name}, data=f, timeout=600,
                          headers={**h, "Content-Type": "video/mp4"})
    if r.status_code >= 300:
        raise FeedError(f"video upload failed: {r.status_code} {r.text[:300]}")
    return r.json()["browser_download_url"]


def _items():
    """Existing feed items as dicts (we wrote the file, so a simple parse is enough)."""
    import re
    if not os.path.exists(FEED):
        return []
    out = []
    for block in re.findall(r"<item>(.*?)</item>", open(FEED, encoding="utf-8").read(), re.S):
        get = lambda tag: html.unescape((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S) or [None, ""])[1])
        enc = re.search(r'<enclosure url="([^"]+)"[^>]*length="(\d+)"', block)
        out.append({"guid": get("guid"), "title": get("title"), "description": get("description"),
                    "link": get("link"), "pubDate": get("pubDate"),
                    "url": html.unescape(enc.group(1)) if enc else get("link"), "size": enc.group(2) if enc else "0"})
    return out


def add_item(key, title, caption, url, size):
    items = [i for i in _items() if i["guid"] != key]
    items.insert(0, {"guid": key, "title": title, "description": caption, "link": url, "url": url, "size": str(size),
                     "pubDate": time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())})
    e = html.escape
    body = "".join(
        f"<item><title>{e(i['title'])}</title><link>{e(i['link'])}</link>"
        f"<description>{e(i['description'])}</description>"
        f'<enclosure url="{e(i["url"])}" length="{i["size"]}" type="video/mp4"/>'
        f'<guid isPermaLink="false">{e(i["guid"])}</guid><pubDate>{i["pubDate"]}</pubDate></item>\n'
        for i in items[:10])
    os.makedirs(os.path.dirname(FEED), exist_ok=True)
    with open(FEED, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
                f"<title>Mira AI TikTok queue</title><link>{SITE}</link>"
                "<description>New videos for Buffer to post to TikTok</description>\n" + body + "</channel></rss>\n")


def publish(video, caption, key, title):
    """Upload + add to the feed. Returns {'id', 'url', 'note'} like the other platforms."""
    url = upload(video, f"{key}.mp4")
    add_item(key, title, caption, url, os.path.getsize(video))
    return {"id": key, "url": url,
            "note": " (queued for Buffer: Zapier picks it up from the feed within ~15 min)"}
