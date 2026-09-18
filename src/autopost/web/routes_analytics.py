from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from autopost.analytics.poller import REWARDS_FOLLOWER_THRESHOLD, REWARDS_VIEWS_THRESHOLD

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    db = request.app.state.db
    settings = request.app.state.settings
    templates = request.app.state.templates
    account = db.get_account()
    rewards = db.latest_rewards_progress()
    jobs = db.recent_job_runs(15)
    counts = {
        status: len(db.list_content_items(status=status, limit=1000))
        for status in ("pending_review", "approved", "scheduled", "posted", "failed")
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "account": account,
            "rewards": rewards,
            "jobs": jobs,
            "counts": counts,
            "settings": settings,
            "follower_threshold": REWARDS_FOLLOWER_THRESHOLD,
            "views_threshold": REWARDS_VIEWS_THRESHOLD,
        },
    )
