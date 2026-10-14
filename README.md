# dola-daily

Prepares one AI video a day.

Every morning at about 7:00 AM (Nepal time) GitHub Actions:

1. picks a random video from the YouMind Seedance 2.5 gallery and saves frame grids of it (`prepare_frames.py`)
2. writes replica prompts for it with Claude (`write_prompts.py`, needs the `ANTHROPIC_API_KEY` secret)

Results land in `days/<date>/`:

- `prompts.md`: the prompts, easy to read
- `prompts.json`: the same, for scripts
- `<video>/`: frame grids and details of the original
