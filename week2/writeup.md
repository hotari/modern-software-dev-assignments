# Week 2 Write-up
Tip: To preview this markdown file
- On Mac, press `Command (⌘) + Shift + V`
- On Windows/Linux, press `Ctrl + Shift + V`

## INSTRUCTIONS

Fill out all of the `TODO`s in this file.

## SUBMISSION DETAILS

Name: hotari \
SUNet ID: 12345678 \
Citations: :)

This assignment took me about **TODO** hours to do. 


## YOUR RESPONSES
For each exercise, please include what prompts you used to generate the answer, in addition to the location of the generated response. Make sure to clearly add comments in your code documenting which parts are generated.

### Exercise 1: Scaffold a New Feature
Prompt: 
```
Based on your analysis of the extract_action_items_llm function, I want to modify it to use the Ollama model. Please perform the modification and include explanations for the lines being changed
``` 

Generated Code Snippets:
```
--- Pydantic schema (structured outputs: https://ollama.com/blog/structured-outputs) ---
class _ActionItemsResult(BaseModel):
    items: list[str]

--- ollama.Client (week2/app/services/extract.py) ---
from ollama import Client

def extract_action_items_llm(text: str) -> List[str]:
    stripped = text.strip()
    if not stripped:
        return []
    client = Client(host=os.getenv("OLLAMA_HOST"))
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    system_msg = (
        "You extract actionable tasks from notes. Each item is one short task phrase "
        "(imperative or clear noun phrase). Include content from bullets, numbered lists, "
        "checkboxes, and lines starting with todo/action/next. Omit headings, filler, and "
        "sentences that only describe context without a task."
    )
    user_msg = f"Extract all action items from this text:\n\n{stripped}"
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        format=_ActionItemsResult.model_json_schema(),
        options={"temperature": 0},
    )
    parsed = _ActionItemsResult.model_validate_json(response.message.content)
    cleaned = [item.strip() for item in parsed.items if item.strip()]
    seen: set[str] = set()
    unique: List[str] = []
    for item in cleaned:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)
    return unique

--- Explanation (maps to week2/app/services/extract.py) ---
- Lines 7–9: import `Client` (Ollama HTTP API) and `BaseModel` (Pydantic) used for structured output.
- Lines 92–95: comment block marking the LLM path and linking structured outputs docs.
- Lines 98–101: `_ActionItemsResult` defines `items: list[str]`; this schema is what `format=` constrains the model to emit.
- Lines 104–111: docstring documents `OLLAMA_MODEL` / `OLLAMA_HOST` (matches lines 117–118).
- Lines 112–114: `text.strip()`; if empty after strip, return `[]` immediately (no Ollama call).
- Line 117: `Client(host=os.getenv("OLLAMA_HOST"))` — optional non-default Ollama URL.
- Line 118: `OLLAMA_MODEL` with default `llama3.2` (model must be pulled locally).
- Lines 120–125: system prompt instructing what counts as an action item.
- Line 126: user message embeds the full stripped note after a fixed prefix.
- Lines 129–137: `client.chat` with `model`, system+user `messages`, `format=_ActionItemsResult.model_json_schema()` (structured JSON), `temperature: 0`.
- Lines 139–140: parse `response.message.content` as JSON into `_ActionItemsResult`.
- Line 141: strip each string and drop empty entries.
- Lines 143–151: case-insensitive deduplication while preserving first-seen order (parallel idea to lines 58–65 in `extract_action_items`).
```

### Exercise 2: Add Unit Tests
Prompt: 
```
Based on your implemenation of extract_action_items_llm, make unit test for that in tests/test_extract.py covering various inputs(e.g., bullet lists, keyword-prefixed lines, empty input).
``` 

