# One-time manual setup checklist

Everything else (content generation, rendering, scheduling, posting, analytics)
runs autonomously once this is done. These steps require a human because
TikTok requires it -- there is no API path around them.

## 1. TikTok developer app

1. Go to https://developers.tiktok.com and register a developer account.
2. Create an app. Add the **Login Kit** and **Content Posting API** products.
3. Set the app's redirect URI to match `tiktok.redirect_uri` in
   `config/default.yaml` (default `http://localhost:8787/oauth/callback`).
   **If TikTok requires an HTTPS redirect URI on a verified domain** (common
   for production apps), point it instead at a small owned HTTPS endpoint or
   a transient tunnel (e.g. Cloudflare Tunnel / ngrok) that forwards to your
   local callback -- only needed during the one-time linking step in #4.
4. Copy the app's **Client Key** and **Client Secret** into `.env`
   (`AUTOPOST_TIKTOK_CLIENT_KEY`, `AUTOPOST_TIKTOK_CLIENT_SECRET`).
5. Submit the app for TikTok's standard app review (typically 1-2 weeks).

## 2. Free API keys

- Pexels: https://www.pexels.com/api/ -- free key, add to `.env` as
  `AUTOPOST_PEXELS_API_KEY`.
- Pixabay: https://pixabay.com/api/docs/ -- free key, add to `.env` as
  `AUTOPOST_PIXABAY_API_KEY`.
- Generate a token-encryption key:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and add it to `.env` as `AUTOPOST_SECRET_KEY`.

Without stock footage keys the pipeline still runs and produces complete
videos (using a generated color-background fallback per scene), but real
stock footage looks much better -- add these before going live.

## 3. Start the service

```
docker compose up
```

Open http://localhost:8080 -- this is the dashboard.

## 4. Link your TikTok account

Click **Link TikTok Account** on the dashboard. This sends your own browser
(not an automated one) to TikTok's real login/consent page. Log in and click
Allow like any other "Login with TikTok" app. The service captures the
resulting tokens automatically and refreshes them going forward -- you only
do this once, unless you revoke access.

## 5. Validate quality in private mode

Until TikTok completes the content audit (#6), all posts publish as
`SELF_ONLY` (visible only to you) -- this is a TikTok platform restriction on
unaudited apps, not a service limitation, and it isn't affected by your
`max_posts_per_day` setting. Watch a few videos render and post privately;
tune `config/local.yaml` (niche, voice, cadence) via the dashboard's Settings
page as needed.

## 6. Submit for TikTok's content audit

Once you're happy with output quality, submit your app for TikTok's audit to
unlock public posting (typically 1-4 weeks, TikTok-side, no guaranteed
timeline). When TikTok approves it:

1. Open the dashboard's **Settings** page.
2. Set **TikTok content audit status** to `approved`.
3. Set **Desired privacy level** to `PUBLIC_TO_EVERYONE`.

No restart or code change needed -- the next scheduled post goes out public.

## 7. Enroll in Creator Rewards once eligible

The dashboard home page tracks your progress toward TikTok's Creator Rewards
Program thresholds (10,000 followers, 100,000 views in the trailing 30 days,
videos ≥60s, account in good standing, eligible country). Once it shows
eligible, open the TikTok app yourself and enroll + verify a payout method --
this enrollment step isn't exposed via any public API and must be done by you
directly in the app.

## Ongoing

- Respond personally to any TikTok policy/compliance emails about your app or
  account -- automated systems can't do this for you.
- Periodically skim posted content in the dashboard queue for quality/policy
  drift, especially if you loosen the human-approval setting.
