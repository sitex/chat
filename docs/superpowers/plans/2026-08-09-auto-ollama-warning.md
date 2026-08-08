# Auto → Ollama WARNING Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать неявный переход `LLM_BACKEND=auto` к финальному fallback `ollama` диагностическим `WARNING`, не добавляя шума на штатные пути выбора бэкенда.

**Architecture:** Изменение ограничено фазой резолюции в `_resolve_backend()`: порядок и маршруты auto-каскада сохраняются, а финальный `ollama` получает одно предупреждение с суммарной причиной и деталями по каждому upstream. Runtime-каскад `_cascade()`, strict `claude-cli`, timeout и суммаризация не меняются. Работа выполняется поверх уже существующего незакоммиченного delta: сначала его сверка со спецификацией, затем исправляются только расхождения.

**Tech Stack:** Python 3.10+, `logging`, `pytest`/`pytest-asyncio`, `ruff`, GitHub CLI.

---

## Карта файлов

| Файл | Ответственность | Действие |
|---|---|---|
| `chatcore/llm.py` | Резолюция `LLM_BACKEND`, диагностика auto-fallback | Изменить только текст `WARNING`, если он не называет суммарную причину в явном виде; сохранить порядок выбора и helper деталей. |
| `tests/test_llm.py` | Регрессии резолюции и уровней логирования | Усилить проверку причины в `WARNING`; добавить покрытие тихой успешной auto-резолюции. |
| `CHANGELOG.md` | Операторское описание изменения `0.1.16` | Сохранить/уточнить только запись #30 и инструкцию `LLM_BACKEND=ollama`. |
| `pyproject.toml` | Версия пакета | Оставить `0.1.16` только если changelog #30 остаётся выпуском `0.1.16`. |
| `.claude/settings.json` | Локальная настройка Claude Code | Не включать в issue #30: изменение модели не относится к LLM-резолюции библиотеки. |

### Task 1: Сверить и изолировать существующий рабочий delta

**Files:**
- Modify: не требуется до обнаружения расхождения
- Inspect: `chatcore/llm.py:118-155`, `tests/test_llm.py:97-129`, `CHANGELOG.md:1-27`, `pyproject.toml:5-8`, `.claude/settings.json:1-15`

- [x] **Step 1: Проверить состояние и отсутствие ошибок пробелов.**

Run:
```bash
git status --short
git diff --check
git diff -- chatcore/llm.py tests/test_llm.py CHANGELOG.md pyproject.toml .claude/settings.json
```

Expected: delta #30 находится только в `chatcore/llm.py`, `tests/test_llm.py`, `CHANGELOG.md` и согласованном с релизом `pyproject.toml`; `.claude/settings.json` отображается как отдельная, не относящаяся к issue правка. `git diff --check` завершается без ошибок.

- [x] **Step 2: Сопоставить delta с утверждённой спецификацией.**

Проверить каждое требование `docs/superpowers/specs/2026-08-09-auto-ollama-warning-design.md`:

```text
LLM_BACKEND=auto + no cliproxy/grok/claude-cli/claude → ровно один WARNING → ollama.
LLM_BACKEND=ollama → ollama без WARNING.
Успешный auto → cliproxy/grok/claude-cli/claude → без WARNING.
WARNING объясняет, что все upstream недоступны, и называет причины каждого.
_cascade(), summarize(), timeout и strict claude-cli не меняются.
```

Expected: единственное известное расхождение — заголовок текущего предупреждения должен явно сказать «ни один из cliproxy/grok/claude-cli/claude недоступен», а не только «скатилась в фолбэк ollama».

- [x] **Step 3: Зафиксировать границу staging.**

Планируемый issue #30 набор:

```text
chatcore/llm.py
tests/test_llm.py
CHANGELOG.md
pyproject.toml
```

Исключённый набор:

```text
.claude/settings.json
```

Expected: `.claude/settings.json` остаётся незастейдженным до и после issue-коммита; его перечисляют в комментарии к issue как сохранённую чужую правку.

### Task 2: Зафиксировать контракт WARNING тестами (TDD)

**Files:**
- Modify: `tests/test_llm.py:102-129`
- Test: `tests/test_llm.py`

- [x] **Step 1: Усилить тест деградации `auto → ollama` ожидаемым текстом причины.**

В `test_resolve_backend_auto_fallback_logs_warning()` после `msg = record.getMessage()` добавить проверку суммарной причины и сохранить проверки деталей:

```python
assert "ни один из cliproxy/grok/claude-cli/claude недоступен" in msg
assert "ollama" in msg
assert "cliproxy" in msg and "CLIPROXY_API_KEY" in msg
assert "grok" in msg and "/nonexistent/grok" in msg
assert "claude-cli" in msg and "/nonexistent/claude" in msg
assert "claude" in msg and "ANTHROPIC_API_KEY" in msg
```

- [x] **Step 2: Запустить точечную регрессию и подтвердить её падение до корректировки текста.**

Run:
```bash
pytest tests/test_llm.py::test_resolve_backend_auto_fallback_logs_warning -v
```

Expected: FAIL на отсутствии фразы `ни один из cliproxy/grok/claude-cli/claude недоступен` в текущем сообщении `WARNING`.

- [x] **Step 3: Добавить тест штатной успешной auto-резолюции без предупреждения.**

Вставить рядом с тестом явного Ollama:

```python
def test_resolve_backend_auto_upstream_no_warning(monkeypatch, caplog):
    """auto → доступный cliproxy — штатная резолюция без WARNING."""
    monkeypatch.setenv("LLM_BACKEND", "auto")
    monkeypatch.setattr(llm, "CLIPROXY_API_KEY", "key")
    monkeypatch.setattr(llm, "CLIPROXY_BASE_URL", "http://proxy:8317")

    with caplog.at_level("WARNING", logger="chatcore.llm"):
        assert llm._resolve_backend() == "cliproxy"

    assert not [r for r in caplog.records if r.levelname == "WARNING"]
```

