"""Единая точка конфигурации chatcore.

Вызови config.setup() в точке входа бота ДО любых других chatcore-вызовов.
Все параметры опциональны — дефолты работают для большинства ботов.

Пример:
    from chatcore import config
    config.setup(
        data_dir="data",
        db_path="mybot.db",
        assistant_label="Патрик Джейн",
        user_label="Пользователь",
    )
"""
from __future__ import annotations

import os
from pathlib import Path

# --- рантайм-состояние (модуль-синглтон) ---

_data_dir: Path | None = None
_db_path: Path | None = None
_assistant_label: str = "Ассистент"
_user_label: str = "Пользователь"


def setup(
    *,
    data_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    assistant_label: str | None = None,
    user_label: str | None = None,
) -> None:
    """Настроить chatcore.

    Args:
        data_dir: папка с JSON-датасетами (data_store.load ищет там).
                  По умолчанию — 'data/' рядом с рабочей директорией.
        db_path:  путь к SQLite-базе. По умолчанию — 'bot.db' в CWD.
        assistant_label: имя ассистента в «плоском» тексте для grok
                         (напр. «Lee Jacobs», «Патрик Джейн»).
        user_label: метка пользователя для grok (напр. «Пользователь», «Студент»).
    """
    global _data_dir, _db_path, _assistant_label, _user_label
    if data_dir is not None:
        _data_dir = Path(data_dir).resolve()
    if db_path is not None:
        _db_path = Path(db_path).resolve()
    if assistant_label is not None:
        _assistant_label = assistant_label
    if user_label is not None:
        _user_label = user_label


def get_data_dir() -> Path:
    if _data_dir is not None:
        return _data_dir
    return Path("data").resolve()


def get_db_path() -> Path:
    if _db_path is not None:
        return _db_path
    env_path = os.environ.get("DB_PATH")
    if env_path:
        return Path(env_path).resolve()
    return Path("bot.db").resolve()


def get_assistant_label() -> str:
    return _assistant_label


def get_user_label() -> str:
    return _user_label
