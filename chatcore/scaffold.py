"""Универсальный каркас Telegram-бота на chatcore.

Предоставляет готовые хендлеры (start/help/reset/lang/on_message/on_callback/on_error)
и фабрику `run()` для запуска. Бот-специфика задаётся через параметры.

Контент-команды (quote/riddle/etc.) описываются декларативно через список `ContentCommand`.
Scaffold автоматически регистрирует хендлеры, кнопки и callbacks для них.

Пример использования:
    from chatcore import config, scaffold

    config.setup(
        data_dir="data",
        db_path="mybot.db",
        assistant_label="Патрик Джейн",
        user_label="Пользователь",
    )
    scaffold.run(
        bot_name="jane-bot",
        start_text_ru="Привет! Я Патрик Джейн...",
        start_text_en="Hello! I'm Patrick Jane...",
        help_text_ru="...",
        help_text_en="...",
        fallback_ru="Хм, отвлёкся. Попробуй ещё раз. 🍵",
        fallback_en="Hm, distracted. Try again. 🍵",
        commands=[
            ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨"),
        ],
        study_paths=None,  # список путей для RAG, или None
        bot_commands_menu=True,
    )
"""
from __future__ import annotations

import html
import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import Callable

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, data_store, llm, memory, persona, retrieval

log = logging.getLogger("chatcore.scaffold")

HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))

# Регексы для чистки markdown-артефактов из LLM-ответов
_MD_CLEANUP = [
    re.compile(r"\*{1,3}([^*\n]+?)\*{1,3}"),
    re.compile(r"__([^_\n]+?)__"),
    re.compile(r"`{1,3}([^`\n]+?)`{1,3}"),
]


@dataclass
class ContentCommand:
    """Описание одной контент-команды (цитата, загадка, урок…).

    Attrs:
        command:     имя команды без / (напр. 'quote', 'riddle').
        dataset:     имя JSON-файла в data/ без расширения (напр. 'quotes').
        callback_id: строка callback_data для inline-кнопки (напр. 'cb_quote').
        label_ru:    текст кнопки на русском (напр. 'Цитату ✨').
        label_en:    текст кнопки на английском.
        formatter:   опциональная функция (item, lang) -> str для нестандартных форматов.
                     По умолчанию — автоформатер: {title/type_*} + {body/def_*/signs_*}.
        seen_ns:     namespace для seen-state (None — без seen-логики; строка — с ней).
        key_fn:      функция (item) -> str для seen-ключа (по умолчанию — json-hash).
    """
    command: str
    dataset: str
    callback_id: str
    label_ru: str
    label_en: str
    formatter: Callable | None = None
    seen_ns: str | None = None
    key_fn: Callable | None = None


