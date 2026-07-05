# Changelog — chatcore (sitex/chat)

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
