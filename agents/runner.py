"""
runner.py — Parallel Agent Orchestrator
Manages multiple lead generation jobs running simultaneously.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Callable

from agents.lead_finder import find_leads
from agents.email_finder import enrich_leads_with_emails
from agents.excel_gen import generate_excel

logger = logging.getLogger(__name__)

_jobs: Dict[str, Dict[str, Any]] = {}


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def list_jobs(user_id: str) -> list[dict]:
    user_jobs = []
    for jid, job in _jobs.items():
        if job.get("user_id") == user_id:
            user_jobs.append({
                "id": jid,
                "niche": job.get("niche", ""),
                "city": job.get("city", ""),
                "state": job.get("state", ""),
                "count": job.get("count", 0),
                "status": job.get("status", ""),
                "progress": job.get("progress", 0),
                "total": job.get("total", 0),
                "leads_found": job.get("leads_found", 0),
                "file": job.get("file", ""),
                "created_at": job.get("created_at", 0),
                "completed_at": job.get("completed_at", 0),
                "error": job.get("error", ""),
            })
    user_jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return user_jobs


async def _progress_callback(job_id: str, phase: str, current: int, total: int):
    """Update job progress."""
    if job_id in _jobs:
        _jobs[job_id]["progress"] = current
        _jobs[job_id]["total"] = total
        _jobs[job_id]["phase"] = phase


async def run_single_job(
    job_id: str,
    niche: str,
    city: str,
    state: str,
    count: int,
    user_id: str,
    ws_broadcast: Callable = None,
):
    """Run a single lead generation job."""
    _jobs[job_id] = {
        "user_id": user_id,
        "niche": niche,
        "city": city,
        "state": state,
        "count": count,
        "status": "running",
        "progress": 0,
        "total": 0,
        "leads_found": 0,
        "file": "",
        "created_at": time.time(),
        "completed_at": 0,
        "error": "",
        "phase": "starting",
    }

    async def on_progress(phase, current, total):
        await _progress_callback(job_id, phase, current, total)
        if ws_broadcast:
            await ws_broadcast({
                "type": "job_progress",
                "job_id": job_id,
                "phase": phase,
                "progress": current,
                "total": total,
            })

    try:
        leads = await find_leads(
            niche=niche,
            city=city,
            state=state,
            count=count,
            progress_callback=on_progress,
        )

        if leads:
            await on_progress("enriching_emails", 0, len(leads))
            leads = await enrich_leads_with_emails(leads)
            await on_progress("generating_excel", len(leads), len(leads))

            filepath = generate_excel(leads, job_id)

            _jobs[job_id].update({
                "status": "complete",
                "leads_found": len(leads),
                "file": filepath,
                "completed_at": time.time(),
                "progress": len(leads),
                "total": len(leads),
            })
        else:
            _jobs[job_id].update({
                "status": "complete",
                "leads_found": 0,
                "completed_at": time.time(),
                "error": "No leads found",
            })

        if ws_broadcast:
            await ws_broadcast({
                "type": "job_complete",
                "job_id": job_id,
                "leads_found": _jobs[job_id]["leads_found"],
                "file": _jobs[job_id].get("file", ""),
            })

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        _jobs[job_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": time.time(),
        })
        if ws_broadcast:
            await ws_broadcast({
                "type": "job_error",
                "job_id": job_id,
                "error": str(e),
            })


async def run_parallel_jobs(
    requests: list[dict],
    user_id: str,
    ws_broadcast: Callable = None,
) -> list[str]:
    """
    Run multiple lead generation jobs in parallel.

    Each request: {"niche": "HVAC", "city": "Houston", "state": "TX", "count": 100}

    Returns: list of job_ids
    """
    job_ids = []
    tasks = []

    for req in requests:
        job_id = str(uuid.uuid4())[:8]
        job_ids.append(job_id)
        tasks.append(run_single_job(
            job_id=job_id,
            niche=req.get("niche", ""),
            city=req.get("city", ""),
            state=req.get("state", ""),
            count=req.get("count", 100),
            user_id=user_id,
            ws_broadcast=ws_broadcast,
        ))

    await asyncio.gather(*tasks)
    return job_ids


async def cancel_job(job_id: str) -> bool:
    """Cancel a running job."""
    if job_id in _jobs and _jobs[job_id]["status"] == "running":
        _jobs[job_id]["status"] = "cancelled"
        _jobs[job_id]["completed_at"] = time.time()
        return True
    return False
