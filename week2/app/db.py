from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True)
class Note:
    """Row from `notes` as a plain object (not tied to HTTP schema)."""

    id: int
    content: str
    created_at: str


@dataclass(frozen=True)
class ActionItem:
    """Row from `action_items`."""

    id: int
    note_id: int | None
    text: str
    done: bool
    created_at: str


def _db_path() -> str:
    return str(get_settings().db_path)


def ensure_data_directory_exists() -> None:
    get_settings().data_dir.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_data_directory_exists()
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    ensure_data_directory_exists()
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS action_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER,
                text TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );
            """
        )
        connection.commit()


def _note_from_row(row: sqlite3.Row) -> Note:
    return Note(id=int(row["id"]), content=str(row["content"]), created_at=str(row["created_at"]))


def _action_item_from_row(row: sqlite3.Row) -> ActionItem:
    return ActionItem(
        id=int(row["id"]),
        note_id=row["note_id"],
        text=str(row["text"]),
        done=bool(row["done"]),
        created_at=str(row["created_at"]),
    )


def insert_note(content: str) -> int:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        connection.commit()
        return int(cursor.lastrowid)


def list_notes() -> list[Note]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, content, created_at FROM notes ORDER BY id DESC")
        return [_note_from_row(row) for row in cursor.fetchall()]


def get_note(note_id: int) -> Note | None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, content, created_at FROM notes WHERE id = ?",
            (note_id,),
        )
        row = cursor.fetchone()
        return _note_from_row(row) if row else None


def insert_action_items(items: list[str], note_id: int | None = None) -> list[int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        ids: list[int] = []
        for item in items:
            cursor.execute(
                "INSERT INTO action_items (note_id, text) VALUES (?, ?)",
                (note_id, item),
            )
            ids.append(int(cursor.lastrowid))
        connection.commit()
        return ids


def list_action_items(note_id: int | None = None) -> list[ActionItem]:
    with get_connection() as connection:
        cursor = connection.cursor()
        if note_id is None:
            cursor.execute(
                "SELECT id, note_id, text, done, created_at FROM action_items ORDER BY id DESC"
            )
        else:
            cursor.execute(
                "SELECT id, note_id, text, done, created_at FROM action_items WHERE note_id = ? ORDER BY id DESC",
                (note_id,),
            )
        return [_action_item_from_row(row) for row in cursor.fetchall()]


def mark_action_item_done(action_item_id: int, done: bool) -> bool:
    """Return True if a row was updated, False if id did not exist."""
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE action_items SET done = ? WHERE id = ?",
            (1 if done else 0, action_item_id),
        )
        connection.commit()
        return cursor.rowcount > 0
