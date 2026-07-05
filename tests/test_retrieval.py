"""Полное покрытие retrieval (Phase 5).

Организовано по группам:
  - is_configured
  - _load_facts (форматы, файлы, источники)
  - retrieve (ранжирование, top_k, фильтрация коротких слов, фолбэки полей)
  - format_context (метки источников, приоритет полей)
  - end-to-end

Регрессии Phase 1.2 сохранены.
"""
import json

import pytest

from chatcore import retrieval


@pytest.fixture(autouse=True)
def reset_retrieval():
    """Сбрасывает глобальное состояние retrieval между тестами."""
    retrieval._sources = []
    retrieval._facts_cache = None
    yield
    retrieval._sources = []
    retrieval._facts_cache = None


def _make_course(tmp_path, name: str, facts, nested: dict | None = None):
    """Создаёт структуру курса в tmp_path.

    Args:
        tmp_path: базовый каталог
        name: имя курса (директория)
        facts: список фактов или словарь {"facts": [...]} для корневого facts.json;
               None — файл не создаётся
        nested: {sub_name: facts_data} для вложенных подкурсов

    Returns:
        Path курса
    """
    course = tmp_path / name
    course.mkdir(parents=True, exist_ok=True)
    if facts is not None:
        (course / "facts.json").write_text(
            json.dumps(facts, ensure_ascii=False), encoding="utf-8"
        )
    if nested:
        for sub_name, sub_facts in nested.items():
            sub = course / sub_name
            sub.mkdir(parents=True, exist_ok=True)
            (sub / "facts.json").write_text(
                json.dumps(sub_facts, ensure_ascii=False), encoding="utf-8"
            )
    return course


# ── is_configured ──────────────────────────────────────────────────────────────

def test_is_configured_default_false():
    assert retrieval.is_configured() is False


def test_is_configured_after_configure_str(tmp_path):
    course = _make_course(tmp_path, "c", [])
    retrieval.configure(str(course))
    assert retrieval.is_configured() is True


def test_is_configured_after_configure_path(tmp_path):
    course = _make_course(tmp_path, "c", [])
    retrieval.configure(course)
    assert retrieval.is_configured() is True


def test_is_configured_after_configure_list(tmp_path):
    course = _make_course(tmp_path, "c", [])
    retrieval.configure([course])
    assert retrieval.is_configured() is True


def test_reconfigure_resets_cache(tmp_path):
    """Повторный configure сбрасывает кэш фактов."""
    course1 = _make_course(tmp_path, "c1", [{"text": "fact from c1"}])
    course2 = _make_course(tmp_path, "c2", [{"text": "fact from c2"}])

    retrieval.configure(course1)
    facts_first = retrieval._load_facts()
    assert any("c1" in str(f) or "fact from c1" in f.get("text", "") for f in facts_first)

    retrieval.configure(course2)
    facts_second = retrieval._load_facts()
    assert len(facts_second) == 1
    assert facts_second[0]["text"] == "fact from c2"


# ── _load_facts ────────────────────────────────────────────────────────────────

def test_load_facts_root_json(tmp_path):
    """Корневой facts.json загружается."""
    course = _make_course(tmp_path, "mycourse", [{"text": "Root fact"}])
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert len(facts) == 1
    assert facts[0]["text"] == "Root fact"


def test_load_facts_wrapped_format(tmp_path):
    """Формат {"facts": [...]} разворачивается правильно."""
    course = _make_course(tmp_path, "wrapped", {"facts": [{"text": "Wrapped fact"}]})
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert len(facts) == 1
    assert facts[0]["text"] == "Wrapped fact"


def test_load_facts_missing_file_skipped(tmp_path):
    """Отсутствующий facts.json не вызывает ошибку — курс просто пустой."""
    course = _make_course(tmp_path, "empty_course", None)
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert facts == []


def test_load_facts_broken_json_skipped(tmp_path):
    """Битый JSON молча пропускается."""
    course = tmp_path / "broken"
    course.mkdir()
    (course / "facts.json").write_text("not valid json{{", encoding="utf-8")
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert facts == []


