# Опциональные модули (план реализации)

Компоненты из существующих ботов, не вошедшие в минимальное ядро `chatcore`.
Документированы здесь для реализации по мере необходимости.

---

## TTS-адаптер (из chat-mannix)

**Что это:** синтез речи через внешний сервис OmniVoice, кэш `.ogg`, доставка
голосовых сообщений в Telegram.

**Где реализовано:** `chat-mannix/bot.py` — функции `synthesize()`, `_tts_token()`,
`_norm_numbers()`, `extract_phrases()`.

**Особенности:**
- OmniVoice запускается как `tts_service_omni` на порту 8902
- Токен доступа: `_tts_token()` читает из `/proc/{pid}/environ` (хак)
- Режим `--pauses 4` для «фраз сострадания» (пользователь повторяет вслух)
- Кэш по `md5(text+mode)[:16]` → `static/audio/{key}.ogg`

**Интеграция в chatcore (ToDo):**
```python
# chatcore/tts.py
class TTSAdapter:
    def configure(self, service_url: str, script_path: str) -> None: ...
    async def synthesize(self, text: str, with_pauses: bool = False) -> str | None: ...
    def is_configured(self) -> bool: ...
```

---

## Web-фронтенд (из chat-mannix)

**Что это:** FastAPI-сервер + SPA на vanilla JS, дублирующий чат-интерфейс
параллельно с Telegram-ботом.

**Где реализовано:** `chat-mannix/server.py` (199 строк) + `chat-mannix/static/index.html`.

**Особенности:**
- Асинхронная модель аудио: POST /chat → {text, audio_key}, клиент поллит `/audio_status/{key}`
- История диалога хранится на клиенте (stateless сервер)
- Тёмная «медитативная» тема (Georgia serif, свеча)
- **Проблема:** ядро LLM (`claude_chat`, `SYSTEM_PROMPT`) дублировано copy-paste между bot.py и server.py

**Интеграция в chatcore (ToDo):**
```python
# chatcore/web.py — FastAPI-адаптер
def create_app(scaffold: BotScaffold) -> FastAPI: ...
```

---

## Геймификация (из study-davidkey/game)

**Что это:** XP, уровни, streak, 13 бейджей, лидерборд — для учебных/quiz-ботов.

**Где реализовано:**
- `study-davidkey/game/db.py` — таблицы users/answers/lessons_viewed/achievements
- `study-davidkey/game/content/achievements.py` — `derive_badges(stats)` (чистая функция)
- `study-davidkey/game/bot.py` — callback-driven quiz engine

**Особенности:**
- XP: +10 правильный, +5×streak (макс ×3) бонус
- Уровни: 6 порогов (0/100/300/700/1500/3000 XP)
- 13 бейджей по stats: first_answer, round10, accuracy80/95, streak3/10, module_nlp, и др.
- Anti-repeat: приоритет невиданным вопросам по recent 60 ответов

**Интеграция в chatcore (ToDo):**
```python
# chatcore/gamification.py
class GameSession:
    def answer_question(self, chat_id: int, correct: bool) -> GameResult: ...
    def get_profile(self, chat_id: int) -> Profile: ...
    def get_leaderboard(self) -> list[Profile]: ...

@dataclass
class GameResult:
    xp_gained: int
    new_badges: list[str]
    level_up: bool
```

**Кандидаты на геймификацию:**
- `study-socialself` — уже есть `bot.py` + 8 `game-*.json`
- `chat-davidkey` — quiz по NLP/гипнотерапии на основе глоссариев
- Любой `study-smartyme-*` — предметные quiz

---

## setup_bot_profile (общий скрипт)

**Что это:** установка описания, short description и аватарки бота через Bot API.

**Проблема:** `setMyPhoto` в Bot API возвращает 404 (не поддерживается).
**Обходной путь:** BotFather + Telethon (user-account MTProto), сессия
`~/projects/chats/session.session`, реализовано в `chat-mentalist/set_bot_photo.py`.

**Шаблон** в `chatcore/templates/` — см. `chat-mentalist/setup_bot_profile.py`.

---

## Статус ботов и миграция

Актуальный статус — в [README.md](../README.md#статус-миграции-на-chatcore).

| Бот | Статус | Следующий шаг |
|-----|--------|---------------|
| `chat-mentalist` | ✅ мигрирован как эталон | — |
| `chat-davidkey` | ✅ создан на chatcore | — |
| `chat-jacobs` | ✅ мигрирован (JacobsScaffold, rolling-summary) | — |
| `chat-vishvanath` | ✅ мигрирован (scaffold.run + RAG study_paths) | — |
| `chat-mannix` | ⬜ нетипичный (TTS/web/CLI) | Извлечь ядро в chatcore.tts + chatcore.web |
| `study-socialself` | ⬜ bot.py в study | Вынести в chat-socialself, добавить quiz |
| `study-read-people` | ⬜ полноценный bot/ | Мигрировать на chatcore |
