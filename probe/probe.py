import sys, os, subprocess
sys.path.insert(0, ".")
import prepare_frames as pf
u = "https://cms-assets.youmind.com/media/1792480423831_uux5h8_Vampire-Queen-Flying-Car-Paris-Halloween.mp4"
open("/tmp/v.mp4", "wb").write(pf.get(u, binary=True, timeout=180))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "/tmp/v.mp4", "-vf", "fps=1/3,scale=640:-2,tile=3x3", "-frames:v", "1", "probe/vamp_grid.jpg"])
for t in (2, 12, 22):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", "/tmp/v.mp4", "-frames:v", "1", f"probe/vamp_{t}.jpg"])
