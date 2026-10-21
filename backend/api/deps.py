from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request

from backend.config import get_settings
from backend.database.db import SessionLocal


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    """Admin endpoints require the secret ADMIN_TOKEN (sent in the X-Admin-Token header)."""
    token = get_settings().admin_token
    if not token:
        raise HTTPException(503, "Admin endpoints are disabled: set ADMIN_TOKEN in the server environment.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), token.encode()):
        raise HTTPException(401, "Invalid or missing admin token.", headers={"WWW-Authenticate": "AdminToken"})


def session_factory(request: Request):
    return getattr(request.app.state, "session_factory", SessionLocal)


def like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
