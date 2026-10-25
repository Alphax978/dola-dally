#!/usr/bin/env python3
"""voice.py: read lines aloud with Kokoro (free, runs on this machine). Kept in its own process (and, in the
posting job, its own Python environment) so its libraries can't clash with the posting tools.

  python3 voice.py JOBS.json      JOBS.json = [{"text": "...", "out": "/path/line.wav"}, ...]
"""
import json
import sys

import numpy as np
import soundfile as sf
from kokoro import KPipeline

jobs = json.load(open(sys.argv[1], encoding="utf-8"))
pipe = KPipeline(lang_code="a")
for j in jobs:
    audio = np.concatenate([a for _, _, a in pipe(j["text"], voice="af_heart", speed=1.0)])
    sf.write(j["out"], audio, 24000)
    print("ok", j["out"], flush=True)
