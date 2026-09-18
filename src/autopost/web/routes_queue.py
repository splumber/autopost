from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/queue", response_class=HTMLResponse)
async def queue_view(request: Request):
    db = request.app.state.db
    templates = request.app.state.templates
    buckets = {
        status: db.list_content_items(status=status, limit=15)
        for status in ("pending_review", "approved", "rendering", "scheduled", "posted", "failed")
    }
    return templates.TemplateResponse(request, "queue.html", {"buckets": buckets})


@router.post("/queue/{item_id}/approve")
async def approve_item(request: Request, item_id: int):
    request.app.state.db.update_content_item(item_id, status="approved")
    return RedirectResponse("/queue", status_code=303)


@router.post("/queue/{item_id}/reject")
async def reject_item(request: Request, item_id: int):
    request.app.state.db.update_content_item(item_id, status="rejected")
    return RedirectResponse("/queue", status_code=303)


@router.post("/queue/{item_id}/retry")
async def retry_item(request: Request, item_id: int):
    """Send a failed item back to 'approved' so the next render cycle retries it."""
    request.app.state.db.update_content_item(item_id, status="approved", error_message=None)
    return RedirectResponse("/queue", status_code=303)


@router.get("/queue/{item_id}/video")
async def item_video(request: Request, item_id: int):
    item = request.app.state.db.get_content_item(item_id)
    if not item or not item["video_path"]:
        raise HTTPException(status_code=404)
    return FileResponse(item["video_path"], media_type="video/mp4")
