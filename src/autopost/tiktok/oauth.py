"""One-time OAuth linking flow (PKCE). This is the only module that touches
TikTok's real login/consent page, and only to let the user authorize the app
themselves -- see docs/SETUP_CHECKLIST.md and web/routes_oauth.py for how the
browser step is triggered."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from autopost.config import TikTokConfig
from autopost.db.repo import Database, now_iso
from autopost.utils.crypto import decrypt, encrypt

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_authorize_url(cfg: TikTokConfig, db: Database) -> str:
    if not cfg.client_key:
        raise RuntimeError("AUTOPOST_TIKTOK_CLIENT_KEY not set -- see docs/SETUP_CHECKLIST.md")
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    db.save_oauth_state(state, verifier)
    params = {
        "client_key": cfg.client_key,
        "scope": ",".join(cfg.scopes),
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


async def exchange_code_for_tokens(
    cfg: TikTokConfig, db: Database, secret_key: str, code: str, state: str
) -> dict:
    verifier = db.consume_oauth_state(state)
    if not verifier:
        raise ValueError("Unknown or already-used OAuth state (link flow may have expired)")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.api_base_url}/v2/oauth/token/",
            data={
                "client_key": cfg.client_key,
                "client_secret": cfg.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": cfg.redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
    _store_tokens(db, secret_key, data)
    return data


async def refresh_access_token(cfg: TikTokConfig, db: Database, secret_key: str) -> str:
    account = db.get_account()
    if not account or not account["refresh_token_enc"]:
        raise RuntimeError("No linked TikTok account to refresh")
    refresh_token = decrypt(secret_key, account["refresh_token_enc"])
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.api_base_url}/v2/oauth/token/",
            data={
                "client_key": cfg.client_key,
                "client_secret": cfg.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
    _store_tokens(db, secret_key, data)
    return data["access_token"]


def _store_tokens(db: Database, secret_key: str, data: dict) -> None:
    expires_in = data.get("expires_in", 86400)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
    db.upsert_account(
        tiktok_open_id=data.get("open_id"),
        access_token_enc=encrypt(secret_key, data["access_token"]),
        refresh_token_enc=encrypt(secret_key, data.get("refresh_token", "")),
        token_expires_at=expires_at,
        scopes=data.get("scope", ""),
        linked_at=now_iso(),
    )


async def get_valid_access_token(cfg: TikTokConfig, db: Database, secret_key: str) -> str:
    account = db.get_account()
    if not account or not account["access_token_enc"]:
        raise RuntimeError("TikTok account not linked yet -- use the dashboard's Link TikTok Account button")
    expires_at = account["token_expires_at"]
    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        if expiry - timedelta(minutes=5) <= datetime.now(timezone.utc):
            return await refresh_access_token(cfg, db, secret_key)
    return decrypt(secret_key, account["access_token_enc"])
