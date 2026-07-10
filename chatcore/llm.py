"""LLM-движок: claude-cli → cliproxy → ollama (и другие бэкенды).

Выбор через переменные окружения:
  LLM_BACKEND=auto|grok|cliproxy|claude-cli|claude|ollama
    auto: cliproxy если есть CLIPROXY_API_KEY,
          иначе grok если есть GROK_BIN,
          иначе claude-cli если есть CLAUDE_CLI_BIN,
          иначе claude если есть ANTHROPIC_API_KEY,
          иначе ollama
  CLIPROXY_BASE_URL=         (cliproxyapi; оставить пустым если не используется)
  CLIPROXY_API_KEY=...
  CLIPROXY_MODEL=claude-sonnet-4-6
  GROK_BIN=~/.grok/bin/grok  (путь к Grok CLI)
  CLAUDE_CLI_BIN=~/.nvm/versions/node/v22.19.0/bin/claude  (путь к claude CLI)
  CLAUDE_CLI_TIMEOUT=45
  CLAUDE_CLI_MODEL=sonnet     (передаётся как --model; по умолч. "sonnet")
  CLAUDE_CONFIG_DIR=...       (если credentials не в ~/.claude/, напр. .claude-bot/)
  ANTHROPIC_API_KEY=...
  CLAUDE_MODEL=claude-sonnet-4-6
  OLLAMA_HOST=http://localhost:11434
  OLLAMA_MODEL=qwen3:8b
  LLM_MAX_TOKENS=700
  LLM_TIMEOUT=25
  GROK_TIMEOUT=45
  LLM_OVERALL_TIMEOUT=60

ВАЖНО: cliproxy с OAuth-аккаунтом Claude Code инжектит свой system-промпт
("You are Claude Code, Anthropic's official CLI for Claude.") поверх нашего.
Это ломает персону. Поэтому backend=claude-cli работает в строгом режиме:
при ошибке _claude_cli исключение поднимается наверх (bot.py покажет
fallback-текст); фолбэка на cliproxy или ollama НЕТ.

Метка ассистента в «плоском» тексте для grok берётся из chatcore.config.

Схема дедлайнов каскада:
  generate() вычисляет deadline = now + LLM_OVERALL_TIMEOUT и передаёт его
  в _cascade(). Перед каждым бэкендом _attempt() проверяет оставшийся
  бюджет; если он меньше _MIN_ATTEMPT_BUDGET — бэкенд пропускается
  с asyncio.TimeoutError("budget exhausted"). Внешний wait_for(
  LLM_OVERALL_TIMEOUT+1) — страховка от зависания без исключений.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time

import httpx

from . import config as _config

log = logging.getLogger("chatcore.llm")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


async def _kill_and_reap(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):
        await proc.wait()

GROK_BIN: str
CLAUDE_MODEL: str
OLLAMA_HOST: str
OLLAMA_MODEL: str
MAX_TOKENS: int
LLM_TIMEOUT: int
LLM_OVERALL_TIMEOUT: int
GROK_TIMEOUT: int
CLAUDE_CLI_BIN: str
CLAUDE_CLI_TIMEOUT: int
CLAUDE_CLI_MODEL: str
SUMMARY_MODEL: str
SUMMARY_TIMEOUT: int
CLIPROXY_BASE_URL: str
CLIPROXY_API_KEY: str
CLIPROXY_MODEL: str


def _read_env() -> None:
    global GROK_BIN, CLAUDE_MODEL, OLLAMA_HOST, OLLAMA_MODEL, MAX_TOKENS
    global LLM_TIMEOUT, LLM_OVERALL_TIMEOUT, GROK_TIMEOUT
    global CLAUDE_CLI_BIN, CLAUDE_CLI_TIMEOUT, CLAUDE_CLI_MODEL
    global SUMMARY_MODEL, SUMMARY_TIMEOUT
    global CLIPROXY_BASE_URL, CLIPROXY_API_KEY, CLIPROXY_MODEL
    GROK_BIN = os.path.expanduser(os.environ.get("GROK_BIN", "~/.grok/bin/grok"))
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "700"))
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "25"))
    LLM_OVERALL_TIMEOUT = int(os.environ.get("LLM_OVERALL_TIMEOUT", "60"))
    GROK_TIMEOUT = int(os.environ.get("GROK_TIMEOUT", "45"))
    CLAUDE_CLI_BIN = os.path.expanduser(
        os.environ.get("CLAUDE_CLI_BIN", "/home/rocky/.nvm/versions/node/v22.19.0/bin/claude")
    )
    CLAUDE_CLI_TIMEOUT = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "45"))
    CLAUDE_CLI_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "sonnet")
    SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "sonnet")
    SUMMARY_TIMEOUT = int(os.environ.get("SUMMARY_TIMEOUT", "60"))
    CLIPROXY_BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "")
    CLIPROXY_API_KEY = os.environ.get("CLIPROXY_API_KEY", "")
    CLIPROXY_MODEL = os.environ.get("CLIPROXY_MODEL", "claude-sonnet-4-6")


reload_env = _read_env
_read_env()

_MIN_ATTEMPT_BUDGET = 3.0


def _resolve_backend() -> str:
    backend = os.environ.get("LLM_BACKEND", "auto").lower()
    if backend == "auto":
        if CLIPROXY_API_KEY and CLIPROXY_BASE_URL:
            return "cliproxy"
        if os.path.isfile(GROK_BIN):
            return "grok"
        if os.path.isfile(CLAUDE_CLI_BIN):
            return "claude-cli"
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "ollama"
    return backend


def _flatten_messages(messages: list[dict]) -> str:
    """Сворачивает историю диалога в плоский текст для Grok CLI -p."""
    assistant_label = _config.get_assistant_label()
    user_label = _config.get_user_label()
    parts = []
    for msg in messages:
        role = user_label if msg["role"] == "user" else assistant_label
        parts.append(f"{role}: {msg['content']}")
    return "\n\n".join(parts)


async def _grok(system: str, messages: list[dict]) -> str:
    prompt = _flatten_messages(messages)
    proc = await asyncio.create_subprocess_exec(
        GROK_BIN, "-p", prompt,
        "--system-prompt-override", system,
        "--disable-web-search",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=GROK_TIMEOUT)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        await _kill_and_reap(proc)
        raise
    return stdout.decode().strip()


async def _claude_cli(system: str, messages: list[dict]) -> str:
    prompt = _flatten_messages(messages)
    args = [CLAUDE_CLI_BIN, "-p", prompt, "--system-prompt", system]
    if CLAUDE_CLI_MODEL:
        args += ["--model", CLAUDE_CLI_MODEL]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_CLI_TIMEOUT)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        await _kill_and_reap(proc)
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude-cli rc={proc.returncode}: {stderr.decode(errors='replace')[:200]}"
        )
    out = stdout.decode(errors="replace").strip()
    if not out or "Please run /login" in out:
        raise RuntimeError(f"claude-cli invalid output: {out[:100]!r}")
    return out


async def _cliproxy(system: str, messages: list[dict]) -> str:
    from anthropic import AsyncAnthropic

    async with AsyncAnthropic(base_url=CLIPROXY_BASE_URL, api_key=CLIPROXY_API_KEY) as client:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=CLIPROXY_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,  # type: ignore[arg-type]
            ),
            timeout=LLM_TIMEOUT,
        )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def _claude(system: str, messages: list[dict]) -> str:
    from anthropic import AsyncAnthropic

    async with AsyncAnthropic() as client:
        resp = await asyncio.wait_for(
            client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,  # type: ignore[arg-type]
            ),
            timeout=LLM_TIMEOUT,
        )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def _ollama(system: str, messages: list[dict]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": False,
        "options": {"temperature": 0.8},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
        r.raise_for_status()
        content = r.json()["message"]["content"]
        return _THINK_RE.sub("", content).strip()


async def _attempt(
    fn,
    system: str,
    messages: list[dict],
    deadline: float | None,
) -> str:
    """Вызвать fn с учётом оставшегося бюджета.

    Если deadline is None — вызов без ограничений.
    Если оставшийся бюджет < _MIN_ATTEMPT_BUDGET — сразу asyncio.TimeoutError.
    Иначе — asyncio.wait_for(fn, remaining).
    """
    if deadline is None:
        return await fn(system, messages)
    remaining = deadline - time.monotonic()
    if remaining < _MIN_ATTEMPT_BUDGET:
        raise asyncio.TimeoutError(f"llm budget exhausted before {fn.__name__}")
    return await asyncio.wait_for(fn(system, messages), timeout=remaining)


async def _cascade(backend: str, system: str, messages: list[dict], deadline: float | None = None) -> str:
    if backend == "cliproxy":
        try:
            return await _attempt(_cliproxy, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.warning("cliproxy failed (%s), falling back to grok", e)
        try:
            return await _attempt(_grok, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.warning("grok fallback failed (%s), falling back to ollama", e)
        return await _attempt(_ollama, system, messages, deadline)

    if backend == "grok":
        try:
            return await _attempt(_grok, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.warning("grok failed (%s), falling back to claude-cli", e)
        try:
            return await _attempt(_claude_cli, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.warning("claude-cli fallback failed (%s), falling back to ollama", e)
        return await _attempt(_ollama, system, messages, deadline)

    if backend == "claude-cli":
        try:
            return await _attempt(_claude_cli, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            # Фолбэк на cliproxy инжектит промпт Claude Code поверх персоны
            # (persona-break); фолбэк на ollama даёт другую модель без
            # предупреждения. Честнее упасть — bot покажет fallback-текст.
            log.error("claude-cli failed, no fallback (strict mode): %s", e)
            raise

    if backend == "claude":
        try:
            return await _attempt(_claude, system, messages, deadline)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            log.warning("claude failed (%s), falling back to ollama", e)
        return await _attempt(_ollama, system, messages, deadline)

    return await _attempt(_ollama, system, messages, deadline)


async def generate(
    system: str, messages: list[dict], backend: str | None = None
) -> str:
    """messages: [{'role':'user'|'assistant','content':str}, ...].

    backend — явный override бэкенда (для служебных вызовов вроде
    режиссёра стола); None → _resolve_backend() как раньше.

    Гарантированно завершается не позже LLM_OVERALL_TIMEOUT секунд — иначе
    обработчик сообщения мог бы зависнуть навсегда и бот молчал бы на текст.
    При истечении дедлайна/ошибке поднимается исключение, которое ловит
    on_message и шлёт пользователю человекочитаемый фолбэк.
    """
    backend = backend or _resolve_backend()
    t0 = time.monotonic()
    deadline = t0 + LLM_OVERALL_TIMEOUT
    try:
        result = await asyncio.wait_for(
            _cascade(backend, system, messages, deadline), timeout=LLM_OVERALL_TIMEOUT + 1
        )
    except asyncio.TimeoutError:
        log.error("llm generate timed out after %ss (backend=%s)", LLM_OVERALL_TIMEOUT, backend)
        raise
    finally:
        elapsed = time.monotonic() - t0
        log.info(
            "llm backend=%s model=%s latency=%.2fs",
            backend,
            CLIPROXY_MODEL if backend == "cliproxy" else backend,
            elapsed,
        )
    return result


def active_backend() -> str:
    return _resolve_backend()


# ---------- суммаризация истории (rolling summary) ----------

def _summary_prompt(prev_summary: str, folded: list[dict], lang: str) -> str:
    convo = _flatten_messages(folded)
    prev = prev_summary.strip() or ("(пусто)" if lang == "ru" else "(empty)")
    if lang == "ru":
        return (
            "Ты ведёшь сжатое резюме диалога. Обнови резюме, вплавив новые реплики "
            "в уже имеющееся. Сохраняй важное: факты о пользователе, его запросы и "
            "цели, ключевые темы, договорённости и данные обещания, значимые детали. "
            "Не включай в резюме утверждения бота об отсутствии у него "
            "памяти или истории разговоров — это техническая ошибка, а не "
            "содержание разговора. "
            "Пиши сжато, до ~200 слов, по-русски, "
            "без приветствий — только суть. Верни ТОЛЬКО текст резюме.\n\n"
            f"ТЕКУЩЕЕ РЕЗЮМЕ:\n{prev}\n\n"
            f"НОВЫЕ РЕПЛИКИ:\n{convo}\n\n"
            "ОБНОВЛЁННОЕ РЕЗЮМЕ:"
        )
    return (
        "You maintain a running summary of a dialogue. Update the summary by folding "
        "the new turns into the existing one. Preserve: facts about the user, their "
        "requests and goals, key topics, commitments and promises made, notable details. "
        "Do not include any claims by the bot that it lacks memory or conversation "
        "history — that is a technical glitch, not conversation content. "
        "Be concise, up to ~200 words, "
        "in English, no greetings — just the essence. Return ONLY the summary text.\n\n"
        f"CURRENT SUMMARY:\n{prev}\n\n"
        f"NEW TURNS:\n{convo}\n\n"
        "UPDATED SUMMARY:"
    )


async def _summary_cli(prompt: str) -> str:
    """Суммаризация через headless Claude Code CLI (`claude -p`)."""
    args = [CLAUDE_CLI_BIN, "-p", prompt]
    if SUMMARY_MODEL:
        args += ["--model", SUMMARY_MODEL]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SUMMARY_TIMEOUT
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        await _kill_and_reap(proc)
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p rc={proc.returncode}: {stderr.decode(errors='replace')[:200]}"
        )
    out = stdout.decode(errors="replace").strip()
    if not out:
        raise RuntimeError("claude -p returned empty output")
    return out


async def summarize(prev_summary: str, folded: list[dict], lang: str = "ru") -> str:
    """Свернуть старые реплики в обновлённое резюме.

    Предпочитает `claude -p` (бесплатно по Max-подписке); при ошибке —
    фолбэк на активный LLM-каскад.
    """
    prompt = _summary_prompt(prev_summary, folded, lang)
    try:
        return await _summary_cli(prompt)
    except Exception as e:
        log.warning("summarize via claude-cli failed (%s), falling back to cascade", e)
        system = (
            "Ты — ассистент, который сжимает диалог в краткое точное резюме."
            if lang == "ru"
            else "You compress a dialogue into a concise, accurate summary."
        )
        return await _cascade(
            _resolve_backend(), system, [{"role": "user", "content": prompt}]
        )
