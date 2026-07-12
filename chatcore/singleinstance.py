"""Защита от запуска второго инстанса бота на одной машине.

Два уровня:
  1. flock на .lock-файл рядом с БД (same-user, быстрый старт).
  2. PID-файл в /tmp по хэшу токена (cross-user: system vs user service).

При обнаружении дубля — выход кодом 0, чтобы systemd Restart=on-failure
не создавал бесконечный цикл перезапусков.
"""
from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import IO

log = logging.getLogger("chatcore.singleinstance")


def acquire(lock_path: Path) -> IO:
    """Взять эксклюзивный flock; вернуть открытый файл (держать до конца жизни процесса).

    Если лок занят другим пользователем (PermissionError) или тем же — выход 0.
    """
    try:
        f: IO = open(lock_path, "a")
    except PermissionError:
        log.critical(
            "Лок %s принадлежит другому пользователю — дубль system/user. "
            "Проверьте: systemctl status <svc> и systemctl --user status <svc>. "
            "Выходим чисто.",
            lock_path,
        )
        sys.exit(0)
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        log.critical(
            "Инстанс уже запущен (лок %s занят). "
            "Проверьте оба systemd-менеджера: "
            "systemctl status <svc> и systemctl --user status <svc>. "
            "Выходим чисто.",
            lock_path,
        )
        sys.exit(0)
    f.write(str(os.getpid()) + "\n")
    f.flush()
    return f


def acquire_token_pidfile(bot_token: str) -> None:
    """Cross-user защита через PID-файл в /tmp, ключ — MD5 токена.

    Вызывать до старта polling. Если другой процесс (любой пользователь)
    уже держит тот же токен — выход 0 (чистый, systemd не перезапустит).
    """
    if not bot_token:
        return
    token_hash = hashlib.md5(bot_token.encode()).hexdigest()[:12]
    pid_path = Path(f"/tmp/chatbot-{token_hash}.pid")
    my_pid = os.getpid()

    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text().strip())
        except (ValueError, OSError):
            existing_pid = None

        if existing_pid and existing_pid != my_pid:
            proc_exists = Path(f"/proc/{existing_pid}").exists()
            if proc_exists:
                log.critical(
                    "Дубль инстанса: бот уже запущен как PID %d "
                    "(возможно, другой пользователь). Выходим чисто.",
                    existing_pid,
                )
                sys.exit(0)

    try:
        pid_path.write_text(str(my_pid))
    except PermissionError:
        log.critical(
            "PID-файл %s принадлежит другому пользователю — дубль. Выходим чисто.",
            pid_path,
        )
        sys.exit(0)