Generated Code Snippets:
```
--- Full source: week2/tests/test_extract.py (lines 1–95) ---

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from ..app.services.extract import extract_action_items, extract_action_items_llm


def test_extract_bullets_and_checkboxes():
    text = """
    Notes from meeting:
    - [ ] Set up database
    * implement API extract endpoint
    1. Write tests
    Some narrative sentence.
    """.strip()

    items = extract_action_items(text)
    assert "Set up database" in items
    assert "implement API extract endpoint" in items
    assert "Write tests" in items


def _ollama_chat_response(items: list[str]) -> SimpleNamespace:
    """Minimal ollama chat response shape: message.content is JSON for _ActionItemsResult."""
    payload = json.dumps({"items": items})
    return SimpleNamespace(message=SimpleNamespace(content=payload))


# --- extract_action_items_llm: Ollama is mocked (no local server required) ---


@patch("week2.app.services.extract.Client")
def test_extract_llm_empty_input_does_not_call_ollama(mock_client_cls):
    assert extract_action_items_llm("") == []
    assert extract_action_items_llm("   \n\t  ") == []
    mock_client_cls.assert_not_called()


@patch("week2.app.services.extract.Client")
def test_extract_llm_bullet_and_numbered_list(mock_client_cls):
    mock_client_cls.return_value.chat.return_value = _ollama_chat_response(
        ["Set up database", "Write tests"]
    )
    text = "- [ ] Set up database\n1. Write tests\nNarrative only."
    items = extract_action_items_llm(text)
    assert items == ["Set up database", "Write tests"]
    mock_client_cls.return_value.chat.assert_called_once()
    call_kwargs = mock_client_cls.return_value.chat.call_args.kwargs
    assert "Set up database" in call_kwargs["messages"][1]["content"]


@patch("week2.app.services.extract.Client")
def test_extract_llm_keyword_prefixed_lines(mock_client_cls):
    mock_client_cls.return_value.chat.return_value = _ollama_chat_response(
        [
            "Review API contract",
            "Ship milestone",
            "Update docs",
        ]
    )
    text = """
    todo: Review API contract
    action: Ship milestone
    next: Update docs
    """.strip()
    items = extract_action_items_llm(text)
    assert items == ["Review API contract", "Ship milestone", "Update docs"]


@patch("week2.app.services.extract.Client")
def test_extract_llm_deduplicates_case_insensitive(mock_client_cls):
    mock_client_cls.return_value.chat.return_value = _ollama_chat_response(
        ["Fix bug", "fix bug", "FIX BUG"]
    )
    items = extract_action_items_llm("anything")
    assert items == ["Fix bug"]


@patch("week2.app.services.extract.Client")
def test_extract_llm_strips_whitespace_and_empty_strings(mock_client_cls):
    mock_client_cls.return_value.chat.return_value = _ollama_chat_response(
        ["  first task  ", "", "  second task"]
    )
    items = extract_action_items_llm("note")
    assert items == ["first task", "second task"]


@patch.dict(os.environ, {"OLLAMA_MODEL": "test-model"}, clear=False)
@patch("week2.app.services.extract.Client")
def test_extract_llm_passes_model_to_chat(mock_client_cls):
    mock_client_cls.return_value.chat.return_value = _ollama_chat_response(["a"])
    extract_action_items_llm("x")
    assert mock_client_cls.return_value.chat.call_args.kwargs["model"] == "test-model"

--- Explanation (maps to week2/tests/test_extract.py) ---
- Lines 1–6: imports (`json`, `os`, `SimpleNamespace`, `patch`) and test subject imports `extract_action_items`, `extract_action_items_llm`.
- Lines 9–21: `test_extract_bullets_and_checkboxes` — covers heuristic `extract_action_items` only (not LLM).
- Lines 24–27: `_ollama_chat_response` builds `message.content` as JSON `{"items": [...]}` so lines 139–140 in `extract.py` parse like a real Ollama reply.
- Line 33: `@patch("week2.app.services.extract.Client")` replaces `Client` in the module under test (same symbol `extract_action_items_llm` uses at line 117 of `extract.py`).
- Lines 34–37: empty string and whitespace-only inputs expect `[]` and `mock_client_cls.assert_not_called()` — aligns with `extract.py` lines 112–114 (early return before `Client(...)`).
- Lines 40–50: bullet/numbered note text; mock chat return; assert extracted list and that `messages[1]["content"]` contains `"Set up database"` — exercises the path that builds `user_msg` (`extract.py` line 126).
- Lines 53–68: `todo:` / `action:` / `next:` body text; assert three-item list equals mock — keyword-style note coverage.
- Lines 71–77: mock duplicates differing only by case; assert one `"Fix bug"` — matches dedupe loop `extract.py` lines 143–151.
- Lines 80–86: mock includes padded strings and `""`; assert strip/drop behavior — matches `extract.py` line 141.
- Lines 89–94: `@patch.dict` sets `OLLAMA_MODEL=test-model`; assert `chat` kwargs `model == "test-model"` — matches `extract.py` line 118 reading `os.getenv("OLLAMA_MODEL", ...)`.
```