def _default_key(item: dict) -> str:
    """Ключ элемента для seen-state по умолчанию."""
    import hashlib, json as _json
    return hashlib.md5(_json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def _auto_format(item: dict, lang: str) -> str:
    """Авто-форматировщик элемента датасета."""
    # Цитата: {ru, en}
    if "ru" in item or "en" in item:
        ru = item.get("ru") or item.get("en")
        en = item.get("en") or item.get("ru")
        if ru == en:
            return f"«{ru}»"
        return f"«{ru}»\n\n«{en}»"

    # Загадка: {q_ru, q_en, a_ru, a_en}
    if "q_ru" in item or "q_en" in item:
        q_ru = item.get("q_ru") or item.get("q_en", "")
        a_ru = item.get("a_ru") or item.get("a_en", "")
        q_en = item.get("q_en") or item.get("q_ru", "")
        a_en = item.get("a_en") or item.get("a_ru", "")
        if q_ru == q_en and a_ru == a_en:
            return (
                f"Riddle:\n<i>{html.escape(q_en)}</i>\n"
                f"Answer: <tg-spoiler>{html.escape(a_en)}</tg-spoiler>"
            )
        return (
            f"Загадка:\n<i>{html.escape(q_ru)}</i>\n"
            f"Ответ: <tg-spoiler>{html.escape(a_ru)}</tg-spoiler>\n\n"
            f"Riddle:\n<i>{html.escape(q_en)}</i>\n"
            f"Answer: <tg-spoiler>{html.escape(a_en)}</tg-spoiler>"
        )

    # Объект с заголовком и телом: {title_ru/title_en, body_ru/body_en}
    title = item.get(f"title_{lang}") or item.get("title_en") or item.get("title") or ""
    body = item.get(f"body_{lang}") or item.get("body_en") or item.get("body") or ""
    if title or body:
        t = html.escape(title)
        b = html.escape(body)
        if title and body:
            return f"<b>{t}</b>\n\n{b}"
        return f"<b>{t}</b>" if title else b

    # Тип личности: {type_*, signs_*, insight_*}
    type_label = item.get(f"type_{lang}") or item.get("type_en") or ""
    signs = item.get(f"signs_{lang}") or item.get("signs_en") or []
    insight = item.get(f"insight_{lang}") or item.get("insight_en") or ""
    if type_label or signs:
        signs_text = "\n".join(f"• {html.escape(s)}" for s in signs)
        h = "Тип:" if lang == "ru" else "Type:"
        return f"<b>{h} {html.escape(type_label)}</b>\n\n{signs_text}\n\n<i>{html.escape(insight)}</i>"

    # Концепт: {term_*, def_*}
    term = item.get(f"term_{lang}") or item.get("term") or ""
    defn = item.get(f"def_{lang}") or item.get("def_en") or ""
    if term:
        return f"<b>{html.escape(term)}</b>\n\n{html.escape(defn)}"

    # Фолбэк — отдаём всё что есть
    return str(item)


def _pick_with_seen(items: list, chat_id: int, ns: str, key_fn: Callable) -> dict:
    """Выбрать элемент без повторов; когда все показаны — новый круг."""
    seen_keys = memory.seen(chat_id, ns)
    pool = [it for it in items if key_fn(it) not in seen_keys]
    if not pool:
        memory.clear_seen(chat_id, ns)
        pool = items
    item = random.choice(pool)
    memory.add_seen(chat_id, key_fn(item), ns)
    return item


def _pick_item(items: list, chat_id: int, cmd: ContentCommand) -> dict:
    if cmd.seen_ns is not None:
        kf = cmd.key_fn or _default_key
        return _pick_with_seen(items, chat_id, cmd.seen_ns, kf)
    return random.choice(items)


def _format_item(item: dict, lang: str, cmd: ContentCommand) -> str:
    if cmd.formatter is not None:
        return cmd.formatter(item, lang)
    return _auto_format(item, lang)


def _needs_html(text: str) -> bool:
    return any(tag in text for tag in ("<b>", "<i>", "<tg-spoiler>"))


def _clean_md(text: str) -> str:
    for pat in _MD_CLEANUP:
        text = pat.sub(r"\1", text)
    return text


class BotScaffold:
    """Сконфигурированный каркас бота. Создаётся через run() или build()."""

    def __init__(
        self,
        bot_name: str,
        start_text_ru: str,
        start_text_en: str,
        help_text_ru: str,
        help_text_en: str,
        fallback_ru: str,
        fallback_en: str,
        commands: list[ContentCommand],
        study_paths: list[str] | None,
        bot_commands_menu: bool,
        extra_bot_commands: list[tuple[str, str]] | None,
        extra_handlers: list[BaseHandler] | None = None,
    ) -> None:
        self.bot_name = bot_name
        self.start_text_ru = start_text_ru
        self.start_text_en = start_text_en
        self.help_text_ru = help_text_ru
        self.help_text_en = help_text_en
        self.fallback_ru = fallback_ru
        self.fallback_en = fallback_en
        self.commands = commands
        self.bot_commands_menu = bot_commands_menu
        self.extra_bot_commands = extra_bot_commands or []
        self.extra_handlers = extra_handlers or []

        # Конфигурируем retrieval если заданы пути
        if study_paths:
            retrieval.configure(study_paths)

        # Индекс команд по callback_id
        self._cb_index: dict[str, ContentCommand] = {c.callback_id: c for c in commands}

    def _reply_keyboard(self, lang: str) -> InlineKeyboardMarkup:
        """Сгенерировать inline-клавиатуру из списка команд (2 кнопки в ряд)."""
        btns = []
        for cmd in self.commands:
            label = cmd.label_ru if lang == "ru" else cmd.label_en
            btns.append(InlineKeyboardButton(label, callback_data=cmd.callback_id))
        # Раскладка: пары по 2 в строке
        rows = [btns[i : i + 2] for i in range(0, len(btns), 2)]
        return InlineKeyboardMarkup(rows)

    def _ui_lang(self, update: Update, chat_id: int) -> str:
        mode = memory.get_lang_mode(chat_id)
        if mode in ("ru", "en"):
            return mode
        u = update.effective_user
        if u and u.language_code and u.language_code.startswith("ru"):
            return "ru"
        if u and u.language_code:
            return "en"
        return "ru"

    # ---------- команды ----------

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        lang = self._ui_lang(update, chat_id)
        text = self.start_text_ru if lang == "ru" else self.start_text_en
        await update.message.reply_text(text)

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        lang = self._ui_lang(update, chat_id)
        text = self.help_text_ru if lang == "ru" else self.help_text_en
        await update.message.reply_text(text)

    async def cmd_reset(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        memory.reset(chat_id)
        # Сбросить все seen-namespaces для этого чата
        for cmd in self.commands:
            if cmd.seen_ns is not None:
                memory.clear_seen(chat_id, cmd.seen_ns)
        lang = self._ui_lang(update, chat_id)
        await update.message.reply_text(
            "Чистый лист. О чём поговорим? 🍵" if lang == "ru"
            else "A clean slate. What shall we talk about? 🍵"
        )

    async def cmd_lang(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        arg = (ctx.args[0].lower() if ctx.args else "")
        if arg in ("ru", "en", "auto"):
            memory.set_lang_mode(chat_id, arg)
            names = {"ru": "русский", "en": "English", "auto": "авто/auto"}
            await update.message.reply_text(f"Язык: {names[arg]}.")
        else:
            await update.message.reply_text(
                "Использование: /lang ru | en | auto\nUsage: /lang ru | en | auto"
            )

    async def _handle_content_cmd(
        self, cmd: ContentCommand, chat_id: int, lang: str, reply_fn
    ) -> None:
        try:
            items = data_store.load(cmd.dataset)
        except FileNotFoundError:
            log.warning("dataset %r missing for /%s", cmd.dataset, cmd.command)
            items = []
        if not items:
            msg = (
                "Пока нечего показать — загляните позже. 🍵"
                if lang == "ru"
                else "Nothing to show yet — check back later. 🍵"
            )
            await reply_fn(msg, parse_mode=None, reply_markup=self._reply_keyboard(lang))
            return
        item = _pick_item(items, chat_id, cmd)
        text = _format_item(item, lang, cmd)
        parse_mode = "HTML" if _needs_html(text) else None
        keyboard = self._reply_keyboard(lang)
        await reply_fn(text, parse_mode=parse_mode, reply_markup=keyboard)

    # ---------- inline callbacks ----------

    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        lang = self._ui_lang(update, chat_id)
        cmd = self._cb_index.get(query.data)
        if cmd is not None:
            await self._handle_content_cmd(
                cmd, chat_id, lang,
                lambda t, parse_mode=None, reply_markup=None:
                    query.message.reply_text(t, parse_mode=parse_mode, reply_markup=reply_markup)
            )

    # ---------- обычный диалог ----------

    async def on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        user_text = update.message.text or ""

        mode = memory.get_lang_mode(chat_id)
        user_lang = persona.detect_lang(user_text)
        prompt_lang = user_lang if mode == "auto" else mode

        rule = persona.language_rule(mode, user_lang)

        # RAG-контекст если retrieval настроен
        extra_ctx = None
        if retrieval.is_configured():
            facts = retrieval.retrieve(user_text, top_k=6)
            if facts:
                extra_ctx = retrieval.format_context(facts)

        system = persona.build_system_prompt(
            prompt_lang, reply_lang_rule=rule, extra_context=extra_ctx
        )

        memory.add(chat_id, "user", user_text)
        msgs = memory.history(chat_id, HISTORY_LIMIT)

        await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            reply = await llm.generate(system, msgs)
        except Exception:
            log.exception("LLM error")
            reply = (
                self.fallback_ru if prompt_lang == "ru" else self.fallback_en
            )
            await update.message.reply_text(reply, reply_markup=self._reply_keyboard(prompt_lang))
            return

        if not reply:
            reply = "…"
        reply = _clean_md(reply)
        memory.add(chat_id, "assistant", reply)
        memory.set_last_lang(chat_id, prompt_lang)
        await update.message.reply_text(reply, reply_markup=self._reply_keyboard(prompt_lang))

    async def on_error(self, update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Глобальный обработчик ошибок."""
        log.exception("Unhandled error while processing update", exc_info=ctx.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                lang = "ru"
                try:
                    chat_id = update.effective_chat.id
                    lang = self._ui_lang(update, chat_id)
                except Exception:
                    pass
                msg = (
                    "Хм, что-то пошло не так. Повторите, пожалуйста. 🍵"
                    if lang == "ru"
                    else "Hmm, something went wrong. Please try again. 🍵"
                )
                await update.effective_message.reply_text(msg)
            except Exception:
                log.exception("Failed to send error notice to user")

    async def post_init(self, app: Application) -> None:
        log.info("LLM backend: %s", llm.active_backend())
        await _check_cliproxy_token()
        if self.bot_commands_menu:
            menu: list[BotCommand] = [
                BotCommand("start", "Начать / Start"),
                BotCommand("help", "Помощь / Help"),
            ]
            for cmd in self.commands:
                label = cmd.label_ru.rstrip(" ✨🎲🎩🔍⚡🔑🧭").strip()
                menu.append(BotCommand(cmd.command, label))
            for name, desc in self.extra_bot_commands:
                menu.append(BotCommand(name, desc))
            menu += [
                BotCommand("lang", "Язык ответов / Reply language"),
                BotCommand("reset", "Забыть разговор / Forget conversation"),
            ]
            await app.bot.set_my_commands(menu)

    def build_app(self) -> Application:
        """Построить PTB Application (полезно для тестов или кастомного запуска)."""
        token = os.environ.get("BOT_TOKEN")
        if not token:
            raise SystemExit(
                "BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен."
            )
        app = ApplicationBuilder().token(token).post_init(self.post_init).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("reset", self.cmd_reset))
        app.add_handler(CommandHandler("lang", self.cmd_lang))

        for cmd in self.commands:
            handler = self._make_content_handler(cmd)
            app.add_handler(CommandHandler(cmd.command, handler))

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))
        for h in self.extra_handlers:
            app.add_handler(h)
        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_error_handler(self.on_error)
        return app

    def _make_content_handler(self, cmd: ContentCommand):
        """Замыкание для команды контента."""
        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            chat_id = update.effective_chat.id
            lang = self._ui_lang(update, chat_id)
            await self._handle_content_cmd(
                cmd, chat_id, lang,
                lambda t, parse_mode=None, reply_markup=None:
                    update.message.reply_text(t, parse_mode=parse_mode, reply_markup=reply_markup)
            )
        return handler


async def _check_cliproxy_token() -> None:
    import aiohttp
    url = os.environ.get("CLIPROXY_BASE_URL", "") + "/v1/models"
    key = os.environ.get("CLIPROXY_API_KEY", "")
    if not key or not url.startswith("http"):
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status in (401, 403):
                    log.warning("cliproxy: token invalid (HTTP %s) — will fallback", resp.status)
                else:
                    log.info("cliproxy: token OK (HTTP %s)", resp.status)
    except Exception as e:
        log.warning("cliproxy: watchdog check failed (%s)", e)


def run(
    bot_name: str,
    start_text_ru: str,
    start_text_en: str,
    help_text_ru: str,
    help_text_en: str,
    commands: list[ContentCommand],
    *,
    fallback_ru: str = "Хм, на мгновение потерял мысль. Попробуйте ещё раз. 🍵",
    fallback_en: str = "Hm, lost my train of thought for a moment. Try again. 🍵",
    study_paths: list[str] | None = None,
    bot_commands_menu: bool = True,
    extra_bot_commands: list[tuple[str, str]] | None = None,
    extra_handlers: list[BaseHandler] | None = None,
) -> None:
    """Запустить бота. Загружает .env, строит приложение, запускает polling.

    Args:
        bot_name:           название для логов.
        start_text_ru/en:  текст команды /start.
        help_text_ru/en:   текст команды /help.
        commands:           список ContentCommand (контент-команды).
        fallback_ru/en:     текст при ошибке LLM.
        study_paths:        пути к study-курсам для RAG (опционально).
        bot_commands_menu:  ставить ли меню команд через set_my_commands.
        extra_bot_commands: дополнительные пары (command, description) для меню.
        extra_handlers:     PTB-хендлеры, регистрируются до catch-all CallbackQueryHandler.
    """
    load_dotenv()
    llm.reload_env()
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    scaffold_obj = BotScaffold(
        bot_name=bot_name,
        start_text_ru=start_text_ru,
        start_text_en=start_text_en,
        help_text_ru=help_text_ru,
        help_text_en=help_text_en,
        fallback_ru=fallback_ru,
        fallback_en=fallback_en,
        commands=commands,
        study_paths=study_paths,
        bot_commands_menu=bot_commands_menu,
        extra_bot_commands=extra_bot_commands,
        extra_handlers=extra_handlers,
    )
    app = scaffold_obj.build_app()
    log.info("%s bot is running…", bot_name)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
