"""on_message всегда отвечает пользователю, даже если LLM недоступен.

Регрессия «бот молчит на обычный текст»: зависший/упавший движок
не должен оставлять сообщение без ответа.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chatcore import llm, scaffold
from chatcore.scaffold import BotScaffold, ContentCommand


def _make_scaffold(**kwargs) -> BotScaffold:
    defaults = dict(
        bot_name="test-bot",
        start_text_ru="Привет!",
        start_text_en="Hello!",
        help_text_ru="Помощь",
        help_text_en="Help",
        fallback_ru="Что-то пошло не так. Повтори. 🍵",
        fallback_en="Something went wrong. Try again. 🍵",
        commands=[],
        study_paths=None,
        bot_commands_menu=False,
        extra_bot_commands=None,
    )
    defaults.update(kwargs)
    return BotScaffold(**defaults)


def _fake_update(text: str, lang_code: str = "ru", chat_id: int = 987654321):
    reply = AsyncMock()
    chat_action = AsyncMock()
    message = SimpleNamespace(text=text, reply_text=reply)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(language_code=lang_code),
        message=message,
    )
    ctx = SimpleNamespace(bot=SimpleNamespace(send_chat_action=chat_action))
    return update, ctx, reply


@pytest.mark.asyncio
async def test_on_message_replies_fallback_when_llm_fails(monkeypatch):
    async def _boom(*_a, **_k):
        raise RuntimeError("backend down")

    monkeypatch.setattr(llm, "generate", _boom)

    bot = _make_scaffold()
    update, ctx, reply = _fake_update("привет")
    await bot.on_message(update, ctx)

    assert reply.await_count == 1
    sent = reply.await_args.args[0]
    # Фолбэк-текст содержит слово из fallback_ru
    assert "пошло" in sent.lower() or "повтори" in sent.lower()


@pytest.mark.asyncio
async def test_on_message_replies_with_llm_text(monkeypatch):
    async def _gen(*_a, **_k):
        return "Любопытно. Расскажите ещё."

    monkeypatch.setattr(llm, "generate", _gen)

    bot = _make_scaffold()
    update, ctx, reply = _fake_update("привет")
    await bot.on_message(update, ctx)

    assert reply.await_count == 1
    sent = reply.await_args.args[0]
    assert "Любопытно" in sent


@pytest.mark.asyncio
async def test_on_message_strips_markdown(monkeypatch):
    async def _gen(*_a, **_k):
        return "это **жирный** и `код`"

    monkeypatch.setattr(llm, "generate", _gen)

    bot = _make_scaffold()
    update, ctx, reply = _fake_update("привет")
    await bot.on_message(update, ctx)

    sent = reply.await_args.args[0]
    assert "*" not in sent and "`" not in sent
    assert "жирный" in sent and "код" in sent


def test_reply_keyboard_ru():
    """Клавиатура генерируется из списка ContentCommand."""
    cmd = ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨")
    bot = _make_scaffold(commands=[cmd])
    kb = bot._reply_keyboard("ru")
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "Цитату ✨" in buttons


def test_reply_keyboard_en():
    cmd = ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨")
    bot = _make_scaffold(commands=[cmd])
    kb = bot._reply_keyboard("en")
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "Quote ✨" in buttons


def test_pick_item_with_seen_no_repeat(tmp_path):
    """seen-логика: элементы не повторяются до исчерпания."""
    import json
    from chatcore import memory

    chat_id = 444555
    items = [{"ru": f"item{i}", "en": f"item{i}"} for i in range(5)]
    # Создаём ContentCommand с seen_ns
    cmd = ContentCommand("q", "quotes", "cb_q", "Q", "Q", seen_ns="test_ns")

    seen_keys: list[str] = []
    for _ in range(5):
        item = scaffold._pick_item(items, chat_id, cmd)
        key = scaffold._default_key(item)
        seen_keys.append(key)

    assert len(set(seen_keys)) == 5  # все 5 разные


def test_auto_format_quote():
    item = {"ru": "Всё просто.", "en": "It's simple."}
    out = scaffold._auto_format(item, "ru")
    assert "Всё просто." in out


def test_auto_format_riddle_bilingual():
    item = {"q_ru": "вопрос", "a_ru": "ответ", "q_en": "question", "a_en": "answer"}
    out = scaffold._auto_format(item, "ru")
    assert "Загадка:" in out and "Riddle:" in out


def test_auto_format_riddle_english_only():
    item = {"q_en": "Knock knock!", "a_en": "Who's there?"}
    out = scaffold._auto_format(item, "en")
    assert "Загадка:" not in out
    assert "Riddle:" in out
