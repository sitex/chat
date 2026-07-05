# Как создать нового бота на chatcore

Новый чат-персона-бот занимает ~15 минут и состоит из трёх частей:
**тонкий `bot.py`** + **папка `data/`** + **конфиг (`.env`, `.service`)**.

## 1. Инициализация

```bash
mkdir ~/projects/chat-mybot
cd ~/projects/chat-mybot
python3 -m venv .venv
.venv/bin/pip install -e ../chat       # chatcore из локального репо
cp ../chat/chatcore/templates/.env.example .env
```

## 2. bot.py (точка входа)

```python
"""Telegram-бот «Моя Персона». Запуск: python bot.py"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # опционально: run() сам перечитывает env через llm.reload_env()

from chatcore import config, scaffold
from chatcore.scaffold import ContentCommand

config.setup(
    data_dir=Path(__file__).parent / "data",
    db_path=Path(__file__).parent / "mybot.db",
    assistant_label="Моя Персона",    # имя в few-shot + grok flatten
    user_label="Пользователь",
)

COMMANDS = [
    ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨"),
    # Добавьте команды — каждая соответствует файлу data/<dataset>.json
    # seen_ns="riddles" — для команд без повторов (пока не показаны все)
]

def main() -> None:
    scaffold.run(
        bot_name="MyBot",
        start_text_ru="Привет! Я Моя Персона...",
        start_text_en="Hello! I'm My Persona...",
        help_text_ru="Что я умею:\n• /quote — цитата\n• /lang ru|en|auto\n• /reset",
        help_text_en="What I can do:\n• /quote — a quote\n• /lang ru|en|auto\n• /reset",
        commands=COMMANDS,
        fallback_ru="Что-то пошло не так. Повторите. 🍵",
        fallback_en="Something went wrong. Try again. 🍵",
        # Опционально: RAG по study-курсу
        # study_paths=[os.environ.get("STUDY_PATH", "/path/to/study-course")],
    )

if __name__ == "__main__":
    main()
```

## 3. data/persona.json

Схема идентична у всех ботов:

```json
{
  "_comment": "Описание персоны",
  "name": "Моя Персона",
  "identity": {
    "ru": "Ты [Имя]...",
    "en": "You are [Name]..."
  },
  "bio":          { "ru": "...", "en": "..." },
  "traits":       { "ru": ["черта 1", "черта 2"], "en": ["trait 1", "trait 2"] },
  "speech_style": { "ru": "...", "en": "..." },
  "teacher_mode": { "ru": "...", "en": "..." },
  "boundaries":   { "ru": "...", "en": "..." },
  "examples": [
    {
      "ru": [{"role":"user","text":"..."},{"role":"assistant","text":"..."}],
      "en": [{"role":"user","text":"..."},{"role":"assistant","text":"..."}]
    }
  ]
}
```

## 4. data/quotes.json и другие датасеты

```json
[
  {"ru": "Цитата на русском.", "en": "Quote in English."}
]
```

Для объектов с заголовком/телом (`/concept`, `/practice`, `/teaching`):
```json
[
  {
    "title_ru": "Название", "title_en": "Title",
    "body_ru": "Текст", "body_en": "Text"
  }
]
```

Для загадок (с `<tg-spoiler>`):
```json
[{"q_ru":"Вопрос","a_ru":"Ответ","q_en":"Question","a_en":"Answer"}]
```

## 5. Опциональный RAG

Если бот должен отвечать на основе учебных материалов курса (как `chat-vishvanath`
или `chat-davidkey`):

```python
config.setup(...)
STUDY_PATH = os.environ.get("STUDY_PATH", "/path/to/study-course")
# ...
scaffold.run(..., study_paths=[STUDY_PATH])
```

`chatcore.retrieval` автоматически найдёт `facts.json` в корне и во всех
подкаталогах одного уровня.

## 6. Деплой

1. Скопируй шаблоны из `chatcore/templates/`:
   - `bot.service.template` → `chat-mybot-bot.service` (заполни `{{ ... }}`)
   - `deploy.yml` → `.github/workflows/deploy.yml`
   - `ci.yml` → `.github/workflows/ci.yml`
2. Настрой systemd: `sudo cp chat-mybot-bot.service /etc/systemd/system/ && sudo systemctl enable chat-mybot-bot`
3. Добавь GitHub Secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`
4. Настрой NOPASSWD sudo для `systemctl restart chat-mybot-bot` в `/etc/sudoers.d/`

## Устранение неполадок

- **Бот молчит на текст**: проверь `LLM_BACKEND` и наличие ключей. Фолбэк — ollama локально.
- **Ошибка импорта chatcore**: `pip install -e ../chat` в venv проекта.
- **Бот отвечает на русском даже при /lang en**: убедись что `user_label` в config.setup не кириллический (влияет на _flatten_messages в grok-режиме).
