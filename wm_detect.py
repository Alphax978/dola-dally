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
PERSIST = 0.7     # an edge pixel must be present in this share of frames


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


def _text_line(mask, W):
    """Largest group of small blobs sharing one line: (count, horizontal span as share of width)."""
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(closed)
    blobs = [k for k in range(1, n) if 5 <= stats[k, cv2.CC_STAT_AREA] <= 0.03 * mask.size
             and stats[k, cv2.CC_STAT_HEIGHT] <= 0.6 * mask.shape[0]]
    if not blobs:
        return 0, 0.0, 0
    ys = np.array([cent[k][1] for k in blobs])
    xs = np.array([cent[k][0] for k in blobs])
    best, span = 0, 0.0
    for y in ys:
        line = np.abs(ys - y) <= max(4, 0.08 * mask.shape[0])
        if line.sum() > best:
            best, span = int(line.sum()), float((xs[line].max() - xs[line].min()) / W)
    area = int(sum(stats[k, cv2.CC_STAT_AREA] for k in blobs))
    return best, span, area


def analyse(frames, ignore=None):
    """frames: list of BGR images. ignore: optional (x0, y0, x1, y1) fractions to mask out.

    Two independent signals, scanned across the WHOLE frame in overlapping horizontal bands:
      A) edges that stay put in almost every frame (outlines of text/logos), and
      B) pixels whose brightness barely changes while the picture around them changes a lot
         (the body of a solid or semi-transparent overlay).
    A band is flagged when either signal forms a text/logo-like group and clearly stands out
    from the rest of the frame (so a locked-off camera doesn't trigger it).
    """
    if len(frames) < 6:
        return False, {"reason": "too few frames"}
    h0, w0 = frames[0].shape[:2]
    H = int(round(h0 * W / w0))
    edges, grays = [], []
    for f in frames:
        g = cv2.cvtColor(cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        grays.append(g)
        edges.append(cv2.Canny(g, 25, 80) > 0)
    stack = np.stack(grays).astype(np.float32)
    std = np.std(stack, axis=0)
    motion = float(std.mean())
    persist = np.mean(edges, axis=0)
    sig_a = (persist >= PERSIST).astype(np.uint8)
    # B: locally still pixels inside a moving neighbourhood
    around = cv2.blur(std, (41, 41))
    sig_b = ((std < 0.55 * around) & (around > 12)).astype(np.uint8)
    sig_b = cv2.morphologyEx(sig_b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    if ignore:
        x0, y0, x1, y1 = ignore
        for m in (sig_a, sig_b):
            m[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = 0

    bands = [(a / 10, min(1.0, a / 10 + 0.2)) for a in range(0, 9)]
    fracs_a = [float(sig_a[int(a * H):int(b * H)].mean()) for a, b in bands]
    fracs_b = [float(sig_b[int(a * H):int(b * H)].mean()) for a, b in bands]
    base_a, base_b = float(np.median(fracs_a)), float(np.median(fracs_b))
    found, best = False, {}
    for (a, b), fa, fb in zip(bands, fracs_a, fracs_b):
        if motion < 4:
            break  # an almost frozen clip: can't tell overlay from scene
        na, span_a, _ = _text_line(sig_a[int(a * H):int(b * H)], W)
        nb, span_b, area_b = _text_line(sig_b[int(a * H):int(b * H)], W)
        # relative test: this band stands out from the rest of the frame
        hit_a = fa >= 0.001 and na >= 2 and span_a >= 0.025 and fa >= 2.5 * base_a
        hit_b = fb >= 0.0012 and nb >= 2 and span_b >= 0.025 and fb >= 2.5 * base_b and area_b >= 20
        # absolute test: a clear line of fixed text/logo, whatever the rest of the frame does
        hit_a = hit_a or (fa >= 0.003 and na >= 3 and span_a >= 0.06)
        hit_b = hit_b or (fb >= 0.004 and nb >= 3 and span_b >= 0.06 and area_b >= 40)
        score = max(fa / (base_a + 1e-4), fb / (base_b + 1e-4))
        if hit_a or hit_b:
            found = True
        if not best or score > best["score"]:
            best = {"band": f"{a:.1f}-{b:.1f}", "score": round(score, 1), "edges": (round(fa, 4), na, round(span_a, 3)),
                    "still": (round(fb, 4), nb, round(span_b, 3)), "hit": bool(hit_a or hit_b)}
    return found, {**best, "motion": round(motion, 1)}


def has_watermark(path):
    return analyse(read_frames(path))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        wm, info = has_watermark(p)
        print(f"{'WATERMARK' if wm else 'clean    '}  {info}  {p}")
