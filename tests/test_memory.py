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


# ---------- rolling summary ----------

SCHAT = 999888777


def test_summary_empty_initially():
    summary, covered = memory.get_summary(SCHAT)
    assert summary == ""
    assert covered == 0


def test_summary_set_and_get():
    memory.set_summary(SCHAT, "Пользователь спросил о Loosh.", 5)
    summary, covered = memory.get_summary(SCHAT)
    assert "Loosh" in summary
    assert covered == 5


def test_summary_update():
    memory.set_summary(SCHAT, "Первое резюме.", 3)
    memory.set_summary(SCHAT, "Обновлённое резюме.", 7)
    summary, covered = memory.get_summary(SCHAT)
    assert "Обновлённое" in summary
    assert covered == 7


def test_reset_clears_summary():
    memory.add(SCHAT, "user", "test")
    memory.set_summary(SCHAT, "резюме", 1)
    memory.reset(SCHAT)
    assert memory.history(SCHAT) == []
    summary, covered = memory.get_summary(SCHAT)
    assert summary == ""
    assert covered == 0


def test_history_after():
    memory.reset(SCHAT)
    for i in range(5):
        memory.add(SCHAT, "user", f"msg {i}")
    # получить id первого сообщения
    db = memory._db()
    first_id = db.execute(
        "SELECT id FROM messages WHERE chat_id=? ORDER BY id LIMIT 1", (SCHAT,)
    ).fetchone()[0]
    hist = memory.history_after(SCHAT, first_id, limit=10)
    assert len(hist) == 4
    assert "msg 1" in hist[0]["content"]


def test_pending_to_summarize():
    memory.reset(SCHAT)
    for i in range(10):
        memory.add(SCHAT, "user", f"msg {i}")
    pending = memory.pending_to_summarize(SCHAT, after_id=0, keep=3)
    assert len(pending) == 7  # 10 - 3 дословных
    assert "id" in pending[0]
    assert pending[0]["role"] == "user"
