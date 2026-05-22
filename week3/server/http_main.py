"""HTTP (Streamable HTTP) entrypoint with API-key Bearer auth.

The MCP protocol exposes a single `/mcp` endpoint. We mount FastMCP under
`/mcp` and gate it with an ASGI middleware that validates the Authorization
header against `MCP_API_KEY`. The shared secret is the audience for *this*
server only — it is never forwarded to GitHub upstream.
"""

from __future__ import annotations

import contextlib
import hmac
import logging
import os
from typing import Awaitable, Callable

import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .mcp_server import build_server, configure_logging

logger = logging.getLogger(__name__)

WWW_AUTH = 'Bearer realm="github-mcp", error="invalid_token"'


class BearerAuthMiddleware:
    """Reject requests that don't present the configured API key.

    The expected token is a single shared secret loaded once at startup;
    comparison is constant-time. `/healthz` is exempt.
    """

    def __init__(self, app: ASGIApp, *, api_key: str, protected_prefix: str) -> None:
        if not api_key:
            raise ValueError("MCP_API_KEY must be set when running the HTTP transport.")
        self._app = app
        self._api_key = api_key
        self._prefix = protected_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not path.startswith(self._prefix):
            await self._app(scope, receive, send)
            return

        if not self._is_authorized(scope):
            await self._reject(send)
            return

        await self._app(scope, receive, send)

    def _is_authorized(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                token = _extract_bearer(value.decode("latin-1"))
                if token is None:
                    return False
                return hmac.compare_digest(token, self._api_key)
        return False

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"error":"unauthorized","message":"Provide Authorization: Bearer <MCP_API_KEY>"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", WWW_AUTH.encode("latin-1")),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _extract_bearer(header_value: str) -> str | None:
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def _healthz(_: Request) -> Response:
    return JSONResponse({"ok": True, "service": "github-mcp"})


def build_app() -> Starlette:
    mcp = build_server(stateless_http=True)
    # Mount at /mcp and serve the protocol at the mount root, so the public
    # URL is http://host:port/mcp (not /mcp/mcp).
    mcp.settings.streamable_http_path = "/"

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        async with mcp.session_manager.run():
            yield

    api_key = os.environ.get("MCP_API_KEY", "")
    app = Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Mount("/mcp", mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )

    # The mount handles its own routing; we only protect the /mcp prefix so
    # /healthz stays open for liveness probes.
    app.add_middleware(BearerAuthMiddleware, api_key=api_key, protected_prefix="/mcp")
    return app


def main() -> None:
    load_dotenv()
    configure_logging()

    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_HTTP_PORT", "8765"))

    if not os.environ.get("MCP_API_KEY"):
        raise SystemExit(
            "MCP_API_KEY is not set. Refusing to start an unauthenticated HTTP server."
        )

    logger.info("Starting GitHub MCP server (HTTP) on %s:%d", host, port)
    uvicorn.run(build_app(), host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
