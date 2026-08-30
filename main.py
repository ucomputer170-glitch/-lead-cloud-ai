"""
main.py — Lead Cloud AI Server
FastAPI + WebSocket + Chat Interface
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PORT, JOBS_DIR, JOBS_FILE
from auth import setup_auth, require_auth
from agent import parse_message, generate_response
from agents.runner import run_single_job, run_parallel_jobs, get_job, list_jobs, cancel_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

setup_auth(app)

_ws_clients: set[WebSocket] = set()


async def broadcast(msg: dict):
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/jobs")
async def api_list_jobs(request: Request):
    user = require_auth(request)
    jobs = list_jobs(user["id"])
    return JSONResponse({"jobs": jobs})


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str, request: Request):
    user = require_auth(request)
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse({
        "id": job_id,
        "niche": job.get("niche", ""),
        "city": job.get("city", ""),
        "state": job.get("state", ""),
        "count": job.get("count", 0),
        "status": job.get("status", ""),
        "progress": job.get("progress", 0),
        "total": job.get("total", 0),
        "leads_found": job.get("leads_found", 0),
        "phase": job.get("phase", ""),
        "file": job.get("file", ""),
        "error": job.get("error", ""),
    })


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel_job(job_id: str, request: Request):
    user = require_auth(request)
    ok = await cancel_job(job_id)
    return JSONResponse({"ok": ok})


@app.get("/api/download/{job_id}")
async def api_download(job_id: str, token: str = ""):
    from auth import get_current_user
    user = get_current_user(token)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    job = get_job(job_id)
    if not job or job.get("status") != "complete":
        return JSONResponse({"error": "Job not ready"}, status_code=404)

    filepath = job.get("file", "")
    if not filepath or not Path(filepath).exists():
        return JSONResponse({"error": "File not found"}, status_code=404)

    filename = Path(filepath).name
    return FileResponse(filepath, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


@app.post("/api/generate")
async def api_generate(request: Request):
    user = require_auth(request)
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    parsed = parse_message(message)
    response_text = generate_response(parsed)

    if parsed["action"] in ("cancel", "status", "history"):
        return JSONResponse({
            "ok": True,
            "response": response_text,
            "action": parsed["action"],
            "jobs": [],
        })

    if not parsed["requests"]:
        return JSONResponse({
            "ok": True,
            "response": response_text,
            "action": "generate",
            "jobs": [],
        })

    import uuid
    job_ids = []

    if len(parsed["requests"]) == 1:
        req = parsed["requests"][0]
        job_id = str(uuid.uuid4())[:8]
        job_ids.append(job_id)
        asyncio.create_task(run_single_job(
            job_id=job_id,
            niche=req["niche"],
            city=req["city"],
            state=req["state"],
            count=req["count"],
            user_id=user["id"],
            ws_broadcast=broadcast,
        ))
    else:
        for req in parsed["requests"]:
            job_id = str(uuid.uuid4())[:8]
            job_ids.append(job_id)
            asyncio.create_task(run_single_job(
                job_id=job_id,
                niche=req["niche"],
                city=req["city"],
                state=req["state"],
                count=req["count"],
                user_id=user["id"],
                ws_broadcast=broadcast,
            ))

    return JSONResponse({
        "ok": True,
        "response": response_text,
        "action": "generate",
        "jobs": job_ids,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
