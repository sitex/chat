"""Тесты admin-команд и вспомогательных функций memory."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chatcore import admin, llm, memory
from chatcore.admin import is_admin, parse_admin_ids
from chatcore.scaffold import BotScaffold, ContentCommand


def _make_scaffold(**kwargs) -> BotScaffold:
    defaults = dict(
        bot_name="test-bot",
        start_text_ru="Привет!",
        start_text_en="Hello!",
        help_text_ru="Помощь",
        help_text_en="Help",
        fallback_ru="Что-то пошло не так.",
        fallback_en="Something went wrong.",
        commands=[],
        study_paths=None,
        bot_commands_menu=False,
        extra_bot_commands=None,
    )
    defaults.update(kwargs)
    return BotScaffold(**defaults)


def _fake_update(user_id: int = 42):
    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, language_code="ru"),
        effective_chat=SimpleNamespace(id=user_id),
        message=message,
    )
    ctx = SimpleNamespace(args=[])
    return update, ctx, reply


# --- parse_admin_ids ---

def test_parse_admin_ids_basic():
    assert parse_admin_ids("123,456") == {123, 456}


def test_parse_admin_ids_spaces_and_empty():
    assert parse_admin_ids(" 123 , ,456, ") == {123, 456}
    assert parse_admin_ids("") == set()


def test_parse_admin_ids_garbage():
    result = parse_admin_ids("123,abc")
    assert result == {123}


# --- is_admin ---

def test_is_admin_reads_env(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "42")
    assert is_admin(42) is True
    assert is_admin(1) is False


def test_is_admin_missing_env(monkeypatch):
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    assert is_admin(42) is False


# --- не-админ молчит ---

@pytest.mark.asyncio
async def test_non_admin_silent(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "999")
    scaffold = _make_scaffold()
    handlers = admin.make_admin_handlers(scaffold)
    update, ctx, reply = _fake_update(user_id=1)  # не-админ

    for h in handlers:
        await h.callback(update, ctx)

    assert reply.await_count == 0


# --- admin_status ---

@pytest.mark.asyncio
async def test_admin_status_replies(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "42")
    monkeypatch.setattr(llm, "active_backend", lambda: "test-backend")

    scaffold = _make_scaffold()
    handlers = admin.make_admin_handlers(scaffold)
    status_handler = handlers[0]

    update, ctx, reply = _fake_update(user_id=42)
    await status_handler.callback(update, ctx)

    assert reply.await_count == 1
    text = reply.await_args.args[0]
    assert "test-backend" in text
    assert "chatcore" in text
    assert "Uptime" in text


# --- admin_stats ---

@pytest.mark.asyncio
async def test_admin_stats_counts(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "42")
    # Заполняем несколько чатов
    memory.add(100, "user", "hello")
    memory.add(200, "user", "world")

    scaffold = _make_scaffold()
    handlers = admin.make_admin_handlers(scaffold)
    stats_handler = handlers[1]

    update, ctx, reply = _fake_update(user_id=42)
    await stats_handler.callback(update, ctx)

    assert reply.await_count == 1
    text = reply.await_args.args[0]
    assert "2" in text  # count_chats должен вернуть 2


# --- admin_reset ---

@pytest.mark.asyncio
async def test_admin_reset_validates_arg(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "42")
    memory.add(555, "user", "test")

    scaffold = _make_scaffold()
    handlers = admin.make_admin_handlers(scaffold)
    reset_handler = handlers[2]

    # Без аргументов
    update, ctx, reply = _fake_update(user_id=42)
    ctx.args = []
    await reset_handler.callback(update, ctx)
    assert "Использование" in reply.await_args.args[0]
    # memory не тронута
    assert memory.history(555) != []

    # Нечисловой аргумент
    update2, ctx2, reply2 = _fake_update(user_id=42)
    ctx2.args = ["abc"]
    await reset_handler.callback(update2, ctx2)
    assert "Использование" in reply2.await_args.args[0]


@pytest.mark.asyncio
async def test_admin_reset_clears_chat(monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "42")
    memory.add(555, "user", "to be removed")
    assert memory.history(555) != []

    cmd_with_seen = ContentCommand(
        command="quote",
        dataset="quotes",
        callback_id="cb_quote",
        label_ru="Цитата",
        label_en="Quote",
        seen_ns="quotes",
    )
    memory.add_seen(555, "item1", "quotes")

    scaffold = _make_scaffold(commands=[cmd_with_seen])
    handlers = admin.make_admin_handlers(scaffold)
    reset_handler = handlers[2]

    update, ctx, reply = _fake_update(user_id=42)
    ctx.args = ["555"]
    await reset_handler.callback(update, ctx)

    assert reply.await_count == 1
    assert "555" in reply.await_args.args[0]
    assert memory.history(555) == []
    assert memory.seen(555, "quotes") == set()


# --- memory.top_chats окно ---

def test_memory_top_chats_window():
    now = time.time()
    # Сообщения «сегодня»
    memory.add(10, "user", "msg1")
    memory.add(10, "user", "msg2")
    memory.add(20, "user", "msg3")

    # Делаем вид, что сообщение от чата 30 было 2 дня назад
    db = memory._db()
    db.execute(
        "INSERT INTO messages(chat_id, role, content, ts) VALUES (?,?,?,?)",
        (30, "user", "old", now - 2 * 86400),
    )
    db.commit()

    since_24h = now - 86400
    top = memory.top_chats(since_24h)
    chat_ids = [cid for cid, _ in top]

    assert 10 in chat_ids
    assert 20 in chat_ids
    assert 30 not in chat_ids  # старое сообщение не попадает в окно
