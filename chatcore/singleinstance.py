"""Защита от запуска второго инстанса бота на одной машине.

Использование:
    _lock = singleinstance.acquire(Path("bot.db.lock"))
    # держать _lock живым до конца процесса — GC не должен закрыть файл
"""
from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path
from typing import IO

log = logging.getLogger("chatcore.singleinstance")


def acquire(lock_path: Path) -> IO:
    """Взять эксклюзивный flock; вернуть открытый файл (держать до конца жизни процесса).

    SystemExit(1) с CRITICAL-логом, если лок занят (второй инстанс) или файл
    недоступен на запись (лок создан другим пользователем — признак дубля
    system/user: следует проверить оба systemd-менеджера).
    """
    try:
        f: IO = open(lock_path, "a")
    except PermissionError as exc:
        log.critical(
            "Не удалось открыть файл лока %s: нет прав на запись. "
            "Возможно, инстанс запущен другим пользователем (дубль system/user). "
            "Проверьте: systemctl status <svc> и systemctl --user status <svc>",
            lock_path,
        )
        raise SystemExit(1) from exc
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        f.close()
        log.critical(
            "Инстанс уже запущен (лок %s занят). "
            "Проверьте оба systemd-менеджера: "
            "systemctl status <svc> и systemctl --user status <svc>",
            lock_path,
        )
        raise SystemExit(1) from exc
    f.write(str(os.getpid()) + "\n")
    f.flush()
    return f
