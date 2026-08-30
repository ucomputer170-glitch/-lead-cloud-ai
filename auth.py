"""
auth.py — Google OAuth + Demo PIN Auth
"""

import json
import secrets
import time
from functools import wraps
from pathlib import Path

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    SECRET_KEY, USERS_FILE
)

_users = {}
_tokens = {}
_demo_pins = {}


def _load_users():
    global _users
    if USERS_FILE.exists():
        try:
            _users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _users = {}


def _save_users():
    USERS_FILE.write_text(json.dumps(_users, indent=2, ensure_ascii=False), encoding="utf-8")


def get_current_user(token: str) -> dict | None:
    if not token:
        return None
    session = _tokens.get(token)
    if not session:
        return None
    if session["expires"] < time.time():
        del _tokens[token]
        return None
    return _users.get(session["user_id"])


def require_auth(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        token = request.query_params.get("token", "")
    user = get_current_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def setup_auth(app):
    _load_users()

    @app.get("/auth/google")
    async def google_login():
        if not GOOGLE_CLIENT_ID:
            return JSONResponse({"error": "Google OAuth not configured"}, status_code=503)
        state = secrets.token_urlsafe(32)
        _demo_pins[state] = time.time() + 600
        url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={GOOGLE_CLIENT_ID}"
            f"&redirect_uri={GOOGLE_REDIRECT_URI}"
            f"&response_type=code"
            f"&scope=openid%20email%20profile"
            f"&state={state}"
            f"&access_type=offline"
        )
        return RedirectResponse(url)

    @app.get("/auth/callback")
    async def google_callback(code: str = "", state: str = ""):
        if not code:
            return RedirectResponse("/?error=no_code")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "redirect_uri": GOOGLE_REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return RedirectResponse("/?error=token_failed")
                userinfo_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                userinfo = userinfo_resp.json()
        except Exception:
            return RedirectResponse("/?error=google_error")

        user_id = userinfo.get("id", "")
        email = userinfo.get("email", "")
        name = userinfo.get("name", "")
        picture = userinfo.get("picture", "")

        _users[user_id] = {
            "id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": time.time(),
            "total_leads": _users.get(user_id, {}).get("total_leads", 0),
            "total_jobs": _users.get(user_id, {}).get("total_jobs", 0),
        }
        _save_users()

        session_token = secrets.token_urlsafe(32)
        _tokens[session_token] = {
            "user_id": user_id,
            "expires": time.time() + 86400 * 7,
        }

        return RedirectResponse(f"/?token={session_token}&name={name}")

    @app.post("/auth/demo-login")
    async def demo_login():
        session_token = secrets.token_urlsafe(32)
        user_id = "demo_user"
        _users[user_id] = {
            "id": user_id,
            "email": "demo@leadcloud.ai",
            "name": "Demo User",
            "picture": "",
            "created_at": time.time(),
            "total_leads": 0,
            "total_jobs": 0,
        }
        _save_users()
        _tokens[session_token] = {
            "user_id": user_id,
            "expires": time.time() + 86400,
        }
        return JSONResponse({"ok": True, "token": session_token, "name": "Demo User"})

    @app.get("/auth/me")
    async def auth_me(request: Request):
        user = require_auth(request)
        return JSONResponse(user)
