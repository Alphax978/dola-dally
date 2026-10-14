# Morning task (read by the Claude routine "Daily Dola video pick")

Prepare today's AI video for the user to replicate in Dola AI: study a randomly picked video from the YouMind Seedance 2.5 gallery frame by frame, and deliver precise, ready-to-paste Dola AI prompts that recreate it as closely as possible. It should reach the user by about 8:00 AM Nepal time (Asia/Kathmandu). One video per day. The user does not have time to review or iterate: they paste the prompt(s) into Dola, generate, upload the clips back into THIS chat, and post the finished video you return. So the prompts must be precise, complete and work on the first try.

CONTEXT: The user runs Dola AI, an AI video platform built on ByteDance's Seedance 2.0 and Seedance 2.5, and posts one AI video a day on X. In Dola they use New Chat → Pro → Generate Videos. Dola usually generates up to 15 seconds per clip, sometimes 30 seconds, and they get 3 Pro generations a day.
- Original 15 seconds or shorter: ONE prompt ("SINGLE").
- Original longer than 15 seconds (up to ~30s): write BOTH
  - Option A: ONE prompt for the whole video ("FULL 30s"; its real length, max 30.0 s; timecodes from 00:00), and
  - Option B: the same video as TWO parts of 15 seconds or less ("PART 1 of 2", "PART 2 of 2"), each part repeating the full style block and the full character block word for word so the parts match when cut together. Split at a real cut, keep each part at 15.0 seconds or less (trim a fraction of a second from the longest shot if needed), and make each part's timecodes restart at 00:00.
  Options A and B must describe the same characters, look, shots and sound, worded identically where possible.
Every prompt is pasted into Dola exactly as given, so each code block must be complete and ready to paste as-is.

STEP 1 — Get today's frames. A GitHub Action in the user's PUBLIC repo Alphax978/dola-dally runs at ~7:00 AM Nepal time: it picks 2 random unused videos of 30 seconds or less from the gallery and saves, for each, timestamped frame grids (frames_N.jpg: one frame every 0.5 s, 6 per row, each stamped with its time), bottom-of-frame text strips (text_N.jpg: one per second, for subtitles/on-screen text) and meta.json (title, YouMind url, x_post, duration, width, height, cuts = scene-cut times in seconds), listed in days/<YYYY-MM-DD>/index.json (Nepal date).
- The routine has already cloned the repo; <repo> below means that checkout (the folder containing this file). Run git -C <repo> pull first so you have this morning's frames.
- Read days/<today's Nepal date>/index.json. Take the FIRST video in it (they are already in random order). Re-roll to the second one only if the first is sexual or graphically violent (gore). Do NOT skip a video because it features copyrighted characters, a franchise cast, or real people/celebrities; keep it and handle it in STEP 3.
- FALLBACK: if today's index.json is missing or empty (the Action failed or ran late), fetch https://youmind.com/seedance-2-5-prompts/explore with WebFetch, number the items, pick one with python3 -c "import random; print(random.randint(1, N))", and work from the creator's prompt text only (STEP 2's second bullet). Mention in one line at the top of the message that today's prompts are built from the creator's text, not the frames.

STEP 2 — Study the video.
- Read meta.json, then look at EVERY frames_N.jpg and text_N.jpg image with the Read tool. Use the cut times to find each shot's start and end. For each shot note: framing (wide/medium/close-up/POV/selfie), camera movement, who is in it and what they do, setting, light, and any on-screen text or subtitles (the text strips show spoken lines when the video has subtitles). Note the aspect ratio from width/height.
- Also read creator_page.txt in the same folder: GitHub saved the YouMind page's text there (this environment can't open youmind.com), and it contains the creator's original prompt. Use it for intent, dialogue and sound that frames can't show. If that file is missing, try WebFetch on meta.json "url" once; if that fails too, work from the frames alone without mentioning it. Where the frames and the creator's prompt disagree, follow the frames.

STEP 3 — Recreate it faithfully. Keep the original's characters, setting, story, shots, timing, camera moves, look, sound and payoff as close to the original as possible: the goal is a replica, not a reinterpretation. Describe characters from what you actually see in the frames (age, skin, hair, face, clothing, signature details).
The only exception: if the original features copyrighted or franchise characters, or real people/celebrities, replace each of them with an original character who plays the same role in the same scene — new face, hair, build, costume, colors and emblems — and keep everything else identical. Don't carry over any signature look, costume, color scheme, emblem, catchphrase or name from those characters or people, and don't mention them in the prompt.
Leave out burned-in subtitles and on-screen text (AI video garbles text); keep the spoken lines as dialogue instead.
Write each prompt in this format, in its own code block:
- FIRST LINE: "use seedance 2.5 for this", followed by a blank line.
- Header line: "VIDEO PROMPT — <SINGLE | FULL 30s | PART 1 of 2 | PART 2 of 2> — N seconds", aspect ratio (same as the original), the look (realism/style, lens, color grade, light), the camera feel, and pacing.
- CHARACTERS block: concrete, fixed descriptions (age, skin, hair, face, clothing, one or two signature details visible in every shot). LOCATION block if relevant.
- Shot list with timecodes matching the real cuts (SHOT n (00:00.0-00:01.5) — title. what happens, framing, camera move, speed), using specific camera language (push-in, dolly, tracking, crane, whip pan, locked-off, low angle) and physical cause and effect.
- SOUND: per shot or as one block. Name the sounds; use an "upbeat instrumental beat" or similar instead of any real song; say "no music" when there should be none; keep spoken lines short and in double quotes, in the original's language.

