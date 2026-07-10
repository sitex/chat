"""Unit-тесты для scripts/roundtable.py (выбор следующего оратора)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# roundtable живёт в scripts/, добавляем корень репо в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import roundtable

from chatcore import llm


def _p(num: int, name: str, key: str = "") -> dict:
    return {"num": num, "name": name, "key": key or name.lower()}


P1 = _p(1, "Патрик")
P3 = _p(3, "Дэн")
P7 = _p(7, "Ричард")


# ── pick_next: передача DIRECTOR_BACKEND в llm.generate ──────────────────────

@pytest.mark.asyncio
async def test_pick_next_passes_director_backend(monkeypatch):
    """При заданном DIRECTOR_BACKEND llm.generate получает backend=<он>."""
    captured: dict = {}

    async def _fake_generate(system, messages, backend=None):
        captured["backend"] = backend
        return "3"

    monkeypatch.setattr(roundtable, "DIRECTOR_BACKEND", "cliproxy")
    monkeypatch.setattr(llm, "generate", _fake_generate)

    got = await roundtable.pick_next(
        [P1, P3], [("Ведущий", "начнём")], "тема")
    assert captured["backend"] == "cliproxy"
    assert got is P3


@pytest.mark.asyncio
async def test_pick_next_empty_director_backend_passes_none(monkeypatch):
    """Пустой DIRECTOR_BACKEND → backend=None (общий _resolve_backend)."""
    captured: dict = {}

    async def _fake_generate(system, messages, backend=None):
        captured["backend"] = backend
        return "1"

    monkeypatch.setattr(roundtable, "DIRECTOR_BACKEND", "")
    monkeypatch.setattr(llm, "generate", _fake_generate)

    await roundtable.pick_next([P1, P3], [("Ведущий", "начнём")], "тема")
    assert captured["backend"] is None


# ── pick_next: фолбэк по порядку при исключении режиссёра ────────────────────

@pytest.mark.asyncio
async def test_pick_next_falls_back_on_llm_error(monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("director down")

    monkeypatch.setattr(llm, "generate", _boom)

    got = await roundtable.pick_next(
        [P1, P3, P7], [("Ведущий", "начнём")], "тема")
    assert got is P1


@pytest.mark.asyncio
async def test_pick_next_falls_back_on_non_number(monkeypatch):
    """Не-номер в ответе режиссёра → первый по порядку."""
    async def _chatty(*_a, **_k):
        return "думаю, никто"

    monkeypatch.setattr(llm, "generate", _chatty)

    got = await roundtable.pick_next(
        [P3, P7], [("Ведущий", "начнём")], "тема")
    assert got is P3


# ── pick_next: короткие пути без LLM ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_pick_next_addressed_skips_llm(monkeypatch):
    """Прямое обращение «№7» в последней реплике → LLM не вызывается."""
    async def _sentinel(*_a, **_k):
        pytest.fail("llm.generate не должен вызываться при прямом обращении")

    monkeypatch.setattr(llm, "generate", _sentinel)

    got = await roundtable.pick_next(
        [P1, P7], [("Дэн", "а что скажет №7?")], "тема")
    assert got is P7


@pytest.mark.asyncio
async def test_pick_next_addressed_by_name_skips_llm(monkeypatch):
    async def _sentinel(*_a, **_k):
        pytest.fail("llm.generate не должен вызываться при обращении по имени")

    monkeypatch.setattr(llm, "generate", _sentinel)

    got = await roundtable.pick_next(
        [P1, P7], [("Дэн", "Ричард, твой ход")], "тема")
    assert got is P7


@pytest.mark.asyncio
async def test_pick_next_single_remaining_skips_llm(monkeypatch):
    async def _sentinel(*_a, **_k):
        pytest.fail("llm.generate не должен вызываться для одного оставшегося")

    monkeypatch.setattr(llm, "generate", _sentinel)

    got = await roundtable.pick_next([P3], [("Ведущий", "начнём")], "тема")
    assert got is P3


@pytest.mark.asyncio
async def test_pick_next_empty_transcript_skips_llm(monkeypatch):
    async def _sentinel(*_a, **_k):
        pytest.fail("llm.generate не должен вызываться при пустом транскрипте")

    monkeypatch.setattr(llm, "generate", _sentinel)

    got = await roundtable.pick_next([P1, P3], [], "тема")
    assert got is P1
