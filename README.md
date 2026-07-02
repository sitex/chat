# chatcore — общее ядро Telegram чат-персона-ботов

Переиспользуемый Python-пакет для Telegram-ботов с персоной, памятью диалога, LLM-каскадом и RAG.
Устанавливается как зависимость в каждый бот: `pip install -e ../chat`.

## Быстрый старт

```bash
# В новом проекте бота:
pip install -e ../chat
```

```python
from chatcore import config, scaffold
from chatcore.scaffold import ContentCommand

config.setup(data_dir="data", db_path="bot.db", assistant_label="Моя Персона")
scaffold.run(
    bot_name="MyBot",
    start_text_ru="Привет!", start_text_en="Hello!",
    help_text_ru="Помощь", help_text_en="Help",
    commands=[ContentCommand("quote", "quotes", "cb_quote", "Цитату ✨", "Quote ✨")],
)
```

→ Подробнее: [docs/CREATING-A-BOT.md](docs/CREATING-A-BOT.md)

## Архитектура ядра

```
chatcore/
├── config.py       # setup() — пути data/db, метки ролей
├── llm.py          # LLM-каскад: cliproxy → grok → claude → ollama
├── memory.py       # SQLite: история + настройки + namespaced seen-state
├── data_store.py   # Hot-reload JSON-загрузчик (data/*.json)
├── persona.py      # Сборка system prompt из persona.json
├── retrieval.py    # Опциональный keyword-RAG (для ботов с курсами)
├── scaffold.py     # Каркас бота: хендлеры, ContentCommand, run()
└── templates/      # Шаблоны деплоя (.service, ci.yml, deploy.yml, .env.example)
```

## Семейство ботов

