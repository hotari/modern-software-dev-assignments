"""FastMCP server definition. Shared between STDIO and HTTP entrypoints."""

from __future__ import annotations

import base64
import logging
import os
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .github_client import (
    GitHubAuthError,
    GitHubClient,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponse,
    GitHubUpstreamError,
    RateLimit,
)

logger = logging.getLogger(__name__)


def build_server(*, stateless_http: bool = False) -> FastMCP:
    """Create a configured FastMCP instance.

    `stateless_http=True` is recommended for the HTTP transport so the server
    scales horizontally without sticky sessions.
    """
    mcp = FastMCP(
        name="github-mcp",
        instructions=(
            "Tools for inspecting public GitHub repositories: search, repo "
            "metadata, issues, and file contents. Set GITHUB_TOKEN in the "
            "server env to raise the rate limit ceiling."
        ),
        stateless_http=stateless_http,
        json_response=stateless_http,
    )

    _register_tools(mcp)
    _register_resources(mcp)
    _register_prompts(mcp)
    return mcp


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _register_tools(mcp: FastMCP) -> None:
    @mcp.tool(title="Search repositories")
    async def search_repositories(
        query: Annotated[str, Field(description="GitHub search qualifiers, e.g. 'fastapi language:python stars:>1000'.")],
        sort: Annotated[
            Literal["stars", "forks", "help-wanted-issues", "updated", "best-match"],
            Field(description="Sort field. 'best-match' uses GitHub's default relevance ranking."),
        ] = "best-match",
        limit: Annotated[int, Field(ge=1, le=25, description="Max results to return (1-25).")] = 10,
    ) -> dict[str, Any]:
        """Search public GitHub repositories.

        Returns a compact list of repos with key metadata (stars, language, description).
        """
        params: dict[str, Any] = {"q": query, "per_page": limit}
        if sort != "best-match":
            params["sort"] = sort

        async with GitHubClient() as gh:
            resp = await _safe_call(gh.get("/search/repositories", params=params))

        items = (resp.data or {}).get("items", [])
        if not items:
            return _empty("No repositories matched the query.", resp.rate_limit)

        return {
            "total_count": resp.data.get("total_count", 0),
            "results": [_summarize_repo(item) for item in items],
            "rate_limit": _format_rate_limit(resp.rate_limit),
        }

    @mcp.tool(title="Get repository")
    async def get_repository(
        owner: Annotated[str, Field(description="Repo owner login, e.g. 'modelcontextprotocol'.")],
        repo: Annotated[str, Field(description="Repo name, e.g. 'python-sdk'.")],
    ) -> dict[str, Any]:
        """Fetch metadata for a single repository.

        Includes description, primary language, stars, default branch, license, topics.
        """
        async with GitHubClient() as gh:
            resp = await _safe_call(gh.get(f"/repos/{owner}/{repo}"))

        return {
            "repository": _summarize_repo(resp.data, include_extra=True),
            "rate_limit": _format_rate_limit(resp.rate_limit),
        }

    @mcp.tool(title="List issues")
    async def list_issues(
        owner: Annotated[str, Field(description="Repo owner login.")],
        repo: Annotated[str, Field(description="Repo name.")],
        state: Annotated[Literal["open", "closed", "all"], Field(description="Issue state filter.")] = "open",
        labels: Annotated[
            str | None,
            Field(description="Comma-separated label names to filter by. e.g. 'bug,help wanted'."),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=50, description="Max results (1-50).")] = 20,
    ) -> dict[str, Any]:
        """List issues for a repository.

        Pull requests are filtered out — use a dedicated tool for PRs if needed.
        """
        params: dict[str, Any] = {"state": state, "per_page": limit}
        if labels:
            params["labels"] = labels

        async with GitHubClient() as gh:
            resp = await _safe_call(gh.get(f"/repos/{owner}/{repo}/issues", params=params))

        raw = resp.data or []
        # /issues returns PRs too; drop them.
        issues = [item for item in raw if "pull_request" not in item]
        if not issues:
            return _empty(f"No {state} issues found.", resp.rate_limit)

        return {
            "count": len(issues),
            "issues": [_summarize_issue(item) for item in issues],
            "rate_limit": _format_rate_limit(resp.rate_limit),
        }

    @mcp.tool(title="Get file content")
    async def get_file_content(
        owner: Annotated[str, Field(description="Repo owner login.")],
        repo: Annotated[str, Field(description="Repo name.")],
        path: Annotated[str, Field(description="Path to the file inside the repo, e.g. 'README.md'.")],
        ref: Annotated[
            str | None,
            Field(description="Branch, tag, or commit SHA. Defaults to the repo's default branch."),
        ] = None,
        max_bytes: Annotated[
            int,
            Field(ge=256, le=200_000, description="Truncate file content after this many decoded bytes."),
        ] = 50_000,
    ) -> dict[str, Any]:
        """Fetch the decoded content of a single file from a repository.

        Binary files (and files exceeding `max_bytes`) are returned truncated with a flag.
        """
        params = {"ref": ref} if ref else None
        async with GitHubClient() as gh:
            resp = await _safe_call(gh.get(f"/repos/{owner}/{repo}/contents/{path}", params=params))

        payload = resp.data or {}
        if isinstance(payload, list):
            raise GitHubError(f"'{path}' is a directory, not a file.")

        if payload.get("type") != "file":
            raise GitHubError(f"Unsupported content type: {payload.get('type')}")

        encoded = payload.get("content", "")
        encoding = payload.get("encoding", "base64")
        if encoding != "base64":
            raise GitHubError(f"Unexpected encoding: {encoding}")

        decoded = base64.b64decode(encoded)
        truncated = len(decoded) > max_bytes
        body_bytes = decoded[:max_bytes]
        try:
            text = body_bytes.decode("utf-8")
            is_binary = False
        except UnicodeDecodeError:
            text = body_bytes.decode("utf-8", errors="replace")
            is_binary = True

        return {
            "path": payload.get("path", path),
            "sha": payload.get("sha"),
            "size_bytes": payload.get("size"),
            "truncated": truncated,
            "is_binary": is_binary,
            "content": text,
            "rate_limit": _format_rate_limit(resp.rate_limit),
        }


