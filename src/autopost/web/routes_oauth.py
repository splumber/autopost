"""One-time TikTok account linking. This is a plain OAuth redirect flow --
the user's own browser (already viewing this dashboard) is sent to TikTok's
real login/consent page and back; no browser automation is involved or
needed here."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from autopost.tiktok import oauth

router = APIRouter()


@router.get("/oauth/link")
async def oauth_link(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    try:
        url = oauth.build_authorize_url(settings.tiktok, db)
    except RuntimeError as exc:
        return HTMLResponse(f"<p>{exc}</p><p><a href='/'>Back</a></p>", status_code=400)
    return RedirectResponse(url)


@router.get("/oauth/callback")
async def oauth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(f"<p>TikTok authorization failed: {error}</p><p><a href='/'>Back</a></p>", status_code=400)
    if not code or not state:
        return HTMLResponse("<p>Missing code/state in callback.</p>", status_code=400)

    db = request.app.state.db
    settings = request.app.state.settings
    try:
        await oauth.exchange_code_for_tokens(settings.tiktok, db, settings.secret_key, code, state)
    except Exception as exc:  # noqa: BLE001 -- surface any failure to the user in the browser
        return HTMLResponse(f"<p>Token exchange failed: {exc}</p><p><a href='/'>Back</a></p>", status_code=400)
    return RedirectResponse("/")
