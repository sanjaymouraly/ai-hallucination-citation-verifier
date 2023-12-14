from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import config


class OwnerAuthMiddleware(BaseHTTPMiddleware):
    """Optional shared-token auth with per-token owner isolation.

    With APP_API_TOKENS unset this is a single-user local installation (owner=local).
    Multi-user deployments must configure one long, unique token per owner.
    """

    async def dispatch(self, request: Request, call_next):
        tokens = config.api_tokens
        request.state.owner_id = "local"
        if not tokens or request.url.path in {"/api/auth/status", "/health", "/openapi.json", "/docs", "/redoc"}:
            if tokens and request.headers.get("authorization", "").startswith("Bearer "):
                supplied = request.headers["authorization"][7:]
                for token, owner in tokens.items():
                    if hmac.compare_digest(supplied, token):
                        request.state.owner_id = owner
                        break
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        for token, owner in tokens.items():
            if hmac.compare_digest(supplied, token):
                request.state.owner_id = owner
                return await call_next(request)
        return JSONResponse({"detail": "Authentication required. Add a valid workspace access token."}, status_code=401)
