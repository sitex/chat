"""Общие фикстуры для тестов chatcore."""
import json

import pytest

# Минимальная persona.json для тестов
_PERSONA = {
    "identity": {"ru": "Ты тестовый ассистент.", "en": "You are a test assistant."},
    "bio": {"ru": "История.", "en": "Backstory."},
    "traits": {"ru": ["спокойный", "внимательный"], "en": ["calm", "attentive"]},
    "speech_style": {"ru": "Говори просто.", "en": "Speak simply."},
    "teacher_mode": {"ru": "Объясняй ясно.", "en": "Explain clearly."},
    "boundaries": {"ru": "Не выходи из образа.", "en": "Stay in character."},
    "examples": [
        {
            "ru": [
                {"role": "user", "text": "Привет"},
                {"role": "assistant", "text": "Приветствую."},
            ],
            "en": [
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Greetings."},
            ],
        }
    ],
}

_QUOTES = [
    {"ru": "Всё просто.", "en": "It's simple."},
    {"ru": "Думай иначе.", "en": "Think differently."},
    {"ru": "Будь собой.", "en": "Be yourself."},
    {"ru": "Движение — жизнь.", "en": "Motion is life."},
    {"ru": "Ищи суть.", "en": "Seek the essence."},
]


@pytest.fixture(autouse=True)
def setup_chatcore_config(tmp_path):
    """Настраивает chatcore.config с временными путями для каждого теста."""
    from chatcore import config, memory

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = tmp_path / "test.db"

    # Записываем тестовые данные
    (data_dir / "persona.json").write_text(
        json.dumps(_PERSONA, ensure_ascii=False), encoding="utf-8"
    )
    (data_dir / "quotes.json").write_text(
        json.dumps(_QUOTES, ensure_ascii=False), encoding="utf-8"
    )

    config.setup(
        data_dir=data_dir,
        db_path=db_path,
        assistant_label="Тест-Ассистент",
        user_label="Пользователь",
    )

    # Сбрасываем кэши между тестами
    from chatcore import data_store, retrieval
    data_store._cache.clear()

    # Сбрасываем retrieval-глобалы (изоляция scaffold-тестов со study_paths)
    retrieval._sources = []
    retrieval._facts_cache = None

    # Сбрасываем соединение с БД
    memory.close()

    yield tmp_path

    # Закрыть соединение после теста
    memory.close()
