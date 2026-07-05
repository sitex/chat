"""chatcore — переиспользуемое ядро для Telegram чат-персона-ботов.

Типичное использование в боте:
    from chatcore import config, scaffold
    from chatcore.scaffold import ContentCommand

    config.setup(
        data_dir="data",
        db_path="mybot.db",
        assistant_label="Моя Персона",
        user_label="Пользователь",
    )
    scaffold.run(
        bot_name="MyBot",
        start_text_ru="Привет!",
        start_text_en="Hello!",
        help_text_ru="Помощь",
        help_text_en="Help",
        commands=[
            ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨"),
        ],
    )

Подробнее: docs/CREATING-A-BOT.md
"""
from . import admin, config, data_store, llm, memory, persona, ratelimit, retrieval, scaffold

__all__ = ["admin", "config", "data_store", "llm", "memory", "persona", "ratelimit", "retrieval", "scaffold"]
