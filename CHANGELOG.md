# Changelog — chatcore (sitex/chat)

## [Unreleased]

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
- `scaffold.py`: базовая Telethon-обёртка + `send_typing`
- `data_store.py`: hot-reload JSON
- `config.py`: глобальная конфигурация (assistant_label, user_label, db_path)
- CI/CD на GitHub Actions
