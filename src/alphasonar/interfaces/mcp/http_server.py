"""Authenticated Streamable HTTP transport for server deployments."""

from __future__ import annotations

import contextlib
import hmac
import os
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from alphasonar.interfaces.mcp.server import app as mcp_server


class BearerTokenMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(supplied, expected):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_http_app(token: str | None = None) -> Starlette:
    if token is None:
        token = os.environ.get("ALPHASONAR_MCP_TOKEN", "") or os.environ.get("IRA_MCP_TOKEN", "")
        token_files = (
            os.environ.get("ALPHASONAR_MCP_TOKEN_FILE", ""),
            os.environ.get("IRA_MCP_TOKEN_FILE", ""),
            "/run/secrets/alphasonar_mcp_token",
            "/run/secrets/ira_mcp_token",
        )
        for token_file in token_files:
            if not token and token_file and Path(token_file).is_file():
                token = Path(token_file).read_text().strip()
    if not token:
        raise RuntimeError("ALPHASONAR_MCP_TOKEN is required for the HTTP MCP transport")

    manager = StreamableHTTPSessionManager(
        app=mcp_server,
        json_response=True,
        stateless=True,
        session_idle_timeout=None,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    async def health(_request):
        return JSONResponse({"status": "ok"})

    protected_mcp = BearerTokenMiddleware(manager.handle_request, token)
    return Starlette(
        routes=[Route("/health", health), Mount("/mcp", app=protected_mcp)],
        lifespan=lifespan,
    )


def run() -> None:
    host = os.environ.get("ALPHASONAR_MCP_HOST") or os.environ.get("IRA_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHASONAR_MCP_PORT") or os.environ.get("IRA_MCP_PORT", "8000"))
    uvicorn.run(create_http_app(), host=host, port=port, log_level="info")
