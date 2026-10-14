# dola-daily

Prepares one AI video a day for the Dola AI X account.

Every morning at about 5:00 AM Nepal time, a GitHub Action (`.github/workflows/prepare.yml`) runs `prepare_frames.py`, which:

1. Opens the YouMind Seedance 2.5 prompt gallery and picks 3 random videos not used before.
2. Downloads each video and saves timestamped frame grids (one frame every 0.5 s) and text strips (for subtitles) under `days/<date>/<video>/`, plus `meta.json` with the title, links, duration and cut times. The videos themselves are not stored.
3. Records the videos in `used.json` so none repeats, and deletes days older than a week.

At about 6:26 AM, a Claude scheduled task reads today's frames, writes frame-accurate Dola AI prompts, and sends them to the phone.

To run it by hand: **Actions → Prepare daily video frames → Run workflow**.