| Бот | Репозиторий / Путь | Telegram | Особенности |
|-----|-------------------|----------|-------------|
| **Патрик Джейн** | [chat-mentalist](../chat-mentalist) | [@mentalist_jane_bot](https://t.me/mentalist_jane_bot) | Загадки со seen-state, уроки, типы личности |
| **Эдвард Манникс** | [chat-mannix](../chat-mannix) | [@mannix_clearing_bot](https://t.me/mannix_clearing_bot) | TTS (OmniVoice), web-фронтенд FastAPI |
| **Lee Jacobs** | [chat-jacobs](../chat-jacobs) | [@unwritten_system_bot](https://t.me/unwritten_system_bot) | Концепты, практики, диагностика OS, на chatcore |
| **Шри Вишванатх** | [chat-vishvanath](../chat-vishvanath) | [@sri_vishwanath_bot](https://t.me/sri_vishwanath_bot) | RAG по `study-vishvanath/facts.json`, на chatcore |
| **David Key** | [chat-davidkey](../chat-davidkey) | *(хэндл уточнить 2026-07-03)* | RAG по NLP + гипнотерапии, на chatcore |
| **David Key Quiz** | [study-davidkey/game](../study-davidkey/game) | [@davidkey_quiz_bot](https://t.me/davidkey_quiz_bot) | Quiz/геймификация (XP/уровни/бейджи), без LLM |
| **Мария** | [chat-socialself](../chat-socialself) | [@maria_socialself_bot](https://t.me/maria_socialself_bot) | Психолог по соцнавыкам, Fast Friend Protocol, RAG |
| **Ачарья Дас** | [chat-acharya-das](../chat-acharya-das) | [@acharya_das_gita_bot](https://t.me/acharya_das_gita_bot) | Ведический учитель, Бхагавад-Гита, RAG по 754 фактам |
| **Marni Kinrys** | [chat-marni](../chat-marni) | [@marni_kinrys_bot](https://t.me/marni_kinrys_bot) | Wing Girl dating coach, RAG по 238 фактам |
| **Dan Bilzerian** | [chat-sigma](../chat-sigma) | [@dan_sigma_bot](https://t.me/dan_sigma_bot) | Sigma Society, self-improvement, RAG по 264 фактам |
| **Luke Hawkins** | [chat-lukehawkins](../chat-lukehawkins) | [@luke_hawkins_bot](https://t.me/luke_hawkins_bot) | NTT-коуч, career coaching, RAG по 394 фактам |

## Статус миграции на chatcore

- [x] **chat-mentalist** — мигрирован как эталон
- [x] **chat-davidkey** — создан на chatcore с нуля
- [x] **chat-jacobs** — мигрирован (JacobsScaffold, rolling-summary)
- [x] **chat-vishvanath** — мигрирован (scaffold.run + RAG study_paths)
- [ ] **chat-mannix** — follow-up: нетипичный (TTS/web/CLI), отдельная задача
- [ ] **study-socialself** — вынести в chat-socialself (quiz + chatcore)
- [ ] **study-read-people** — мигрировать bot/ на chatcore

## Roadmap новых ботов

Кандидаты из `study-*` с богатым контентом и живой персоной:

**Tier 1 — ✅ созданы (named харизматичный учитель):**
- [x] `chat-socialself` — Мария, психолог по соцнавыкам, Fast Friend Protocol
- [x] `chat-acharya-das` — Ачарья Дас, Бхагавад-Гита (RU, прямой аналог vishvanath)
- [x] `chat-marni` — Marni, dating & relationship coach
- [x] `chat-lukehawkins` — Luke Hawkins, career coaching
- [x] `chat-sigma` — Sigma Society, self-improvement

**Tier 2 — гид по учению:**
- `chat-gita`, `chat-yoga-vasistha`, `chat-vedanta`, `chat-ifs`, `chat-smysl`

**Уже имеют бота → миграция:**
- `study-socialself` — quiz/гейм (8 game-*.json, аналог davidkey)
- `study-read-people` — полноценный `bot/` (Docker, tests)

Сборка любого = `data/persona.json` + тонкий `bot.py` на scaffold + `STUDY_PATH` → 15 минут.
→ [docs/OPTIONAL-MODULES.md](docs/OPTIONAL-MODULES.md) — TTS, web-фронтенд, геймификация

## Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/)

### [Unreleased]

#### Added
- `chatcore` — пакет с переиспользуемым ядром из 5 родственных ботов
  - `config.py` — единая настройка путей и меток ролей
  - `llm.py` — каскад cliproxy→grok→claude→ollama с `LLM_OVERALL_TIMEOUT`
  - `memory.py` — SQLite с namespaced seen-state и idempotent-миграциями
  - `data_store.py` — hot-reload JSON
  - `persona.py` — сборка system prompt из persona.json (+ опц. extra_context)
  - `retrieval.py` — keyword-RAG по одному или нескольким `facts.json`
  - `scaffold.py` — `BotScaffold` + `ContentCommand` + `run()` — декларативный каркас бота
  - `templates/` — шаблоны `.service`, `ci.yml`, `deploy.yml`, `.env.example`
- `docs/CREATING-A-BOT.md` — инструкция создания нового бота за 15 минут
- `docs/OPTIONAL-MODULES.md` — план реализации TTS, web-frontend, геймификации
- `tests/` — 33 теста (llm, memory, persona, scaffold) перенесены из chat-mentalist
- **`chat-davidkey`** — новый бот: чат-персона David Key (NLP + гипнотерапия),
  с RAG по `study-davidkey/{nlp,hypnotherapy}/facts.json`
- **`chat-mentalist` мигрирован** на chatcore: src/llm+memory+persona+data_store
  заменены импортами из chatcore; тесты зелёные

#### Architecture
- Дублирование кода ~90% между 5 ботами сведено к нулю
- Новый бот = `data/persona.json` + тонкий `bot.py` (< 80 строк) + `.env`
- LLM-каскад, seen-state, RAG — один источник правды в chatcore

---

*Проект `chat` — внутренний инструмент, не публичная библиотека.*