def test_load_facts_nested_subfolder_label(tmp_path):
    """Вложенный facts.json получает метку имени поддиректории."""
    course = _make_course(tmp_path, "base", None, nested={"nlp": [{"text": "NLP fact"}]})
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert len(facts) == 1
    assert facts[0]["_source"] == "nlp"


def test_load_facts_root_and_nested(tmp_path):
    """Корневой и вложенные facts.json объединяются."""
    course = _make_course(
        tmp_path, "combined",
        [{"text": "Root fact"}],
        nested={"sub": [{"text": "Sub fact"}]},
    )
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert len(facts) == 2
    texts = {f["text"] for f in facts}
    assert texts == {"Root fact", "Sub fact"}


def test_load_facts_cached(tmp_path):
    """Второй вызов _load_facts возвращает тот же объект (кэш)."""
    course = _make_course(tmp_path, "c", [{"text": "X"}])
    retrieval.configure(course)
    first = retrieval._load_facts()
    second = retrieval._load_facts()
    assert first is second


# ── Phase 1.2: _source ────────────────────────────────────────────────────────

def test_source_label_added_when_absent(tmp_path):
    """Факты без _source получают метку имени курса."""
    course = _make_course(tmp_path, "mycourse", [{"text": "Fact A"}])
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert len(facts) == 1
    assert facts[0]["_source"] == "mycourse"


def test_existing_source_preserved(tmp_path):
    """Уже проставленный _source не перезаписывается."""
    course = _make_course(tmp_path, "course2", [{"text": "Fact B", "_source": "custom"}])
    retrieval.configure(course)
    facts = retrieval._load_facts()
    assert facts[0]["_source"] == "custom"


def test_source_label_nested_subfolder(tmp_path):
    """Вложенный факт получает метку поддиректории, не родителя."""
    base = tmp_path / "base"
    sub = base / "sub"
    sub.mkdir(parents=True)
    (sub / "facts.json").write_text(
        json.dumps([{"text": "Nested fact"}], ensure_ascii=False), encoding="utf-8"
    )
    retrieval.configure(base)
    facts = retrieval._load_facts()
    assert facts[0]["_source"] == "sub"


# ── retrieve ───────────────────────────────────────────────────────────────────

def test_retrieve_empty_without_config():
    """Без configure возвращает пустой список."""
    assert retrieval.retrieve("meditation") == []


def test_retrieve_ranking_by_keyword_matches(tmp_path):
    """Факты с большим числом совпадений ключевых слов идут первыми."""
    course = _make_course(tmp_path, "c", [
        {"text": "meditation helps with stress and anxiety"},
        {"text": "meditation is a mindfulness practice"},
        {"text": "running is healthy"},
    ])
    retrieval.configure(course)
    results = retrieval.retrieve("meditation mindfulness", top_k=3)
    assert results[0]["text"] == "meditation is a mindfulness practice"


def test_retrieve_exact_phrase_bonus(tmp_path):
    """Точная фраза в тексте даёт бонус и поднимает факт выше."""
    course = _make_course(tmp_path, "c", [
        {"text": "mindfulness meditation is great"},
        {"text": "deep meditation practice"},
    ])
    retrieval.configure(course)
    results = retrieval.retrieve("deep meditation practice", top_k=2)
    assert results[0]["text"] == "deep meditation practice"


def test_retrieve_top_k(tmp_path):
    """top_k ограничивает количество результатов."""
    course = _make_course(tmp_path, "c", [
        {"text": "apple is a fruit"},
        {"text": "apple juice is tasty"},
        {"text": "apple trees grow tall"},
        {"text": "apple cider is fermented"},
    ])
    retrieval.configure(course)
    results = retrieval.retrieve("apple", top_k=2)
    assert len(results) == 2