STEP 4 — Save the prompts to GitHub for Dola's scheduled task (it reads them from a fixed link a little later).
- In <repo>: first run git fetch origin && git checkout -B main origin/main (work directly on main, never on a claude/ branch), then write these files (Nepal date for <date>):
  - prompts/today.md — exactly this layout and nothing else:
      DATE: <YYYY-MM-DD>
      STATUS: READY
      TITLE: <short title>
      LENGTH: <N> seconds, <aspect ratio>
      (blank line)
      MAIN PROMPT — generate ONE video from everything between the two lines below:
      ----- START -----
      <the FULL 30s prompt (Option A), or the SINGLE prompt for a video of 15 s or less, exactly as in the message>
      ----- END -----
  - prompts/today-parts.md — only for videos longer than 15 s: same DATE/STATUS/TITLE lines, then "PART 1 (generate as its own video):" with ----- START -----/----- END ----- around Part 1, then the same for PART 2.  For videos of 15 s or less, write "No parts today (single prompt)." instead.
  - prompts/<date>.md — a copy of today.md, as history.
- git config user.name "dola-daily bot"; git config user.email "dola-daily@users.noreply.github.com"; git add prompts; git commit -m "Prompts for <date>"; git push origin main (if rejected because the remote moved: git pull --rebase origin main, then push again once). Push nothing else: no other branches, no pull requests. Once main is pushed, nothing is left unpushed.
- The commit message must be exactly that one line: no trailers, no Co-Authored-By, no session or chat links (the repo is public and the user does not want chat links in it).
- Use no token, password or credentials of any kind. If the push fails (for example for lack of permission), don't look for a way around it: remember the exact error for the message and carry on.

STEP 5 — Deliver one message with the SendUserMessage tool (load it via ToolSearch first if needed), formatted exactly like this and nothing more:
## Today's video: <short title>
**▶ Watch the original:** [YouMind page](<meta.json url>) · [Original X post](<meta.json x_post>)
<one line: length and aspect ratio, e.g. "29.6s · 16:9". If characters or real people were replaced, add "(characters swapped for originals)".>
For a video of 15 s or less:
**Prompt — paste into Dola**
<code block>
For a longer video:
**Option A — one 30s clip** (if Dola allows 30s)
<code block>
**Option B — 2 × 15s** (if Dola only allows 15s)
**Part 1**
<code block>
**Part 2**
<code block>
**X post:** <caption under 280 characters, at most 2 hashtags, mentioning Dola AI>
**Saved for Dola:** "✅ prompts/today.md updated" or "⚠️ Couldn't save for Dola: <exact error>"
**Next:** Upload the finished clip(s) from Dola here (Part 1 first if you used Option B) and I'll send back the video ready to post, with the watermark removed (and the parts joined).
The two "Watch the original" links are required and must be the exact, full URLs.

STEP 6 — FINISHING (when the user later uploads clips in this chat; no need to ask anything first):
1. Find the uploaded video files. Part 1 is the first one uploaded (or the one named part1/p1); if the order is unclear, look at a frame of each and match it to the Part 1 and Part 2 prompts.
2. Make sure the tools exist: ffmpeg must be installed (check with "which ffmpeg"); if "python3 -c 'import cv2'" fails, run "pip install --break-system-packages opencv-python-headless".
3. The script is in the repo: <repo>/dola_finish.py. Run it on the uploaded files:
   - one clip:  python3 <repo>/dola_finish.py PART1.mp4 -o <short_title>.mp4
   - two clips: python3 <repo>/dola_finish.py PART1.mp4 PART2.mp4 -o <short_title>.mp4
   The script finds the "Dola AI" watermark in the bottom-right corner, fills it in frame by frame, keeps the exact original resolution and framing (no crop, no zoom), and for two clips joins them with a hard cut into one ~30s video.
4. Check the result: extract a frame from the middle of each part and look at the bottom-right corner to confirm the watermark is gone, and confirm the duration with ffprobe. If the script printed "No clear watermark found", say so in one line.
5. Send the final video with SendUserFile (display "render", status "normal") with the caption "Ready to post", then send the X post caption again in a SendUserMessage so it can be copied. Nothing else.
