#!/usr/bin/env python3
"""dola_finish.py: remove the "Dola AI" watermark from 1 or 2 clips and, if 2, join them.

Usage:  python3 dola_finish.py PART1.mp4 [PART2.mp4] -o final.mp4
Keeps the original resolution and framing (no crop, no zoom). Needs ffmpeg + opencv-python.
"""
import argparse, os, subprocess, sys, tempfile
import cv2
import numpy as np

# Where the Dola AI watermark sits, as fractions of the frame (measured on a 1280x720 clip:
# x 1119-1251, y 661-693). We search a slightly larger box around it.
WM_BOX = (0.855, 0.995, 0.885, 0.990)  # x0, x1, y0, y1


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(out[0]), int(out[1])
    num, den = out[2].split("/")
    fps = float(num) / float(den or 1)
    has_audio = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                     "stream=index", "-of", "csv=p=0", path],
                                    capture_output=True, text=True).stdout.strip())
    return w, h, fps, has_audio


def find_mask(path, w, h):
    """Watermark = pixels in the corner box that stay bright in every frame."""
    x0, x1 = int(WM_BOX[0] * w), int(WM_BOX[1] * w)
    y0, y1 = int(WM_BOX[2] * h), int(WM_BOX[3] * h)
    cap = cv2.VideoCapture(path)
    mins = None
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % 2 == 0:
            g = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
            mins = g if mins is None else np.minimum(mins, g)
        i += 1
    cap.release()
    if mins is None:
        sys.exit(f"Couldn't read frames from {path}")
    mask = (mins > 90).astype(np.uint8) * 255
    # drop tiny specks, keep the text
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros_like(mask)
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] >= 15:
            keep[lab == k] = 255
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    found = int((keep > 0).sum())
    full = np.zeros((h, w), np.uint8)
    full[y0:y1, x0:x1] = keep
    return full, found, (x0, x1, y0, y1)


def clean(path, out_path):
    w, h, fps, has_audio = probe(path)
    mask, found, (x0, x1, y0, y1) = find_mask(path, w, h)
    print(f"{os.path.basename(path)}: {w}x{h} @ {fps:g}fps, watermark pixels found: {found}")
    if found < 200:
        print("  No clear watermark found; copying the clip through unchanged.")
    # work on a padded box around the watermark for speed and good context
    P = 24
    bx0, bx1, by0, by1 = max(0, x0 - P), w, max(0, y0 - P), h
    sub_mask = mask[by0:by1, bx0:bx1]
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
           "-r", f"{fps:g}", "-i", "-", "-i", path, "-map", "0:v"]
    cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "192k"] if has_audio else []
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-shortest", out_path]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cap = cv2.VideoCapture(path)
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if found >= 200:
            roi = f[by0:by1, bx0:bx1]
            f[by0:by1, bx0:bx1] = cv2.inpaint(roi, sub_mask, 6, cv2.INPAINT_TELEA)
        enc.stdin.write(f.tobytes())
    cap.release()
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit(f"Encoding failed for {path}")
    return w, h, fps, has_audio


def join(parts, out_path, w, h, fps):
    """Hard-cut join, matched to part 1's size and frame rate. Adds silence if a part has no audio."""
    inputs, filters, labels = [], [], ""
    for i, (p, has_audio) in enumerate(parts):
        inputs += ["-i", p]
        filters.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                       f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:g},format=yuv420p[v{i}]")
        if has_audio:
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                  "csv=p=0", p], capture_output=True, text=True).stdout.strip()
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur}[a{i}]")
        labels += f"[v{i}][a{i}]"
    filters.append(f"{labels}concat=n={len(parts)}:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    out_path], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="Part 1 first, then Part 2")
    ap.add_argument("-o", "--output", default="final.mp4")
    a = ap.parse_args()
    if len(a.clips) > 3:
        sys.exit("Give at most 3 clips.")
    tmp = tempfile.mkdtemp()
    cleaned = []
    for i, c in enumerate(a.clips):
        out = a.output if len(a.clips) == 1 else os.path.join(tmp, f"part{i + 1}.mp4")
        info = clean(c, out)
        cleaned.append((out, info))
    if len(cleaned) > 1:
        w, h, fps, _ = cleaned[0][1]
        join([(p, info[3]) for p, info in cleaned], a.output, w, h, fps)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        a.output], capture_output=True, text=True).stdout.strip()
    print(f"Done: {a.output} ({float(d):.1f}s)")


if __name__ == "__main__":
    main()
