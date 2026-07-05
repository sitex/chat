"""Sliding-window rate-limiter для on_message (in-memory).

Счётчики живут в памяти процесса: перезапуск бота сбрасывает окна —
приемлемо для защиты LLM-бэкенда от потока сообщений.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """Лимит max_calls вызовов на пользователя за period_sec (скользящее окно).

    max_calls <= 0 отключает лимит (is_allowed всегда True).
    clock инъецируется для тестов (по умолчанию time.monotonic).
    """

    def __init__(
        self,
        max_calls: int,
        period_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_calls = max_calls
        self.period_sec = period_sec
        self._clock = clock
        self._calls: dict[int, deque[float]] = {}
        self._warned: set[int] = set()

    def is_allowed(self, user_id: int) -> bool:
        """True — вызов разрешён (и учтён). False — лимит исчерпан."""
        if self.max_calls <= 0:
            return True
        now = self._clock()
        dq = self._calls.setdefault(user_id, deque())
        cutoff = now - self.period_sec
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) < self.max_calls:
            dq.append(now)
            self._warned.discard(user_id)
            return True
        return False

    def should_warn(self, user_id: int) -> bool:
        """True один раз за окно превышения — чтобы не спамить отказами.

        Флаг сбрасывается, когда is_allowed снова возвращает True.
        """
        if user_id in self._warned:
            return False
        self._warned.add(user_id)
        return True