### Exercise 3: Refactor Existing Code for Clarity
Prompt: 
```
Perform a refactor of the code in the backend, focusing in particular on well-defined API contracts/schemas, database layer cleanup, app lifecycle/configuration, error handling
``` 

Generated/Modified Code Snippets:
```
Exercise 3 refactor — modified / added files (paths from repo root: week2/…)

NEW: week2/app/config.py (lines 1–31)
- Settings dataclass, get_settings() with WEEK2_DATA_DIR override, reset_settings_cache().

NEW: week2/app/schemas/__init__.py (lines 1–23)
- Re-exports Pydantic models for OpenAPI / routers.

NEW: week2/app/schemas/notes.py (lines 1–29)
- NoteCreatePayload (strip + validation), NoteOut (API response).

NEW: week2/app/schemas/action_items.py (lines 1–53)
- ExtractPayload, ExtractedItemOut, ExtractResponse, ActionItemOut, ActionItemDonePayload, ActionItemMarkedOut.

MODIFIED: week2/app/db.py (lines 1–151)
- Note / ActionItem dataclasses (9–26); get_settings() for paths (29–41); row mappers (72–83); list/get return typed records (94–109, 126–138); mark_action_item_done returns bool (141–150).

MODIFIED: week2/app/main.py (lines 1–43)
- lifespan: load_dotenv + init_db (16–21); FastAPI(lifespan=…) (24); sqlite3.Error → 500 JSON (27–29); routers/static unchanged (38–42).

MODIFIED: week2/app/routers/action_items.py (lines 1–45)
- Pydantic payloads/responses; response_model on routes; Query(note_id); 404 if mark_done updates 0 rows (39–44).

MODIFIED: week2/app/routers/notes.py (lines 1–26)
- NoteCreatePayload / NoteOut; model_validate from db records; 500 if insert race (11–17).

MODIFIED: week2/app/services/extract.py (lines 1–151; typing cleanup from same pass)
- Prefer built-in list[str] / list[…] annotations (e.g. 34–36, 59, 103, 142–143) for consistency with ruff; behavior unchanged.

NOT changed for Exercise 3: week2/tests/test_extract.py, week2/frontend/index.html (API shapes kept compatible; empty text now 422 vs former 400).
```


### Exercise 4: Use Agentic Mode to Automate a Small Task
Prompt: 
```
Implement the operations described in lines 59–61 of assignment.md based on Agentic mode. Testing must be conducted in the cs146s conda environment
``` 

Generated Code Snippets:
```
MODIFIED: week2/app/routers/notes.py (lines 17-21) - Added `list_all_notes` endpoint.
MODIFIED: week2/app/routers/action_items.py (lines 33-41) - Added `extract_llm` endpoint.
MODIFIED: week2/frontend/index.html (lines 33-35, 45, 78-95) - Added "Extract LLM" and "List Notes" buttons and their JavaScript logic.
NEW: week2/tests/test_endpoints.py (lines 1-40) - Added tests for `list_notes_endpoint` and `extract_llm_endpoint`.
```


### Exercise 5: Generate a README from the Codebase
Prompt: 
```
Generate a README from the codebase.
``` 

Generated Code Snippets:
```
NEW: week2/README.md (lines 1-100) - Generated a comprehensive README documenting the project features, setup, running instructions, API endpoints, and testing procedures.
```


## SUBMISSION INSTRUCTIONS
1. Hit a `Command (⌘) + F` (or `Ctrl + F`) to find any remaining `TODO`s in this file. If no results are found, congratulations – you've completed all required fields. 
2. Make sure you have all changes pushed to your remote repository for grading.
3. Submit via Gradescope. 