- [x] **Step 4: Запустить три резолюционные регрессии.**

Run:
```bash
pytest tests/test_llm.py::test_resolve_backend_auto_fallback_logs_warning tests/test_llm.py::test_resolve_backend_explicit_ollama_no_warning tests/test_llm.py::test_resolve_backend_auto_upstream_no_warning -v
```

Expected: первая регрессия всё ещё FAIL до изменения `chatcore/llm.py`; две проверки отсутствия предупреждения PASS.

### Task 3: Исправить только текст диагностического WARNING

**Files:**
- Modify: `chatcore/llm.py:118-155`
- Test: `tests/test_llm.py:102-145`

- [x] **Step 1: Заменить вызов `log.warning` в финальной ветке `auto` на диагностический текст.**

Сохранить условия и `return "ollama"`; заменить только строку формата:

```python
        log.warning(
            "LLM auto-резолюция: ни один из cliproxy/grok/claude-cli/claude "
            "недоступен; переход на ollama: %s",
            _describe_auto_fallback(),
        )
```

Не менять `_describe_auto_fallback()`: он уже перечисляет отсутствующие `CLIPROXY_API_KEY`/`CLIPROXY_BASE_URL`, пути `GROK_BIN` и `CLAUDE_CLI_BIN`, а также `ANTHROPIC_API_KEY`.

- [x] **Step 2: Запустить три точечных теста после изменения.**

Run:
```bash
pytest tests/test_llm.py::test_resolve_backend_auto_fallback_logs_warning tests/test_llm.py::test_resolve_backend_explicit_ollama_no_warning tests/test_llm.py::test_resolve_backend_auto_upstream_no_warning -v
```

Expected: PASS, 3 passed.

- [x] **Step 3: Проверить, что соседние пути не изменились.**

Run:
```bash
git diff --check
git diff -- chatcore/llm.py
```

Expected: diff затрагивает только `_resolve_backend()` и `_describe_auto_fallback()`; `_cascade()`, `generate()` и `summarize()` не изменены.

### Task 4: Проверить changelog, версию и полный набор качества

**Files:**
- Modify: `CHANGELOG.md:1-27` только при несоответствии спецификации
- Modify: `pyproject.toml:5-8` только при нарушении соответствия changelog/release
- Test: `tests/test_llm.py`

- [x] **Step 1: Сверить операторскую документацию.**

Запись `0.1.16` в `CHANGELOG.md` должна содержать оба факта:

```text
При auto без всех upstream записывается WARNING с причинами отказа.
Для намеренной работы через Ollama оператор задаёт LLM_BACKEND=ollama явно, без WARNING.
```

Expected: если оба факта уже описаны, не редактировать `CHANGELOG.md`; не добавлять информацию о новых проверках Ollama или других fallback-маршрутах.

- [x] **Step 2: Сверить версию релиза.**

Run:
```bash
python -c "from pathlib import Path; import re; p=Path('pyproject.toml').read_text(); print(re.search(r'^version = \"([^\"]+)\"$', p, re.M).group(1))"
```

Expected: `0.1.16`, совпадающая с заголовком changelog. Если значение уже `0.1.16`, не редактировать `pyproject.toml` повторно.

- [x] **Step 3: Запустить тесты и статический анализ затронутых модулей.**

Run:
```bash
pytest tests/test_llm.py -v
ruff check chatcore/llm.py tests/test_llm.py
```

Expected: все тесты `tests/test_llm.py` PASS; `ruff` завершается без замечаний.

### Task 5: Закоммитить строго issue #30 и документировать сохранённую чужую правку

**Files:**
- Stage: `chatcore/llm.py`, `tests/test_llm.py`, `CHANGELOG.md`, `pyproject.toml`
- Exclude: `.claude/settings.json`

- [x] **Step 1: Убедиться, что staging содержит только файлы issue.**

Run:
```bash
git add chatcore/llm.py tests/test_llm.py CHANGELOG.md pyproject.toml
git diff --cached --name-only
git status --short
```

Expected cached paths:

```text
CHANGELOG.md
chatcore/llm.py
pyproject.toml
tests/test_llm.py
```

Expected unstaged path:

```text
 M .claude/settings.json
```

- [x] **Step 2: Создать целевой коммит.**

Run:
```bash
git commit -m "fix(llm): предупреждать auto→ollama fallback (#30)" \
  -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

Expected: один новый коммит с реализацией #30; `.claude/settings.json` не включён.

- [x] **Step 3: Повторно проверить состояние и отправить комментарий к issue.**

Run:
```bash
git status --short
gh issue comment 30 --body "Реализация завершена: auto→ollama теперь пишет диагностический WARNING с причиной недоступности cliproxy/grok/claude-cli/claude; явный LLM_BACKEND=ollama остаётся тихим. Проверено: pytest tests/test_llm.py -v, ruff check chatcore/llm.py tests/test_llm.py. В рабочем дереве сознательно оставлена не относящаяся к #30 правка: .claude/settings.json (переключение модели Claude Code); она не вошла в коммит."
```

Expected: GitHub содержит русскоязычный комментарий о результате, валидации и исключённой чужой правке.

- [x] **Step 4: Закрыть issue после успешного комментария и проверки.**

Run:
```bash
gh issue close 30 --comment "Issue закрыт после коммита реализации и прохождения проверок."
```

Expected: issue #30 имеет состояние `closed`; локальное рабочее дерево по-прежнему содержит только сохранённую внешнюю правку `.claude/settings.json`.
