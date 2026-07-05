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
        effective_user=SimpleNamespace(id=chat_id, language_code=lang_code),
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


# ── Phase 1.3: пустой / отсутствующий датасет ─────────────────────────────────

@pytest.mark.asyncio
async def test_handle_content_cmd_empty_dataset(tmp_path):
    """Пустой датасет → вежливое сообщение, без исключения."""
    from chatcore import data_store as ds

    # conftest уже настроил config с tmp_path/data; пишем пустой файл туда
    data_dir = tmp_path / "data"
    (data_dir / "empty.json").write_text("[]", encoding="utf-8")
    ds._cache.clear()

    cmd = ContentCommand("q", "empty", "cb_q", "Q", "Q")
    bot = _make_scaffold(commands=[cmd])
    replies = []

    async def reply_fn(text, parse_mode=None, reply_markup=None):
        replies.append(text)

    await bot._handle_content_cmd(cmd, chat_id=1, lang="ru", reply_fn=reply_fn)
    assert len(replies) == 1
    assert "нечего" in replies[0] or "check back" in replies[0]


@pytest.mark.asyncio
async def test_handle_content_cmd_missing_dataset(tmp_path):
    """Отсутствующий файл датасета → вежливое сообщение, без исключения."""
    from chatcore import data_store as ds
    ds._cache.clear()

    cmd = ContentCommand("q", "nonexistent", "cb_q", "Q", "Q")
    bot = _make_scaffold(commands=[cmd])
    replies = []

    async def reply_fn(text, parse_mode=None, reply_markup=None):
        replies.append(text)

    await bot._handle_content_cmd(cmd, chat_id=1, lang="en", reply_fn=reply_fn)
    assert len(replies) == 1
    assert "check back" in replies[0]


# ── Phase 1.4: on_error локализован ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_error_ru(monkeypatch):
    """on_error отвечает на русском для русскоязычного пользователя."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    # Патчим scaffold.Update чтобы isinstance-проверка прошла с SimpleNamespace
    monkeypatch.setattr(scaffold, "Update", SimpleNamespace)

    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply)
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=111),
        effective_user=SimpleNamespace(language_code="ru"),
    )
    ctx = SimpleNamespace(error=RuntimeError("boom"))

    bot = _make_scaffold()
    await bot.on_error(update, ctx)

    assert reply.await_count == 1
    text = reply.await_args.args[0]
    assert "пошло" in text.lower()


@pytest.mark.asyncio
async def test_on_error_en(monkeypatch):
    """on_error отвечает на английском при lang_mode=en."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from chatcore import memory

    monkeypatch.setattr(scaffold, "Update", SimpleNamespace)

    chat_id = 222
    memory.set_lang_mode(chat_id, "en")

    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply)
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(language_code="en"),
    )
    ctx = SimpleNamespace(error=RuntimeError("boom"))

    bot = _make_scaffold()
    await bot.on_error(update, ctx)

    assert reply.await_count == 1
    text = reply.await_args.args[0]
    assert "went wrong" in text.lower()


# ── Phase 1.5: язык кнопки = язык команды ─────────────────────────────────────