def test_retrieve_short_words_ignored(tmp_path):
    """Слова длиной ≤2 символа не участвуют в ранжировании."""
    course = _make_course(tmp_path, "c", [
        {"text": "do is it or no go"},
    ])
    retrieval.configure(course)
    # Запрос из одних коротких слов — ни одно из них не влияет на score
    results = retrieval.retrieve("do it or go")
    assert results == []


def test_retrieve_text_fallback_value(tmp_path):
    """При отсутствии поля text используется value."""
    course = _make_course(tmp_path, "c", [{"value": "value field content"}])
    retrieval.configure(course)
    results = retrieval.retrieve("value field content", top_k=1)
    assert len(results) == 1
    assert results[0]["value"] == "value field content"


def test_retrieve_text_fallback_content(tmp_path):
    """При отсутствии text/value используется content."""
    course = _make_course(tmp_path, "c", [{"content": "content field fact"}])
    retrieval.configure(course)
    results = retrieval.retrieve("content field fact", top_k=1)
    assert len(results) == 1
    assert results[0]["content"] == "content field fact"


def test_retrieve_no_match_excluded(tmp_path):
    """Факты без совпадений не включаются в результат."""
    course = _make_course(tmp_path, "c", [
        {"text": "completely unrelated topic"},
        {"text": "another unrelated sentence"},
    ])
    retrieval.configure(course)
    results = retrieval.retrieve("meditation mindfulness yoga")
    assert results == []


def test_retrieve_empty_dataset(tmp_path):
    """Пустой датасет → пустой результат."""
    course = _make_course(tmp_path, "c", [])
    retrieval.configure(course)
    assert retrieval.retrieve("anything") == []


# ── format_context ─────────────────────────────────────────────────────────────

def test_format_context_with_source():
    """Формат [label] text при наличии источника."""
    facts = [{"text": "Some fact", "_source": "lesson1"}]
    result = retrieval.format_context(facts)
    assert result == "[lesson1] Some fact"


def test_format_context_priority_source_value():
    """source_value имеет приоритет над lesson и _source."""
    facts = [{"text": "fact", "source_value": "sv", "lesson": "les", "_source": "src"}]
    result = retrieval.format_context(facts)
    assert result == "[sv] fact"


def test_format_context_priority_lesson_over_source():
    """lesson имеет приоритет над _source."""
    facts = [{"text": "fact", "lesson": "lesson_name", "_source": "source_name"}]
    result = retrieval.format_context(facts)
    assert result == "[lesson_name] fact"


def test_format_context_no_source():
    """Без источника — только текст, без скобок."""
    facts = [{"text": "Just a fact"}]
    result = retrieval.format_context(facts)
    assert result == "Just a fact"


def test_format_context_empty_input():
    """Пустой список → пустая строка."""
    assert retrieval.format_context([]) == ""


def test_format_context_multiple_facts():
    """Несколько фактов разделяются переводом строки."""
    facts = [
        {"text": "First fact", "_source": "s1"},
        {"text": "Second fact", "_source": "s2"},
    ]
    result = retrieval.format_context(facts)
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[0] == "[s1] First fact"
    assert lines[1] == "[s2] Second fact"


def test_format_context_text_fallback_fields():
    """value и content тоже выводятся как текст."""
    facts = [{"value": "val fact", "_source": "s1"}]
    result = retrieval.format_context(facts)
    assert result == "[s1] val fact"


# ── end-to-end ─────────────────────────────────────────────────────────────────

def test_end_to_end_configure_retrieve_format_context(tmp_path):
    """Полный цикл: configure → retrieve → format_context содержит [course_name]."""
    course = _make_course(tmp_path, "philosophy", [
        {"text": "Socrates believed in the examined life"},
        {"text": "Plato described the allegory of the cave"},
        {"text": "Aristotle studied the golden mean"},
    ])
    retrieval.configure(course)

    results = retrieval.retrieve("Socrates examined life", top_k=3)
    assert len(results) >= 1

    context = retrieval.format_context(results)
    assert "[philosophy]" in context
    assert "Socrates" in context
