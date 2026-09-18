# autopost

A single-service pipeline that generates, renders, and posts original
faceless short-form videos to one TikTok account you own, using your local
LLM proxy for scripts and TikTok's official Content Posting API to publish.

Not included, by design: automated account/email creation, reposting other
creators' content, or engagement manipulation -- see `docs/SETUP_CHECKLIST.md`
for the (unavoidable, TikTok-side) manual steps and everything else this
service automates for you.

## Quick start

1. Complete `docs/SETUP_CHECKLIST.md` steps 1-2 (TikTok developer app, free
   stock-footage API keys, `.env`).
2. `docker compose up`
3. Open http://localhost:8080, click **Link TikTok Account**.
4. Watch content generate and post (privately, until TikTok audits your app --
   see the checklist).

## How it works

One process runs three loops concurrently (`src/autopost/scheduler/loop.py`):

- **Content pipeline**: idea generation -> script -> AI policy self-check ->
  metadata -> TTS narration -> stock footage -> ffmpeg render -> scheduling.
- **Publish loop**: posts due, scheduled videos via TikTok's Content Posting
  API, respecting TikTok's rate limits and a hard-clamped daily cap.
- **Analytics loop**: polls follower/view counts and tracks progress toward
  TikTok's Creator Rewards Program thresholds.

A FastAPI dashboard (same process) shows pipeline status, a content review
queue, Creator Rewards progress, and lets you edit settings (niche, cadence,
audit/privacy status) without restarting.

See `plans/` history or `docs/` for the fuller design writeup, and
`config/default.yaml` for every tunable setting.

## Local development (without Docker)

```
python -m venv .venv
.venv/Scripts/pip install -e .          # Windows
source .venv/bin/activate && pip install -e .   # macOS/Linux
cp .env.example .env   # fill in AUTOPOST_SECRET_KEY at minimum
python -m autopost --check-config       # sanity check
python -m autopost                      # runs scheduler + dashboard
```

ffmpeg is bundled via the `imageio-ffmpeg` package -- no system install
needed either locally or in the container.

## Tests

```
.venv/Scripts/pytest    # or: pytest, if venv is activated
```
