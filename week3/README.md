# Week 3 — GitHub MCP Server

A Model Context Protocol server that wraps a slice of the **GitHub REST API**.
Ships with both **STDIO** (for Claude Desktop, Cursor, MCP Inspector) and
**Streamable HTTP** (for remote/agent-runtime use) transports. The HTTP
transport requires API-key bearer auth.

## What's inside

| Capability | Name | Purpose |
| --- | --- | --- |
| Tool | `search_repositories` | Search public repos by GitHub query syntax |
| Tool | `get_repository` | Metadata for a single repo |
| Tool | `list_issues` | List open/closed issues (PRs filtered out) |
| Tool | `get_file_content` | Fetch and decode a single file |
| Resource | `github://rate-limit` | Live snapshot of the server's GitHub quota |
| Prompt | `triage_open_issues` | Workflow template for issue triage |

Endpoints used: `GET /search/repositories`, `GET /repos/{owner}/{repo}`,
`GET /repos/{owner}/{repo}/issues`, `GET /repos/{owner}/{repo}/contents/{path}`,
`GET /rate_limit`.

## Layout

```
week3/
├── README.md
├── pyproject.toml
├── .env.example
└── server/
    ├── __init__.py
    ├── github_client.py    # async httpx client w/ retry + rate-limit
    ├── mcp_server.py       # FastMCP instance, tools, resource, prompt
    ├── stdio_main.py       # STDIO entrypoint
    └── http_main.py        # Streamable-HTTP entrypoint w/ Bearer auth
```

## Prerequisites

