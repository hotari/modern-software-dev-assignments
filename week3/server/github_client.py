"""Async GitHub REST client with retry, rate-limit awareness, and typed errors."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 3
USER_AGENT = "week3-mcp-github/0.1.0"


class GitHubError(Exception):
    """Base class for GitHub client errors surfaced to MCP callers."""


class GitHubAuthError(GitHubError):
    """401/403 from GitHub — bad/missing GITHUB_TOKEN or insufficient scope."""


class GitHubNotFoundError(GitHubError):
    """404 from GitHub."""


class GitHubRateLimitError(GitHubError):
    """Primary or secondary rate-limit exhausted after retries."""


class GitHubUpstreamError(GitHubError):
    """5xx or network failure that retries did not recover."""


@dataclass(frozen=True)
class RateLimit:
    limit: int | None
    remaining: int | None
    reset_epoch: int | None

    @classmethod
    def from_headers(cls, headers: httpx.Headers) -> "RateLimit":
        def _int(name: str) -> int | None:
            v = headers.get(name)
            try:
                return int(v) if v is not None else None
            except ValueError:
                return None

        return cls(
            limit=_int("X-RateLimit-Limit"),
            remaining=_int("X-RateLimit-Remaining"),
            reset_epoch=_int("X-RateLimit-Reset"),
        )


@dataclass
class GitHubResponse:
    data: Any
    rate_limit: RateLimit
    status_code: int


class GitHubClient:
    """Thin wrapper around httpx.AsyncClient with GitHub-aware retries.

    Auth uses GITHUB_TOKEN from env. The MCP_API_KEY (HTTP transport auth) is
    never forwarded upstream — separate concerns.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN") or None
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GitHubClient":
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            timeout=self._timeout,
            headers=self._default_headers(),
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _default_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def get(self, path: str, params: dict[str, Any] | None = None) -> GitHubResponse:
        return await self._request("GET", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> GitHubResponse:
        if self._client is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as e:
                if attempt > self._max_retries:
                    raise GitHubUpstreamError(f"Timeout contacting GitHub after {attempt} attempts") from e
                await self._sleep_backoff(attempt)
                continue
            except httpx.HTTPError as e:
                if attempt > self._max_retries:
                    raise GitHubUpstreamError(f"Network error: {e}") from e
                await self._sleep_backoff(attempt)
                continue

            rate = RateLimit.from_headers(resp.headers)

            if resp.status_code < 400:
                return GitHubResponse(
                    data=resp.json() if resp.content else None,
                    rate_limit=rate,
                    status_code=resp.status_code,
                )

            if resp.status_code in (429, 502, 503, 504) and attempt <= self._max_retries:
                delay = self._retry_after_delay(resp) or self._backoff_seconds(attempt)
                logger.warning(
                    "GitHub %s %s -> %d; retrying in %.1fs (attempt %d/%d)",
                    method, path, resp.status_code, delay, attempt, self._max_retries,
                )
                await asyncio.sleep(delay)
                continue

            # Primary rate-limit exhausted: 403 with remaining=0
            if (
                resp.status_code == 403
                and rate.remaining == 0
                and attempt <= self._max_retries
            ):
                delay = self._retry_after_delay(resp) or 30.0
                logger.warning("Primary rate limit hit; sleeping %.1fs", delay)
                await asyncio.sleep(min(delay, 60.0))
                continue

            self._raise_for_status(resp, rate)

    @staticmethod
    def _retry_after_delay(resp: httpx.Response) -> float | None:
        ra = resp.headers.get("Retry-After")
        if ra is None:
            return None
        try:
            return float(ra)
        except ValueError:
            return None

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        # Exponential with jitter: 0.5, 1, 2, 4 ...
        base = 0.5 * (2 ** (attempt - 1))
        return base + random.uniform(0, base * 0.25)

    async def _sleep_backoff(self, attempt: int) -> None:
        await asyncio.sleep(self._backoff_seconds(attempt))

    @staticmethod
    def _raise_for_status(resp: httpx.Response, rate: RateLimit) -> None:
        message = _extract_error_message(resp)
        if resp.status_code in (401, 403):
            if rate.remaining == 0:
                raise GitHubRateLimitError(
                    f"GitHub rate limit exhausted (resets at epoch {rate.reset_epoch})."
                )
            raise GitHubAuthError(f"GitHub auth error ({resp.status_code}): {message}")
        if resp.status_code == 404:
            raise GitHubNotFoundError(f"Not found: {message}")
        if 500 <= resp.status_code < 600:
            raise GitHubUpstreamError(f"GitHub {resp.status_code}: {message}")
        raise GitHubError(f"GitHub {resp.status_code}: {message}")


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200] or "<empty body>"
    if isinstance(body, dict):
        return str(body.get("message") or body)
    return str(body)[:200]
