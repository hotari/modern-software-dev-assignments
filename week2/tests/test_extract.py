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
