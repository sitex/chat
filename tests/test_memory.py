"""Тесты слоя памяти (SQLite) — история и namespaced seen-state."""
import pytest

from chatcore import memory

CHAT = 111222333


def test_add_and_history():
    memory.add(CHAT, "user", "Привет")
    memory.add(CHAT, "assistant", "Добрый день")
    hist = memory.history(CHAT)
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert hist[1]["role"] == "assistant"


def test_history_limit():
    memory.reset(CHAT)
    for i in range(25):
        memory.add(CHAT, "user", f"msg {i}")
    hist = memory.history(CHAT, limit=10)
    assert len(hist) == 10
    assert "msg 24" in hist[-1]["content"]


def test_reset():
    memory.add(CHAT, "user", "test")
    memory.reset(CHAT)
    assert memory.history(CHAT) == []


def test_seen_empty_initially():
    assert memory.seen(CHAT, "riddles") == set()


def test_seen_add_and_retrieve():
    memory.add_seen(CHAT, "key1", "riddles")
    memory.add_seen(CHAT, "key2", "riddles")
    s = memory.seen(CHAT, "riddles")
    assert "key1" in s and "key2" in s


def test_seen_clear():
    memory.add_seen(CHAT, "key1", "riddles")
    memory.clear_seen(CHAT, "riddles")
    assert memory.seen(CHAT, "riddles") == set()


def test_seen_namespaces_independent():
    """Разные namespace не пересекаются."""
    memory.add_seen(CHAT, "item1", "riddles")
    memory.add_seen(CHAT, "item1", "tricks")
    memory.clear_seen(CHAT, "riddles")
    assert "item1" not in memory.seen(CHAT, "riddles")
    assert "item1" in memory.seen(CHAT, "tricks")


def test_lang_mode_default_auto():
    assert memory.get_lang_mode(CHAT + 1) == "auto"


def test_lang_mode_set():
    memory.set_lang_mode(CHAT, "en")
    assert memory.get_lang_mode(CHAT) == "en"
    memory.set_lang_mode(CHAT, "auto")
    assert memory.get_lang_mode(CHAT) == "auto"


def test_last_lang_default_ru():
    assert memory.get_last_lang(CHAT + 2) == "ru"


def test_last_lang_set():
    memory.set_last_lang(CHAT, "en")
    assert memory.get_last_lang(CHAT) == "en"
