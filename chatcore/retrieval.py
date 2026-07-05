"""Keyword-retrieval по facts.json из одного или нескольких study-курсов.

Опциональный модуль — подключается только если задан STUDY_PATH.

Пример:
    from chatcore import retrieval
    retrieval.configure(["/path/to/study-vishvanath"])
    facts = retrieval.retrieve("медитация", top_k=6)
    ctx = retrieval.format_context(facts)
"""
from __future__ import annotations

import json
from pathlib import Path

_sources: list[Path] = []
_facts_cache: list[dict] | None = None


def configure(paths: list[str | Path] | str | Path) -> None:
    """Задать один или несколько study-путей для retrieval.

    Args:
        paths: путь или список путей к корням study-курсов.
               В каждом ожидается файл facts.json.
               Для davidkey можно передать путь к корню с подкурсами
               (nlp/facts.json + hypnotherapy/facts.json).
    """
    global _sources, _facts_cache
    _facts_cache = None  # сбросить кэш при повторной настройке
    if isinstance(paths, (str, Path)):
        paths = [paths]
    _sources = [Path(p) for p in paths]


def _load_facts() -> list[dict]:
    global _facts_cache
    if _facts_cache is not None:
        return _facts_cache
    all_facts: list[dict] = []
    for base in _sources:
        # Ищем facts.json: сначала в корне, потом во вложенных каталогах (один уровень)
        candidates = [base / "facts.json"]
        candidates += list(base.glob("*/facts.json"))
        for path in candidates:
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                facts = raw["facts"] if isinstance(raw, dict) and "facts" in raw else raw
                if isinstance(facts, list):
                    # помечаем источник для format_context
                    source_label = path.parent.name if path.parent != base else base.name
                    for fact in facts:
                        if "_source" not in fact:
                            fact = dict(fact)
                            fact["_source"] = source_label
                        all_facts.append(fact)
            except Exception:
                pass
    _facts_cache = all_facts
    return _facts_cache


def retrieve(query: str, top_k: int = 6) -> list[dict]:
    """Keyword-поиск: возвращает top_k наиболее релевантных фактов."""
    facts = _load_facts()
    if not facts:
        return []

    q_lower = query.lower()
    q_words = [w for w in q_lower.split() if len(w) > 2]

    scored: list[tuple[int, dict]] = []
    for fact in facts:
        text = fact.get("text") or fact.get("value") or fact.get("content") or ""
        if not text:
            continue
        tl = text.lower()
        score = sum(2 for w in q_words if w in tl)
        if q_lower in tl:
            score += 5
        if score > 0:
            scored.append((score, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]


def format_context(facts: list[dict]) -> str:
    lines = []
    for fact in facts:
        text = fact.get("text") or fact.get("value") or fact.get("content") or ""
        source = (
            fact.get("source_value")
            or fact.get("lesson")
            or fact.get("_source")
            or ""
        )
        if text:
            lines.append(f"[{source}] {text.strip()}" if source else text.strip())
    return "\n".join(lines)


def is_configured() -> bool:
    return bool(_sources)