# ---------------------------------------------------------------------------
# Resources & prompts
# ---------------------------------------------------------------------------


def _register_resources(mcp: FastMCP) -> None:
    @mcp.resource("github://rate-limit")
    async def rate_limit_resource() -> str:
        """Live snapshot of the server's GitHub rate-limit budget."""
        async with GitHubClient() as gh:
            try:
                resp = await gh.get("/rate_limit")
            except GitHubError as e:
                return f"Unable to read rate limit: {e}"
        core = (resp.data or {}).get("resources", {}).get("core", {})
        return (
            f"core.limit={core.get('limit')}, "
            f"remaining={core.get('remaining')}, "
            f"reset_epoch={core.get('reset')}"
        )


def _register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(title="Triage open issues")
    def triage_open_issues(owner: str, repo: str) -> str:
        """Prompt template for triaging the open issue queue of a repository."""
        return (
            f"You have access to GitHub tools. For the repository {owner}/{repo}:\n"
            "1. Call list_issues with state='open' (limit 20).\n"
            "2. Group the issues into: bugs, feature requests, questions, and unclear.\n"
            "3. Flag any issue that has been quiet for a long time or has no labels.\n"
            "4. Suggest a 3-item ordered triage plan."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_call(coro) -> GitHubResponse:
    """Re-raise GitHub client errors as plain ValueErrors with a stable shape.

    FastMCP serializes raised exceptions into MCP tool errors; we use this
    wrapper so MCP clients see consistent, actionable messages.
    """
    try:
        return await coro
    except GitHubNotFoundError as e:
        raise ValueError(str(e)) from e
    except GitHubAuthError as e:
        raise ValueError(
            f"GitHub authentication failed: {e}. "
            "Set GITHUB_TOKEN in the server env or check token scopes."
        ) from e
    except GitHubRateLimitError as e:
        raise ValueError(f"GitHub rate limit exhausted: {e}") from e
    except GitHubUpstreamError as e:
        raise ValueError(f"GitHub upstream error (try again later): {e}") from e
    except GitHubError as e:
        raise ValueError(str(e)) from e


def _summarize_repo(item: dict[str, Any], *, include_extra: bool = False) -> dict[str, Any]:
    summary = {
        "full_name": item.get("full_name"),
        "html_url": item.get("html_url"),
        "description": item.get("description"),
        "language": item.get("language"),
        "stars": item.get("stargazers_count"),
        "forks": item.get("forks_count"),
        "open_issues": item.get("open_issues_count"),
        "default_branch": item.get("default_branch"),
        "archived": item.get("archived", False),
    }
    if include_extra:
        summary["topics"] = item.get("topics") or []
        license_obj = item.get("license") or {}
        summary["license"] = license_obj.get("spdx_id") if isinstance(license_obj, dict) else None
        summary["pushed_at"] = item.get("pushed_at")
    return summary


def _summarize_issue(item: dict[str, Any]) -> dict[str, Any]:
    user = item.get("user") or {}
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "state": item.get("state"),
        "labels": [lab.get("name") for lab in item.get("labels", []) if isinstance(lab, dict)],
        "author": user.get("login"),
        "comments": item.get("comments"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
    }


def _empty(message: str, rate_limit: RateLimit) -> dict[str, Any]:
    return {"results": [], "message": message, "rate_limit": _format_rate_limit(rate_limit)}


def _format_rate_limit(rate: RateLimit) -> dict[str, Any]:
    return {
        "remaining": rate.remaining,
        "limit": rate.limit,
        "reset_epoch": rate.reset_epoch,
    }


def configure_logging() -> None:
    """Log to stderr only. Critical for STDIO transport (stdout is reserved)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    # stream=None defaults to stderr in StreamHandler.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
