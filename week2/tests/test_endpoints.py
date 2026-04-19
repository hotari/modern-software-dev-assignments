from __future__ import annotations

from unittest.mock import patch
from fastapi.testclient import TestClient
from ..app.main import app
from ..app.db import Note

client = TestClient(app)

def test_list_notes_endpoint():
    mock_notes = [
        Note(id=1, content="Note 1", created_at="2023-01-01 10:00:00"),
        Note(id=2, content="Note 2", created_at="2023-01-01 11:00:00"),
    ]
    with patch("week2.app.db.list_notes", return_value=mock_notes):
        response = client.get("/notes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["content"] == "Note 1"
        assert data[1]["id"] == 2
        assert data[1]["content"] == "Note 2"

def test_extract_llm_endpoint():
    mock_items = ["Task 1", "Task 2"]
    with patch("week2.app.routers.action_items.extract_action_items_llm", return_value=mock_items), \
         patch("week2.app.routers.action_items.db.insert_note", return_value=123), \
         patch("week2.app.routers.action_items.db.insert_action_items", return_value=[1, 2]):
        
        payload = {"text": "Some notes", "save_note": True}
        response = client.post("/action-items/extract-llm", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["note_id"] == 123
        assert len(data["items"]) == 2
        assert data["items"][0]["text"] == "Task 1"
        assert data["items"][1]["text"] == "Task 2"
