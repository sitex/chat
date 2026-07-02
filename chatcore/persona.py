"""Сборка system prompt из data/persona.json (двуязычно).

Метки ролей в few-shot примерах берутся из chatcore.config
(assistant_label / user_label).
"""
from __future__ import annotations

import random

from . import config, data_store


def detect_lang(text: str) -> str:
    """Грубое определение языка по наличию кириллицы."""
    if not text:
        return "ru"
    cyr = sum("Ѐ" <= ch <= "ӿ" for ch in text)
    lat = sum("a" <= ch.lower() <= "z" for ch in text)
    return "ru" if cyr >= lat else "en"


def _section(block: dict, lang: str) -> str:
    """Вернуть текст секции на нужном языке (с фолбэком)."""
    val = block.get(lang) or block.get("ru") or block.get("en")
    if isinstance(val, list):
        return "\n".join(f"- {item}" for item in val)
    return str(val)


def build_system_prompt(
    lang: str,
    reply_lang_rule: str | None = None,
    extra_context: str | None = None,
    conversation_summary: str | None = None,
) -> str:
    """Собрать system prompt из persona.json.

    Args:
        lang: язык промпта ('ru'|'en').
        reply_lang_rule: инструкция о языке ответа (из language_rule()).
        extra_context: дополнительный контекст (напр. RAG-факты из курса).
        conversation_summary: rolling-резюме предыдущих реплик диалога.
    """
    p = data_store.load("persona")
    parts: list[str] = []

    parts.append(_section(p["identity"], lang))
    parts.append("")

    bio_h = "Биография:" if lang == "ru" else "Backstory:"
    parts.append(bio_h)
    parts.append(_section(p["bio"], lang))
    parts.append("")

    tr_h = "Характер:" if lang == "ru" else "Personality:"
    parts.append(tr_h)
    parts.append(_section(p["traits"], lang))
    parts.append("")

    st_h = "Стиль речи:" if lang == "ru" else "Speech style:"
    parts.append(st_h)
    parts.append(_section(p["speech_style"], lang))
    parts.append("")

    parts.append(_section(p["teacher_mode"], lang))
    parts.append(_section(p["boundaries"], lang))
    parts.append("")

    # Rolling-резюме предыдущих реплик (если накопилась история)
    if conversation_summary and conversation_summary.strip():
        sum_h = "Резюме предыдущего разговора (не упоминай это явно):" \
            if lang == "ru" \
            else "Summary of previous conversation (don't mention this explicitly):"
        parts.append(sum_h)
        parts.append(conversation_summary.strip())
        parts.append("")

    # Опциональный контекст (RAG из курса, как у vishvanath)
    if extra_context:
        ctx_h = "Знания из твоих курсов (говори от первого лица как учитель, не цитируй как список):" \
            if lang == "ru" \
            else "Knowledge from your courses (speak in first person as a teacher, not as a list):"
        parts.append(ctx_h)
        parts.append(extra_context)
        parts.append("")

    # несколько живых цитат как ориентир тона
    try:
        quotes = data_store.load("quotes")
        sample = random.sample(quotes, min(4, len(quotes)))
        q_h = "Примеры твоих фраз (для тона, не цитируй дословно постоянно):" if lang == "ru" \
            else "Examples of your lines (for tone, don't quote verbatim constantly):"
        parts.append(q_h)
        for q in sample:
            parts.append(f"- «{q.get(lang) or q.get('en')}»")
        parts.append("")
    except Exception:
        pass

    # Few-shot примеры диалогов из persona.json
    try:
        examples = p.get("examples", [])
        if examples:
            sample = random.sample(examples, min(2, len(examples)))
            ex_h = "Примеры коротких ответов в образе:" if lang == "ru" \
                else "Examples of short in-character replies:"
            parts.append(ex_h)
            assistant_label = config.get_assistant_label()
            user_label = config.get_user_label() if lang == "ru" else "User"
            for ex in sample:
                dialogue = ex.get(lang) or ex.get("ru") or []
                for turn in dialogue:
                    if turn["role"] == "user":
                        parts.append(f"{user_label}: {turn['text']}")
                    else:
                        parts.append(f"{assistant_label}: {turn['text']}")
                parts.append("")
    except Exception:
        pass

    if reply_lang_rule:
        parts.append(reply_lang_rule)

    return "\n".join(parts).strip()


def language_rule(mode: str, user_lang: str) -> str:
    """Инструкция о языке ответа. mode: auto|ru|en."""
    target = user_lang if mode == "auto" else mode
    if target == "ru":
        return "ВАЖНО: отвечай на русском языке."
    return "IMPORTANT: reply in English."
