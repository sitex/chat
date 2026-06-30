"""Память диалога на чат (SQLite).

История сообщений + настройки языка + обобщённый seen-state.

Путь к БД задаётся через chatcore.config.setup(db_path=...).
"""
from __future__ import annotations

import sqlite3
import time

from . import config

_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        db_path = config.get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   chat_id INTEGER NOT NULL,
                   role TEXT NOT NULL,
                   content TEXT NOT NULL,
                   ts REAL NOT NULL
               )"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                   chat_id INTEGER PRIMARY KEY,
                   lang_mode TEXT NOT NULL DEFAULT 'auto',
                   last_lang TEXT NOT NULL DEFAULT 'ru'
               )"""
        )
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id)"
        )
        # Обобщённый seen-state: namespace позволяет хранить несколько
        # независимых «уже показанных» множеств на один чат.
        # Примеры namespace: 'riddles', 'tricks', 'quotes'.
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS seen_items (
                   chat_id INTEGER NOT NULL,
                   namespace TEXT NOT NULL DEFAULT '',
                   item_key TEXT NOT NULL,
                   PRIMARY KEY (chat_id, namespace, item_key)
               )"""
        )
        # Idempotent-миграции для БД, созданных старыми версиями без last_lang
        try:
            _conn.execute(
                "ALTER TABLE settings ADD COLUMN last_lang TEXT NOT NULL DEFAULT 'ru'"
            )
        except sqlite3.OperationalError:
            pass  # колонка уже существует
        _conn.commit()
    return _conn


# ---------- диалог ----------

def add(chat_id: int, role: str, content: str) -> None:
    db = _db()
    db.execute(
        "INSERT INTO messages(chat_id, role, content, ts) VALUES (?,?,?,?)",
        (chat_id, role, content, time.time()),
    )
    db.commit()


def history(chat_id: int, limit: int = 20) -> list[dict]:
    """Последние N сообщений в хронологическом порядке: [{'role','content'}]."""
    db = _db()
    rows = db.execute(
        "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def reset(chat_id: int) -> None:
    db = _db()
    db.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    db.commit()


# ---------- seen-state (обобщённый) ----------

def seen(chat_id: int, namespace: str = "") -> set[str]:
    """Ключи элементов, уже показанных в этом чате (переживают перезапуск)."""
    db = _db()
    rows = db.execute(
        "SELECT item_key FROM seen_items WHERE chat_id=? AND namespace=?",
        (chat_id, namespace),
    ).fetchall()
    return {r[0] for r in rows}


def add_seen(chat_id: int, key: str, namespace: str = "") -> None:
    db = _db()
    db.execute(
        "INSERT OR IGNORE INTO seen_items(chat_id, namespace, item_key) VALUES (?,?,?)",
        (chat_id, namespace, key),
    )
    db.commit()


def clear_seen(chat_id: int, namespace: str = "") -> None:
    db = _db()
    db.execute(
        "DELETE FROM seen_items WHERE chat_id=? AND namespace=?",
        (chat_id, namespace),
    )
    db.commit()


# ---------- настройки языка ----------

def get_lang_mode(chat_id: int) -> str:
    db = _db()
    row = db.execute(
        "SELECT lang_mode FROM settings WHERE chat_id=?", (chat_id,)
    ).fetchone()
    return row[0] if row else "auto"


def get_last_lang(chat_id: int) -> str:
    db = _db()
    row = db.execute(
        "SELECT last_lang FROM settings WHERE chat_id=?", (chat_id,)
    ).fetchone()
    return row[0] if row else "ru"


def set_last_lang(chat_id: int, lang: str) -> None:
    db = _db()
    db.execute(
        "INSERT INTO settings(chat_id, lang_mode, last_lang) VALUES (?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET last_lang=excluded.last_lang",
        (chat_id, "auto", lang),
    )
    db.commit()


def set_lang_mode(chat_id: int, mode: str) -> None:
    db = _db()
    db.execute(
        "INSERT INTO settings(chat_id, lang_mode) VALUES (?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET lang_mode=excluded.lang_mode",
        (chat_id, mode),
    )
    db.commit()
