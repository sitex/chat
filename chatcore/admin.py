"""Админ-команды scaffold: /admin_status, /admin_stats, /admin_reset.

Доступ — по ADMIN_IDS из окружения (Telegram user_id через запятую).
Не-админам не отвечаем (не палим существование команд).
Команды не добавляются в меню set_my_commands.
"""
from __future__ import annotations

import importlib.metadata
import logging
import os
import time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from . import llm, memory

log = logging.getLogger("chatcore.admin")

_started_at = time.monotonic()  # uptime процесса — от импорта chatcore.admin


def parse_admin_ids(env_val: str) -> set[int]:
    """'123, 456' -> {123, 456}; мусорные элементы логируются и пропускаются."""
    ids: set[int] = set()
    for part in env_val.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            log.warning("ADMIN_IDS: пропускаю нечисловой элемент %r", part)
    return ids


def is_admin(user_id: int) -> bool:
    """Читает ADMIN_IDS из os.environ при каждом вызове (дёшево, тестируемо)."""
    return user_id in parse_admin_ids(os.environ.get("ADMIN_IDS", ""))


def _version() -> str:
    try:
        return importlib.metadata.version("chatcore")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def make_admin_handlers(scaffold_obj) -> list[CommandHandler]:
    """Фабрика хендлеров. scaffold_obj: BotScaffold (нужен bot_name и commands
    для очистки seen-state в /admin_reset). Тип не аннотирован — циклический импорт."""

    async def admin_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or not is_admin(user.id) or update.message is None:
            return
        uptime = int(time.monotonic() - _started_at)
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)
        await update.message.reply_text(
            f"🤖 {scaffold_obj.bot_name}\n"
            f"chatcore: {_version()}\n"
            f"LLM backend: {llm.active_backend()}\n"
            f"Uptime: {h}h {m}m {s}s\n"
            f"Чатов в БД: {memory.count_chats()}"
        )

    async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or not is_admin(user.id) or update.message is None:
            return
        now = time.time()
        lines = [f"📊 Всего чатов: {memory.count_chats()}"]
        for label, since in (("24ч", now - 86400), ("7д", now - 7 * 86400)):
            top = memory.top_chats(since)
            lines.append(f"\nТоп за {label}:")
            if top:
                lines += [f"  {cid}: {cnt}" for cid, cnt in top]
            else:
                lines.append("  (пусто)")
        await update.message.reply_text("\n".join(lines))

    async def admin_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or not is_admin(user.id) or update.message is None:
            return
        if not ctx.args or not _is_int(ctx.args[0]):
            await update.message.reply_text("Использование: /admin_reset <chat_id>")
            return
        target = int(ctx.args[0])
        memory.reset(target)
        for cmd in scaffold_obj.commands:
            if cmd.seen_ns is not None:
                memory.clear_seen(target, cmd.seen_ns)
        await update.message.reply_text(f"Чат {target} сброшен.")

    return [
        CommandHandler("admin_status", admin_status),
        CommandHandler("admin_stats", admin_stats),
        CommandHandler("admin_reset", admin_reset),
    ]


def _is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        return False
