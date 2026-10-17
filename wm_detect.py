#!/usr/bin/env python3
"""
wm_detect.py: does a video carry a burned-in watermark (an app logo or name like
"Wizstar AI", "Dola AI", "Kling", "Hailuo"...)?

How: a watermark stays at exactly the same spot while the picture under it changes.
We sample frames across the clip, find edges, and look for edges that are present in
almost every frame inside the usual watermark areas (top and bottom bands, corners),
shaped like a line of text or a logo. A static camera also produces steady edges, so
the same test is run on the middle of the frame and the bands must stand out clearly.

  python3 wm_detect.py VIDEO.mp4 [...]     prints a verdict per file
  from wm_detect import has_watermark      -> (bool, details dict)
"""
import sys

import cv2
import numpy as np

W = 480            # analysis width
SAMPLES = 24       # frames sampled across the clip
PERSIST = 0.85     # an edge pixel must be present in this share of frames
BANDS = ((0.0, 0.18), (0.78, 1.0))  # top and bottom bands (fractions of height)


def read_frames(path, n=SAMPLES):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frames = []
    idxs = np.linspace(0, max(total - 1, 0), n).astype(int) if total else range(n * 10)
    for i in idxs:
        if total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if not ok:
            if total:
                continue
            break
        if not total and len(frames) >= n:
            break
        frames.append(f)
    cap.release()
    return frames


def analyse(frames, ignore=None):
    """frames: list of BGR images. ignore: optional (x0, y0, x1, y1) fractions to mask out."""
    if len(frames) < 6:
        return False, {"reason": "too few frames"}
    h0, w0 = frames[0].shape[:2]
    H = int(round(h0 * W / w0))
    edges, grays = [], []
    for f in frames:
        g = cv2.cvtColor(cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        grays.append(g)
        edges.append(cv2.Canny(g, 60, 160) > 0)
    persist = np.mean(edges, axis=0)
    static = (persist >= PERSIST).astype(np.uint8)
    if ignore:
        x0, y0, x1, y1 = ignore
        static[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = 0
    # How much does the picture change? A watermark only means something over a changing picture.
    motion = float(np.mean(np.std(np.stack(grays).astype(np.float32), axis=0)))
    mid = static[int(0.25 * H):int(0.72 * H), :]
    mid_frac = float(mid.mean())

    best = {"band_frac": 0.0, "blobs": 0, "row_span": 0.0}
    found = False
    for a, b in BANDS:
        band = static[int(a * H):int(b * H), :]
        frac = float(band.mean())
        # text and logos = several small edge clusters lined up in a row
        closed = cv2.morphologyEx(band, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        n, lab, stats, cent = cv2.connectedComponentsWithStats(closed)
        blobs = [k for k in range(1, n) if 6 <= stats[k, cv2.CC_STAT_AREA] <= 0.02 * band.size
                 and stats[k, cv2.CC_STAT_HEIGHT] <= 0.5 * band.shape[0]]
        row_span = 0.0
        if blobs:
            ys = np.array([cent[k][1] for k in blobs])
            xs = np.array([cent[k][0] for k in blobs])
            # largest group of blobs sharing roughly one text line
            best_line = 0
            for y in ys:
                line = np.abs(ys - y) <= max(4, 0.06 * band.shape[0])
                if line.sum() > best_line:
                    best_line, span = line.sum(), (xs[line].max() - xs[line].min()) / W
                    row_span = span
            nb = best_line
        else:
            nb = 0
        hit = frac >= 0.0015 and nb >= 2 and row_span >= 0.03 and frac >= 2.5 * mid_frac and motion >= 4
        if frac > best["band_frac"]:
            best = {"band_frac": round(frac, 4), "blobs": int(nb), "row_span": round(float(row_span), 3)}
        found = found or hit
    return found, {**best, "mid_frac": round(mid_frac, 4), "motion": round(motion, 1)}


def has_watermark(path):
    return analyse(read_frames(path))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        wm, info = has_watermark(p)
        print(f"{'WATERMARK' if wm else 'clean    '}  {info}  {p}")
