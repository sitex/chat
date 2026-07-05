"""Hot-reloading JSON loader.

Файлы в data_dir можно редактировать на ходу — изменения подхватываются
автоматически (проверяется mtime), перезапуск бота не нужен.

Директория задаётся через chatcore.config.setup(data_dir=...).
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config

_cache: dict[str, tuple[float, Any]] = {}


def load(name: str) -> Any:
    """Загрузить <data_dir>/<name>.json, перечитывая файл при изменении."""
    path = config.get_data_dir() / f"{name}.json"
    mtime = os.path.getmtime(path)
    cached = _cache.get(name)
    if cached is None or cached[0] != mtime:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _cache[name] = (mtime, data)
        return data
    return cached[1]
