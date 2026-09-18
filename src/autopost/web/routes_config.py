from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from autopost.config import save_local_override
from autopost.llm.prompts import NICHE_DESCRIPTIONS

router = APIRouter()


@router.get("/config", response_class=HTMLResponse)
async def config_view(request: Request):
    settings = request.app.state.settings
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "config.html",
        {"cfg": settings.redacted(), "niches": list(NICHE_DESCRIPTIONS.keys())},
    )


@router.post("/config")
async def config_update(
    request: Request,
    active_niche: str = Form(...),
    human_approval_required: str = Form("false"),
    max_posts_per_day: int = Form(...),
    min_hours_between_posts: int = Form(...),
    audit_status: str = Form(...),
    privacy_level: str = Form(...),
):
    settings = request.app.state.settings
    human_approval_bool = human_approval_required == "true"

    settings.niche.active_niche = active_niche
    settings.scheduler.human_approval_required = human_approval_bool
    settings.tiktok.max_posts_per_day = max_posts_per_day
    settings.tiktok.min_hours_between_posts = min_hours_between_posts
    settings.tiktok.audit_status = audit_status
    settings.tiktok.privacy_level = privacy_level

    save_local_override(
        {
            "niche": {"active_niche": active_niche},
            "scheduler": {"human_approval_required": human_approval_bool},
            "tiktok": {
                "max_posts_per_day": max_posts_per_day,
                "min_hours_between_posts": min_hours_between_posts,
                "audit_status": audit_status,
                "privacy_level": privacy_level,
            },
        }
    )
    return RedirectResponse("/config", status_code=303)
