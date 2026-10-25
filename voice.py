#!/usr/bin/env python3
"""voice.py: read lines aloud with Kokoro (free, runs on this machine). Kept in its own process (and, in the
posting job, its own Python environment) so its libraries can't clash with the posting tools.
Each line is done on its own: a line Kokoro can't read is reported and left out (it gets the backup voice).

  python3 voice.py JOBS.json      JOBS.json = [{"text": "...", "out": "/path/line.wav"}, ...]
"""
import json
import sys
import traceback

import numpy as np
import soundfile as sf
from kokoro import KPipeline

jobs = json.load(open(sys.argv[1], encoding="utf-8"))
pipe = KPipeline(lang_code="a")
for j in jobs:
    try:
        audio = np.concatenate([a for _, _, a in pipe(j["text"], voice="af_heart", speed=1.0)])
        sf.write(j["out"], audio, 24000)
        print("ok", j["out"], flush=True)
    except Exception as e:
        tb = traceback.format_exc().strip().splitlines()
        where = next((l.strip() for l in reversed(tb) if l.strip().startswith("File ")), "")
        print(f"FAIL {j['text'][:80]!r}: {type(e).__name__}: {e} at {where}", flush=True)