@pytest.mark.asyncio
async def test_on_callback_uses_ui_lang(monkeypatch):
    """on_callback использует _ui_lang, а не get_last_lang — /lang en уважается."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from chatcore import memory

    chat_id = 333
    memory.set_lang_mode(chat_id, "en")

    cmd = ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨")
    bot = _make_scaffold(commands=[cmd])

    replies = []
    reply_text = AsyncMock(side_effect=lambda t, **kw: replies.append(t))
    message = SimpleNamespace(
        chat_id=chat_id,
        reply_text=reply_text,
    )
    query = SimpleNamespace(
        answer=AsyncMock(),
        data="cb_quote",
        message=message,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(language_code="en"),
        effective_chat=SimpleNamespace(id=chat_id),
    )
    ctx = SimpleNamespace()

    await bot.on_callback(update, ctx)

    # Кнопка должна отработать (один ответ)
    assert reply_text.await_count == 1


# ── Phase 5.2: порядок регистрации extra_handlers ─────────────────────────────

def test_build_app_extra_handlers_order(monkeypatch):
    """extra_handlers регистрируются после on_message, до catch-all CallbackQueryHandler."""
    from unittest.mock import MagicMock, patch

    from telegram.ext import CallbackQueryHandler as CQH
    from telegram.ext import MessageHandler as MH

    monkeypatch.setenv("BOT_TOKEN", "fake:token12345")

    handlers_registered = []
    fake_app = MagicMock()
    fake_app.add_handler.side_effect = lambda h: handlers_registered.append(h)

    with patch("chatcore.scaffold.ApplicationBuilder") as MockBuilder:
        (
            MockBuilder.return_value
            .token.return_value
            .post_init.return_value
            .build.return_value
        ) = fake_app

        extra = MagicMock()
        bot = _make_scaffold(extra_handlers=[extra])
        bot.build_app()

    # Позиции в порядке регистрации
    extra_idx = handlers_registered.index(extra)
    msg_idx = next(i for i, h in enumerate(handlers_registered) if isinstance(h, MH))
    cq_idx = next(i for i, h in enumerate(handlers_registered) if isinstance(h, CQH))

    assert msg_idx < extra_idx, "extra_handler должен быть после on_message"
    assert extra_idx < cq_idx, "extra_handler должен быть до catch-all CallbackQueryHandler"


# ── Phase 3: rate-limit и admin-хендлеры ──────────────────────────────────────

@pytest.mark.asyncio
async def test_on_message_rate_limited(monkeypatch):
    """LLM вызывается ровно 2 раза, 3-е сообщение получает предупреждение."""
    call_count = [0]

    async def _gen(*_a, **_k):
        call_count[0] += 1
        return "ответ"

    monkeypatch.setattr(llm, "generate", _gen)

    bot = _make_scaffold(rate_limit=2)
    update1, ctx1, reply1 = _fake_update("msg1")
    update2, ctx2, reply2 = _fake_update("msg2")
    update3, ctx3, reply3 = _fake_update("msg3")

    await bot.on_message(update1, ctx1)
    await bot.on_message(update2, ctx2)
    await bot.on_message(update3, ctx3)

    assert call_count[0] == 2
    assert reply3.await_count == 1
    text = reply3.await_args.args[0]
    assert "подождите" in text.lower() or "wait" in text.lower()


@pytest.mark.asyncio
async def test_on_message_rate_limit_warns_once(monkeypatch):
    """При 4 сообщениях с лимитом 2: ровно одно предупреждение (3-е), 4-е молчит."""
    async def _gen(*_a, **_k):
        return "ответ"

    monkeypatch.setattr(llm, "generate", _gen)

    bot = _make_scaffold(rate_limit=2)
    replies = []
    for i in range(4):
        update, ctx, reply = _fake_update(f"msg{i}")
        await bot.on_message(update, ctx)
        replies.append(reply)

    # msg1, msg2 — LLM; msg3 — предупреждение; msg4 — молчание
    assert replies[2].await_count == 1   # предупреждение
    assert replies[3].await_count == 0   # молчание


@pytest.mark.asyncio
async def test_on_message_rate_limit_disabled(monkeypatch):
    """rate_limit=0 отключает лимит — все 15 сообщений доходят до LLM."""
    call_count = [0]

    async def _gen(*_a, **_k):
        call_count[0] += 1
        return "ответ"

    monkeypatch.setattr(llm, "generate", _gen)

    bot = _make_scaffold(rate_limit=0)
    for i in range(15):
        update, ctx, _ = _fake_update(f"msg{i}")
        await bot.on_message(update, ctx)

    assert call_count[0] == 15


def test_build_app_registers_admin_handlers(monkeypatch):
    """admin_status/admin_stats/admin_reset регистрируются до MessageHandler."""
    from unittest.mock import MagicMock, patch

    from telegram.ext import CommandHandler as CH
    from telegram.ext import MessageHandler as MH

    monkeypatch.setenv("BOT_TOKEN", "fake:token12345")

    handlers_registered = []
    fake_app = MagicMock()
    fake_app.add_handler.side_effect = lambda h: handlers_registered.append(h)

    with patch("chatcore.scaffold.ApplicationBuilder") as MockBuilder:
        (
            MockBuilder.return_value
            .token.return_value
            .post_init.return_value
            .build.return_value
        ) = fake_app

        bot = _make_scaffold()
        bot.build_app()

    msg_idx = next(i for i, h in enumerate(handlers_registered) if isinstance(h, MH))
    admin_commands = {"admin_status", "admin_stats", "admin_reset"}
    for h in handlers_registered:
        if isinstance(h, CH):
            cmds = set(h.commands)
            if cmds & admin_commands:
                idx = handlers_registered.index(h)
                assert idx < msg_idx, f"admin handler {cmds} должен быть до MessageHandler"
                admin_commands -= cmds

    assert not admin_commands, f"Не найдены хендлеры: {admin_commands}"