- Python 3.10+
- `uv` (recommended) or `pip`
- Optional: a [GitHub personal access token](https://github.com/settings/tokens)
  with `public_repo` scope. Without one the server still works but is capped
  at GitHub's 60 req/hour unauthenticated limit.

## Setup

```bash
cd week3
cp .env.example .env
# edit .env — at minimum set MCP_API_KEY if you plan to run the HTTP transport
```

Install dependencies into a local venv:

```bash
# with uv (fast)
uv venv && source .venv/bin/activate
uv pip install -e .

# or with pip
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Environment variables

| Name | Required | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | optional | Used for **upstream** GitHub calls. Never forwarded to MCP clients. |
| `MCP_API_KEY` | **required for HTTP** | Shared secret presented by HTTP clients as `Authorization: Bearer <key>`. Never forwarded upstream. |
| `MCP_HTTP_HOST` | optional | HTTP bind host. Default `127.0.0.1`. |
| `MCP_HTTP_PORT` | optional | HTTP bind port. Default `8765`. |
| `LOG_LEVEL` | optional | `DEBUG` / `INFO` / `WARNING` / `ERROR`. Logs go to **stderr only**. |

> The two secrets are separate by design. `GITHUB_TOKEN` authenticates the
> server to GitHub. `MCP_API_KEY` authenticates MCP clients to *this* server.
> They are never mixed, in line with the MCP authorization spec's "never
> pass tokens through to upstream APIs" guidance.

## Running

### STDIO (local — Claude Desktop, Cursor, MCP Inspector)

```bash
python -m server.stdio_main
```

Inspect with the official inspector tool:

```bash
npx @modelcontextprotocol/inspector python -m server.stdio_main
```

#### Claude Desktop config

Add the following to `claude_desktop_config.json` (replace the paths):

```json
{
  "mcpServers": {
    "github-mcp": {
      "command": "/absolute/path/to/week3/.venv/bin/python",
      "args": ["-m", "server.stdio_main"],
      "cwd": "/absolute/path/to/week3",
      "env": {
        "GITHUB_TOKEN": "ghp_yourTokenHere",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Restart Claude Desktop. You should see `github-mcp` listed under tools.

### HTTP (Streamable HTTP — remote / agent runtimes)

```bash
python -m server.http_main
# -> Starting GitHub MCP server (HTTP) on 127.0.0.1:8765
```

The MCP endpoint is mounted at `/mcp/` (Starlette redirects `/mcp` → `/mcp/`
with a 307 — MCP clients follow it transparently). A liveness probe is
exposed at `/healthz` (unauthenticated).

#### Smoke-test the auth gate

```bash
curl -i http://127.0.0.1:8765/healthz
# -> 200 {"ok": true, ...}

curl -i -X POST http://127.0.0.1:8765/mcp/
# -> 401 with WWW-Authenticate: Bearer ...

curl -i -X POST http://127.0.0.1:8765/mcp/ \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
# -> 200 application/json with a serverInfo + capabilities payload
```

#### Inspector against HTTP

```bash
npx @modelcontextprotocol/inspector
# In the UI: transport=Streamable HTTP, URL=http://127.0.0.1:8765/mcp/,
# Header: Authorization: Bearer <MCP_API_KEY>
```

## Example invocation flow

After connecting the server in Claude Desktop:

1. Ask Claude: *"Use the github-mcp server to search for the top 5 Python
   repos about retrieval-augmented generation."*
   - Claude calls `search_repositories(query="rag language:python stars:>500", limit=5)`.
2. Ask: *"Now show me the open issues for the top result."*
   - Claude calls `list_issues(owner=…, repo=…, state="open", limit=20)`.
3. Ask: *"Read the project's README so I can summarize what it does."*
   - Claude calls `get_file_content(owner=…, repo=…, path="README.md")`.
4. Run the **Triage open issues** prompt with `owner` + `repo` to get a
   structured triage workflow.

## Reliability behaviors

- **Timeouts:** each upstream call uses a 20s timeout.
- **Retries:** 429, 502, 503, 504 retried up to 3× with exponential backoff
  + jitter; `Retry-After` honored when present.
- **Primary rate limit:** 403 with `X-RateLimit-Remaining: 0` triggers a
  capped sleep (≤ 60s) before retry, then surfaces a friendly error.
- **Empty results:** tools return a `message` field rather than an empty
  silence so the calling model can react.
- **Typed errors:** `Not found`, `auth failed`, `rate limit exhausted`, and
  generic upstream errors are converted to `ValueError` with stable phrasing
  so MCP clients see consistent error text.
- **Rate-limit visibility:** every successful tool result includes a
  `rate_limit` block with `remaining` / `limit` / `reset_epoch`. The
  `github://rate-limit` resource exposes the same data on demand.
- **STDIO logging:** all logs go to **stderr** (`stdout` is reserved for the
  JSON-RPC stream).

## Tool reference

### `search_repositories`

| Param | Type | Notes |
| --- | --- | --- |
| `query` | string | GitHub search qualifiers (`language:python stars:>1000` etc.) |
| `sort` | enum | `stars` / `forks` / `help-wanted-issues` / `updated` / `best-match` |
| `limit` | int 1-25 | Default 10 |

**Example output (abridged):**
```json
{
  "total_count": 1234,
  "results": [
    {"full_name": "tiangolo/fastapi", "stars": 76000, "language": "Python", "description": "..."}
  ],
  "rate_limit": {"remaining": 59, "limit": 60, "reset_epoch": 1716370000}
}
```

### `get_repository`

| Param | Type |
| --- | --- |
| `owner` | string |
| `repo` | string |

Returns the same shape as `search_repositories.results[*]` with extra fields
(`topics`, `license`, `pushed_at`).

### `list_issues`

| Param | Type | Notes |
| --- | --- | --- |
| `owner` / `repo` | string | |
| `state` | enum | `open` (default), `closed`, `all` |
| `labels` | string? | Comma-separated label filter |
| `limit` | int 1-50 | Default 20 |

Pull requests are filtered out.

### `get_file_content`

| Param | Type | Notes |
| --- | --- | --- |
| `owner` / `repo` | string | |
| `path` | string | File path inside the repo |
| `ref` | string? | Branch/tag/SHA. Defaults to default branch |
| `max_bytes` | int 256-200000 | Truncate after this many decoded bytes |

Returns `{ path, sha, size_bytes, truncated, is_binary, content, rate_limit }`.
Binary files come back with `is_binary: true` and replacement-character
decoding so the LLM can still see structure.

## Auth notes (bonus)

- HTTP transport refuses to start unless `MCP_API_KEY` is set in the env.
- Requests to `/mcp/...` without a matching `Authorization: Bearer <key>`
  header receive `401` + `WWW-Authenticate: Bearer realm="github-mcp", error="invalid_token"`.
- Comparison is constant-time (`hmac.compare_digest`).
- The MCP key is **never** forwarded to GitHub. Upstream auth uses the
  separate `GITHUB_TOKEN`.

This satisfies the assignment's bonus rubric: API-key auth with audience
isolation between server and upstream credentials.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `GitHub auth error (401)` from tools | Bad/expired `GITHUB_TOKEN`. Unset it or rotate. |
| `GitHub rate limit exhausted` after a few calls | No `GITHUB_TOKEN` set → 60 req/h ceiling. Add a token. |
| HTTP server returns 401 to inspector | Missing/incorrect `Authorization: Bearer` header. |
| STDIO client sees garbled JSON-RPC | Something printed to stdout. Check that no third-party code is calling `print()` — this server uses stderr logging only. |
