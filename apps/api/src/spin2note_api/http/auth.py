"""JWT validation against self-hosted Supabase Auth (GoTrue).

Verifies the bearer token using the GoTrue JWKS endpoint (RS256/ES256). For local dev a
shared HS256 secret can be configured instead. This keeps auth as a drop-in: no bespoke
crypto, just standard JWT verification.
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings, get_settings

_bearer = HTTPBearer(auto_error=True)
_optional_bearer = HTTPBearer(auto_error=False)
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client(url: str) -> jwt.PyJWKClient:
    client = _jwks_clients.get(url)
    if client is None:
        client = jwt.PyJWKClient(url)
        _jwks_clients[url] = client
    return client


async def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    token = credentials.credentials
    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
            )
        else:
            signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.supabase_jwt_audience,
            )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    return claims


async def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """Best-effort user id: the JWT subject when a valid token is present, else the dev default.

    Lets bulk imports / local dev upload without auth while honouring a real user when signed in.
    """
    if credentials is None:
        return settings.default_user_id
    try:
        claims = await require_user(credentials, settings)
    except HTTPException:
        return settings.default_user_id
    return str(claims.get("sub", settings.default_user_id))
