"""Тесты сборки system prompt и определения языка."""
from chatcore import persona


def test_detect_lang_ru():
    assert persona.detect_lang("привет, как тебя зовут") == "ru"


def test_detect_lang_en():
    assert persona.detect_lang("hello, what is your name") == "en"


def test_detect_lang_empty_defaults_ru():
    assert persona.detect_lang("") == "ru"


def test_language_rule():
    assert "русск" in persona.language_rule("auto", "ru").lower()
    assert "english" in persona.language_rule("auto", "en").lower()
    # явный режим перекрывает язык собеседника
    assert "english" in persona.language_rule("en", "ru").lower()
    assert "русск" in persona.language_rule("ru", "en").lower()


def test_build_system_prompt_ru():
    rule = persona.language_rule("auto", "ru")
    sp = persona.build_system_prompt("ru", reply_lang_rule=rule)
    assert sp
    assert "русск" in sp.lower()


def test_build_system_prompt_en():
    rule = persona.language_rule("auto", "en")
    sp = persona.build_system_prompt("en", reply_lang_rule=rule)
    assert sp
    assert "english" in sp.lower()


def test_build_system_prompt_with_extra_context():
    ctx = "Факт из курса: медитация снижает стресс."
    sp = persona.build_system_prompt("ru", extra_context=ctx)
    assert ctx in sp


def test_build_system_prompt_uses_config_labels():
    """Few-shot примеры используют метки из config."""
    from chatcore import config
    config.setup(assistant_label="Мастер", user_label="Ученик")
    sp = persona.build_system_prompt("ru")
    # Хотя бы один из лейблов должен встречаться
    assert "Мастер" in sp or "Ученик" in sp
