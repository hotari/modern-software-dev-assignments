from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from ollama import Client
from pydantic import BaseModel

load_dotenv()

BULLET_PREFIX_PATTERN = re.compile(r"^\s*([-*•]|\d+\.)\s+")
KEYWORD_PREFIXES = (
    "todo:",
    "action:",
    "next:",
)


def _is_action_line(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped:
        return False
    if BULLET_PREFIX_PATTERN.match(stripped):
        return True
    if any(stripped.startswith(prefix) for prefix in KEYWORD_PREFIXES):
        return True
    if "[ ]" in stripped or "[todo]" in stripped:
        return True
    return False


def extract_action_items(text: str) -> list[str]:
    lines = text.splitlines()
    extracted: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _is_action_line(line):
            cleaned = BULLET_PREFIX_PATTERN.sub("", line)
            cleaned = cleaned.strip()
            # Trim common checkbox markers
            cleaned = cleaned.removeprefix("[ ]").strip()
            cleaned = cleaned.removeprefix("[todo]").strip()
            extracted.append(cleaned)
    # Fallback: if nothing matched, heuristically split into sentences and pick imperative-like ones
    if not extracted:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if _looks_imperative(s):
                extracted.append(s)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in extracted:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)
    return unique


def _looks_imperative(sentence: str) -> bool:
    words = re.findall(r"[A-Za-z']+", sentence)
    if not words:
        return False
    first = words[0]
    # Crude heuristic: treat these as imperative starters
    imperative_starters = {
        "add",
        "create",
        "implement",
        "fix",
        "update",
        "write",
        "check",
        "verify",
        "refactor",
        "document",
        "design",
        "investigate",
    }
    return first.lower() in imperative_starters


# ---------------------------------------------------------------------------
# LLM extraction: uses the Ollama HTTP API via ollama.Client (local model).
# Structured JSON: https://ollama.com/blog/structured-outputs
# ---------------------------------------------------------------------------


class _ActionItemsResult(BaseModel):
    """Response shape; `format=` constrains the model to emit JSON matching this schema."""

    items: list[str]


def extract_action_items_llm(text: str) -> list[str]:
    """
    Extract action items using a model served by Ollama (local inference server).

    Environment:
    - ``OLLAMA_MODEL``: model name to run (default ``llama3.2``). Pull it first: ``ollama pull <name>``.
    - ``OLLAMA_HOST``: optional base URL if Ollama is not on localhost:11434.
    """
    stripped = text.strip()
    if not stripped:
        return []

    # Client talks to the Ollama daemon; it loads and runs the named model on request.
    client = Client(host=os.getenv("OLLAMA_HOST"))
    model = os.getenv("OLLAMA_MODEL", "llama3.2")

    system_msg = (
        "You extract actionable tasks from notes. Each item is one short task phrase "
        "(imperative or clear noun phrase). Include content from bullets, numbered lists, "
        "checkboxes, and lines starting with todo/action/next. Omit headings, filler, and "
        "sentences that only describe context without a task."
    )
    user_msg = f"Extract all action items from this text:\n\n{stripped}"

    # `format` enables structured outputs: reply is JSON matching _ActionItemsResult.
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        format=_ActionItemsResult.model_json_schema(),
        options={"temperature": 0},
    )

    # `message.content` is the JSON string from the model; validate into Python types.
    parsed = _ActionItemsResult.model_validate_json(response.message.content)
    cleaned = [item.strip() for item in parsed.items if item.strip()]

    seen: set[str] = set()
    unique: list[str] = []
    for item in cleaned:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)
    return unique
