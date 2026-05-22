"""STDIO entrypoint. Run via `python -m server.stdio_main`."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from .mcp_server import build_server, configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()  # No-op if .env is missing.
    configure_logging()
    logger.info("Starting GitHub MCP server (STDIO transport)")
    mcp = build_server(stateless_http=False)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
