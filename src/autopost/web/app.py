from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from autopost.config import Settings
from autopost.db.repo import Database

WEB_DIR = Path(__file__).parent
security = HTTPBasic(auto_error=False)


def _basic_auth_dependency(settings: Settings):
    async def check(credentials: HTTPBasicCredentials | None = Depends(security)):
        if not settings.web.basic_auth_username:
            return  # no auth configured, dashboard is localhost-only by default
        if credentials is None:
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
        ok_user = secrets.compare_digest(credentials.username, settings.web.basic_auth_username)
        ok_pass = secrets.compare_digest(credentials.password, settings.web.basic_auth_password or "")
        if not (ok_user and ok_pass):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})

    return check


def create_app(db: Database, settings: Settings) -> FastAPI:
    app = FastAPI(title="autopost dashboard")
    app.state.db = db
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    from autopost.web import routes_analytics, routes_config, routes_oauth, routes_queue

    auth_dep = _basic_auth_dependency(settings)
    for router in (
        routes_analytics.router,
        routes_oauth.router,
        routes_queue.router,
        routes_config.router,
    ):
        app.include_router(router, dependencies=[Depends(auth_dep)])

    return app
