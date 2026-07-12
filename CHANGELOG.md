# Changelog — chatcore (sitex/chat)

## [0.1.10] — 2026-07-12

### Fixed
- `chatcore/singleinstance.py`: cross-user защита через PID-файл `/tmp/chatbot-{token_hash}.pid` — обнаруживает дубль system/user service до старта polling; выход кодом 0 (не SystemExit(1)) — `Restart=on-failure` не создаёт бесконечный цикл.
- `chatcore/scaffold.py`: 5×409 Conflict → `os._exit(0)` вместо `os._exit(78)` — дублирующий инстанс завершается чисто, systemd не перезапускает его снова.

## [0.1.9] — 2026-07-12

### Fixed
- `scripts/check_single_instance.sh`: фильтрация только venv-путей (`/home/rocky/projects/*/.venv/*`) — устраняет ложные FAIL на node/gitwatch/immich-watcher.
- `tests/test_table_tts.py`: моки `concat_ogg` принимают `**kw` — тесты падали с `TypeError` после добавления `gap_ms` в вызов.

### Changed
- `@maria_socialself_bot` удалён и пересоздан как `@david_socialself_bot` (новый токен в `chat-socialself/.env`, сервис на VPS перезапущен) (#29).
- `tools/update_all_bot_profiles.py`: socialself short/description обновлены под David Morin.
- `scripts/roundtable.py`, `scripts/table_bot.py`: socialself-персонаж переименован Мария → David (Morin, основатель SocialSelf FFP) (#28).
- `chat-socialself/data/persona.json`: имя, пол, identity и bio обновлены под реального автора курса.

### Added (2026-07-11)
- `tools/update_all_bot_profiles.py` — скрипт обновления `setMyDescription`/`setMyShortDescription` всех 11 ботов персон.

### Fixed (Infrastructure, 2026-07-10)
- `scripts/table_tts.py`: убран `stop_periods` из ffmpeg `silenceremove` — резал речь при per-sentence паузах (#24).

### Added (2026-07-10)
- `scripts/table_bot.py`: `TABLE_ROUNDS` — авто-продолжение N раундов подряд без кнопки; дефолт 1 (#25).


## [0.1.8] — 2026-07-10

### Added
- `chatcore/llm.py`: `generate(backend=...)` — опциональный override бэкенда для служебных вызовов (режиссёр стола); дефолт не изменился (#20).
- `chatcore/llm.py`: UA-обход клоакинга CLIProxyAPI для claude-моделей — `User-Agent: claude-cli/...` + префикс-блок «You are Claude Code...» в system; персона — вторым блоком. Grok-путь прод-ботов не затронут (#20).
- `scripts/table_tts.py`: класс `TTSWorker` — фоновый поток-конвейер; доставка голосовых строго по порядку, `deliver=False` для прогрева, тихий фолбэк при `synth → None` (#20).
- `tests/test_roundtable.py`: 8 unit-тестов `pick_next` — передача backend, фолбэк по порядку при ошибке/не-числе, короткие пути без LLM (#20).
- `tests/test_llm.py`: тесты backend-override (`generate`), UA-обхода cliproxy для claude- и не-claude-моделей (#20).
- `tests/test_table_tts.py`: 4 unit-теста `TTSWorker` — порядок, deliver=False, synth→None, close (#20).

### Changed
- `scripts/roundtable.py`: `DIRECTOR_BACKEND` из окружения — режиссёр `pick_next()` использует отдельный (дешёвый) бэкенд без холодного старта Node (#20).
- `scripts/table_bot.py`: `start_table` пробрасывает `CLIPROXY_*` и `DIRECTOR_BACKEND` из `~/.table-bot.env`; `TABLE_LLM_BACKEND` (дефолт `claude-cli`) и `TABLE_LLM_MAX_TOKENS` (дефолт `250`) конфигурируют бэкенд и лимит реплик (#20).
- `scripts/table_bot.py`: `_table_reader` использует `TTSWorker` — текст реплики уходит в чат немедленно, синтез аудио не блокирует следующий текст; прогрев TTS-модели на старте стола (#20).

### Infrastructure (podcastify, home machine)
- TTS стола переведён на GGUF-бэкенд: `tts_service_higgs.py` получил режим `HIGGS_BACKEND=gguf` — subprocess `higgs_cli` (HiggsTTS.cpp, квант Q4_K, ~3–4 GB VRAM вместо ~13 GB у sglang-omni, синтез реплики ~3.5 с через туннель). Код chat не менялся — тот же туннель VPS:8902 → home:8903 (sitex/podcastify#7, #19).

## [0.1.7] — 2026-07-10

### Added
- `scripts/table_tts.py` — модуль озвучки круглого стола: `VOICE_BY_KEY` (11 персон), `clean_for_tts` (markdown/emoji/№N), `healthz`, `synthesize_ogg` (WAV → OGG через ffmpeg, timeout 180 с, тихий фолбэк) (#19).
- `tests/test_table_tts.py` — 21 unit-тест с моками httpx/ffmpeg: happy path, все ветки → None, синхронизация VOICE_BY_KEY ↔ DEFAULT_PERSONAS (#19).

### Changed
- `scripts/roundtable.py:274`: событие `reply` теперь содержит поле `key` персоны (аддитивно, обратно совместимо) (#19).
- `scripts/table_bot.py`: добавлены `TTS_URL`/`TTS_TOKEN` из `.env`, `api_voice()`, healthz-флаг в `start_table()`, вызов `synthesize_ogg` в `_table_reader()` с тихим фолбэком (#19).

### Infrastructure (podcastify, home machine)
- `tts_service_higgs.py`: добавлены 10 голосов `table-*` (ref WAV из bootstrap) — туннель VPS:8902 → home:8903 (#19).
- `tools/bootstrap_table_voices.py`: скрипт bootstrap ref WAV через OmniVoice design-mode (#19).
- `tts_service_omni.py`: зарегистрированы 10 voice slots + исправлены instruct-строки под валидный OmniVoice API (#19).

## [0.1.6] — 2026-07-09

### Added
- `/table 1,3,5: тема` в table_bot.py — выбор подмножества участников: числа/запятые перед первым двоеточием = номера 1–11 (дедупликация, минимум 2), иначе весь текст = тема; состав передаётся в `roundtable.py --personas` (#17).
- Аватарка и описание `@rocky_roundtable_bot`: `avatars/rocky_roundtable.png` (Grok Imagine, установка через BotFather), description/short_description через Bot API (#18).

### Changed
- `roundtable.py`: номер участника вне диапазона 1–11 отсеивается с сообщением, а не роняет скрипт IndexError (#17).

### Notes
- Зеркальный парсинг добавлен в manager-bot (sitex/telegram-mcp#7) — контракт общий, менять синхронно.

## [0.1.5] — 2026-07-09

### Added
- `scripts/roundtable.py` — движок круглого стола персон: тема + 11 участников из семейства chat-*, режимы `--jsonl` (события JSON-строками для ботов) и `--interactive` (stdin: `MORE`/`STOP`/текст = реплика Ведущего, автозавершение после 600 с тишины) (#15).
- Живой порядок круга: следующего оратора выбирает режиссёр — прямое обращение («№3»/имя) → отвечает адресат, иначе LLM решает, кому есть что сказать; каждый говорит один раз за круг, `--sequential` возвращает фиксированный порядок (#15).
- `NAME_OVERRIDE` в roundtable: участник ifs отображается как «Ричард Шварц» (persona.json ботов не тронут).
- `scripts/table_bot.py` + `scripts/systemd/table-bot.service` — standalone Telegram-бот стола `@rocky_roundtable_bot` для VPS: long-poll, allowlist, кнопки «Ещё круг»/«Завершить», обычный текст = реплика Ведущего (#16).
- Деплой на VPS Contabo: клон репо + venv с chatcore, deploy key для chat-mannix, `CLAUDE_CLI_BIN` в env юнита; связка проверена e2e на claude-cli (#16).

### Notes
- Команда `/table` также врезана в manager-bot (sitex/telegram-mcp#6) — локальный вариант стола на том же движке.

## [0.1.4] — 2026-07-06

### Added
- `chatcore/singleinstance.py` — flock-guard: второй инстанс на той же машине получает CRITICAL-лог и SystemExit(1). Отключается через `SINGLE_INSTANCE_LOCK=0` (#14).
- `scaffold.run()`: при старте берёт эксклюзивный flock на `<db_path>.lock`; GC-безопасный держатель лока.
- `BotScaffold.on_error()`: Conflict-watchdog — ≥5 ошибок `telegram.error.Conflict` подряд в окне 60 с → `os._exit(78)`; короткое перекрытие при деплое (1–2 Conflict) порога не достигает (#14).
- `scripts/check_single_instance.sh` — аудит дублей: проверяет каждый ExecStart в system+user менеджерах, количество процессов и 409 Conflict в journald (#14).
- `scripts/systemd/check-single-instance.{service,timer}` — user-level oneshot-юнит с ежедневным таймером; при FAIL — failed-состояние видно в `systemctl --user --failed` (#14).
- `docs/single-instance.md` — инвариант, таблица канонов менеджеров, инструкция по аудиту и установке таймера (#14).

### Changed
- `chatcore/templates/deploy.yml`: заменён `sudo systemctl restart` на user-level рестарт + guard-шаг (`sudo -n systemctl stop/disable {{ SERVICE_NAME }} 2>/dev/null || true`) перед `systemctl --user restart` (#14). ⚠️ Шаблон-breaking: существующие боты нужно обновить deploy.yml.
- `chatcore/templates/bot.service.template`: добавлен комментарий-инвариант (user-only, не копировать в /etc/systemd/system/) (#14).

### Tests
- `tests/test_singleinstance.py` — acquire/отказ/повторный захват/PermissionError-ветка (4 теста).
- `tests/test_scaffold.py` — watchdog: порог 5, окно 60 с, сброс при паузе, no-reply на Conflict, не-Conflict не растит счётчик (5 тестов).

## [0.1.3] — 2026-07-05

### Added
- `chatcore/ratelimit.py` — sliding-window rate-limit для `on_message` (10 сообщ./60 сек на пользователя, `rate_limit=0` отключает). ⚠️ Новое поведение по умолчанию — существующие боты получают лимит 10/60 автоматически (#10).
- `chatcore/admin.py` — `/admin_status`, `/admin_stats`, `/admin_reset <chat_id>` по `ADMIN_IDS` из env; молчаливый игнор не-админов; не добавляется в меню команд (#10).
- `memory.count_chats()`, `memory.top_chats(since_ts)` — статистика активности для admin-команд.
- Параметры `rate_limit` (int, по умолч. 10) и `rate_period` (float, по умолч. 60.0) в `scaffold.run()` и `BotScaffold.__init__()`.

### Changed (Breaking)
- **`llm.py`**: backend `claude-cli` теперь работает в **строгом режиме** — фолбэк на `cliproxy` и `ollama` убран. При ошибке `claude -p` исключение поднимается наверх; бот показывает fallback-текст вместо ответа со сломанной персоной. Причина: cliproxy инжектирует промпт «You are Claude Code…» поверх персонажа.

### Tests
- Удалены `test_claude_cli_cascades_to_cliproxy`, `test_claude_cli_cascades_to_ollama`, `test_claude_cli_cascades_to_ollama_when_cliproxy_also_fails`.
- Добавлены `test_claude_cli_strict_raises`, `test_claude_cli_strict_never_calls_fallbacks`.
- `test_budget_exhausted_before_fallback` переведён на backend `grok` (бюджетная логика `_attempt` не затрагивает строгий каскад).

## [0.1.2] — 2026-07-05

### Added
- `llm.reload_env()` — перечитывает все env-константы без перезапуска; `scaffold.run()` вызывает автоматически, снимая требование «load_dotenv до import chatcore» (Phase 3).
- `memory.close()` — закрыть и сбросить глобальное соединение; позволяет переключать БД в тестах без перезапуска (Phase 2).
- `scripts/gen_avatar.py` — единый параметризованный скрипт аватаров (username, prefix, prompt как аргументы CLI); заменяет 4 копипаст-скрипта (Phase 4).
- `Makefile` с целями `test`, `lint`, `typecheck`, `fmt`, `check` (Phase 4).
- ruff (≥0.5) и mypy (≥1.10) добавлены в `[project.optional-dependencies] dev` (Phase 4).
- Шаг `Lint: ruff check .` в шаблоне `chatcore/templates/ci.yml` (Phase 4).
- `tests/test_retrieval.py` — 32 теста retrieval (configure, _load_facts, retrieve, format_context, end-to-end) (Phase 5).

### Fixed
- **`scaffold.py`**: httpx (INFO) писал полный URL Bot API с BOT_TOKEN в journald — `logging.getLogger("httpx").setLevel(logging.WARNING)` убирает токен из журналов.
- **`llm.py`**: зомби-процессы — добавлен `_kill_and_reap(proc)` с `await proc.wait()` в except-блоках `_grok`, `_claude_cli`, `_summary_cli` (Phase 1).
- **`llm.py`**: утечка HTTP-клиентов — `AsyncAnthropic` создаётся через `async with` в `_cliproxy` и `_claude` (Phase 2).
- **`llm.py`**: deadline-aware каскад — `_attempt()` проверяет оставшийся бюджет до старта каждого фолбэка; `generate()` передаёт `deadline = monotonic() + LLM_OVERALL_TIMEOUT` (Phase 2).
- **`retrieval.py`**: метка источника RAG — guard при добавлении фактов писал `"_source"`, проверял `"source_label"`; исправлено: используется `"_source"` везде (Phase 1).
- **`scaffold.py`**: `_pick_item` на пустом датасете — guard в `_handle_content_cmd` перехватывает `FileNotFoundError` и пустой список, отвечает двуязычным «Пока нечего показать — загляните позже. 🍵» (Phase 1).
- **`scaffold.py`**: `on_error` извинялся только по-русски — теперь берёт язык через `_ui_lang`, двуязычное generic-извинение (Phase 1).
- **`scaffold.py`**: язык кнопок теперь берётся из `_ui_lang` (как команды), а не `memory.get_last_lang` — `/lang en` уважается inline-кнопками (Phase 1). ⚠️ Поведенческое изменение.
- **`memory.py`**: после `sqlite3.connect` устанавливаются `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` (Phase 2). ⚠️ Рядом с `bot.db` появятся `-wal`/`-shm`; деплой-скрипты, копирующие только `bot.db`, нужно обновить.
- **`deploy.yml` шаблон**: бэкпорт `--force-reinstall` в `pip install` (заявлен в 0.1.1, не бэкпортирован в шаблон) (Phase 6).

### Documentation
- `docs/CREATING-A-BOT.md`: добавлен раздел `extra_handlers` / `extra_bot_commands` / `bot_commands_menu` (сигнатура `run()`, порядок регистрации, пример); упомянуты `make check` и `memory.close()` (Phase 6).
- `README.md`: убран встроенный дубль changelog (заменён ссылкой на CHANGELOG.md); каскад LLM обновлён (`cliproxy→grok→claude-cli→claude→ollama`); актуальное число тестов (Phase 6).
- `docs/OPTIONAL-MODULES.md`: таблица статусов приведена к README (Phase 6).
- `CHANGELOG.md`: исправлено «Telethon-обёртка» → «PTB-каркас» в описании 0.1.1 (Phase 6).

### Removed
- `gen_avatars.py`, `gen_avatar_ifs.py`, `gen_avatar_lee_jacobs.py`, `gen_avatar_david_key.py` — заменены единым `scripts/gen_avatar.py` (Phase 4).
- `chatcore.egg-info/` удалён из git-индекса (был закоммичен по ошибке) (Phase 4).

### Risk
- `reload_env()` затирает ручные присваивания `llm.CONST = x` до вызова `run()` — нужно использовать env-переменные.
- Deadline-каскад: фолбэки при очень тесном `LLM_OVERALL_TIMEOUT` теперь пропускаются сразу, а не обрезаются на ходу; смягчение — `_MIN_ATTEMPT_BUDGET=3.0` с.

## [0.1.1] — 2026-07-05

### Added
- `scaffold.py`: параметр `extra_handlers: list[BaseHandler] | None` в `BotScaffold.__init__`, `build_app()` и `run()` — регистрация кастомных PTB-хендлеров до catch-all `CallbackQueryHandler` (first-match в group 0)

### Fixed
- `deploy.yml` шаблон: убран невалидный job-level `if: ${{ secrets.VPS_HOST != '' }}` (джоб не стартовал в GHA)
- `deploy.yml` шаблон: добавлен `--force-reinstall` в `pip install` (git-пин с той же версией не переустанавливался без флага)

## [0.1.0] — 2026-07-02

### Fixed
- `_claude_cli()`: добавлен флаг `--model CLAUDE_CLI_MODEL` (передавался, но игнорировался)
- `_claude_cli()`: проверка `returncode != 0` → `RuntimeError`; валидация пустого вывода и «Please run /login»
- Каскад `claude-cli`: фолбэк `claude-cli → cliproxy → ollama` (был прямой → ollama)
- `_summary_prompt(ru/en)`: guard — не включать в резюме отказы бота об отсутствии памяти
- `build_system_prompt()`: блок `conversation_summary` перенесён в конец промпта (после `reply_lang_rule`) для recency-эффекта

### Added
- Константа `CLAUDE_CLI_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "sonnet")`
- Docstring: предупреждение о cliproxy OAuth инжекции system-промпта; `CLAUDE_CLI_MODEL`, `CLAUDE_CONFIG_DIR` в списке env
- 10 регрессионных тестов (`tests/test_llm.py`, `tests/test_persona.py`)

### Initial release (0.1.0)
- Выделение chatcore как переиспользуемого ядра чат-персона-ботов
- LLM-каскад: `cliproxy → grok → claude-cli → claude → ollama`
- `persona.py`: сборка system prompt из `data/persona.json` (двуязычно)
- `memory.py`: SQLite rolling-history с поддержкой rolling summary
- `scaffold.py`: базовый PTB-каркас + `send_typing`
- `data_store.py`: hot-reload JSON
- `config.py`: глобальная конфигурация (assistant_label, user_label, db_path)
- CI/CD на GitHub Actions
