"""Регрессионные тесты retrieval — Phase 1.2 (минимальный набор).

Полное покрытие — Phase 5.
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


def _write_facts(path, facts):
    path.write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")


# ── Phase 1.2: _source проставляется именем курса ─────────────────────────────

def test_source_label_added_when_absent(tmp_path):
    """Факты без _source получают метку имени курса."""
    course = tmp_path / "mycourse"
    course.mkdir()
    _write_facts(course / "facts.json", [{"text": "Fact A"}])

    retrieval.configure(course)
    facts = retrieval._load_facts()

    assert len(facts) == 1
    assert facts[0]["_source"] == "mycourse"


def test_existing_source_preserved(tmp_path):
    """Уже проставленный _source не перезаписывается."""
    course = tmp_path / "course2"
    course.mkdir()
    _write_facts(course / "facts.json", [{"text": "Fact B", "_source": "custom"}])

    retrieval.configure(course)
    facts = retrieval._load_facts()

    assert facts[0]["_source"] == "custom"


def test_source_label_nested_subfolder(tmp_path):
    """Вложенный факт получает метку поддиректории, не родителя."""
    base = tmp_path / "base"
    sub = base / "sub"
    sub.mkdir(parents=True)
    _write_facts(sub / "facts.json", [{"text": "Nested fact"}])

    retrieval.configure(base)
    facts = retrieval._load_facts()

    assert facts[0]["_source"] == "sub"
