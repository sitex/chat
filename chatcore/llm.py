"""LLM-движок: cliproxy → grok → claude-cli → claude → ollama.

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
  ANTHROPIC_API_KEY=...
  CLAUDE_MODEL=claude-sonnet-4-6
  OLLAMA_HOST=http://localhost:11434
  OLLAMA_MODEL=qwen3:8b
  LLM_MAX_TOKENS=700
  LLM_TIMEOUT=25
  GROK_TIMEOUT=45
  LLM_OVERALL_TIMEOUT=60

Метка ассистента в «плоском» тексте для grok берётся из chatcore.config.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time

import httpx

from . import config as _config

log = logging.getLogger("chatcore.llm")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

GROK_BIN = os.path.expanduser(os.environ.get("GROK_BIN", "~/.grok/bin/grok"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "700"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "25"))
# Жёсткий общий дедлайн на весь каскад бэкендов — чтобы generate() никогда
# не зависал бесконечно (иначе обработчик сообщения молчит навсегда).
LLM_OVERALL_TIMEOUT = int(os.environ.get("LLM_OVERALL_TIMEOUT", "60"))
GROK_TIMEOUT = int(os.environ.get("GROK_TIMEOUT", "45"))
CLAUDE_CLI_BIN = os.path.expanduser(
    os.environ.get("CLAUDE_CLI_BIN", "/home/rocky/.nvm/versions/node/v22.19.0/bin/claude")
)
CLAUDE_CLI_TIMEOUT = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "45"))

CLIPROXY_BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "")
CLIPROXY_API_KEY = os.environ.get("CLIPROXY_API_KEY", "")
CLIPROXY_MODEL = os.environ.get("CLIPROXY_MODEL", "claude-sonnet-4-6")


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
        proc.kill()
        raise
    return stdout.decode().strip()


async def _claude_cli(system: str, messages: list[dict]) -> str:
    prompt = _flatten_messages(messages)
    proc = await asyncio.create_subprocess_exec(
        CLAUDE_CLI_BIN, "-p", prompt,
        "--system-prompt", system,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_CLI_TIMEOUT)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        proc.kill()
        raise
    return stdout.decode().strip()


async def _cliproxy(system: str, messages: list[dict]) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(base_url=CLIPROXY_BASE_URL, api_key=CLIPROXY_API_KEY)
    resp = await asyncio.wait_for(
        client.messages.create(
            model=CLIPROXY_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        ),
        timeout=LLM_TIMEOUT,
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def _claude(system: str, messages: list[dict]) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    resp = await asyncio.wait_for(
        client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
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


async def _cascade(backend: str, system: str, messages: list[dict]) -> str:
    if backend == "cliproxy":
        try:
            return await _cliproxy(system, messages)
        except Exception as e:
            log.warning("cliproxy failed (%s), falling back to grok", e)
            try:
                return await _grok(system, messages)
            except Exception as e2:
                log.warning("grok fallback failed (%s), falling back to ollama", e2)
                return await _ollama(system, messages)
    if backend == "grok":
        try:
            return await _grok(system, messages)
        except Exception as e:
            log.warning("grok failed (%s), falling back to claude-cli", e)
            try:
                return await _claude_cli(system, messages)
            except Exception as e2:
                log.warning("claude-cli fallback failed (%s), falling back to ollama", e2)
                return await _ollama(system, messages)
    if backend == "claude-cli":
        try:
            return await _claude_cli(system, messages)
        except Exception as e:
            log.warning("claude-cli failed (%s), falling back to ollama", e)
            return await _ollama(system, messages)
    if backend == "claude":
        try:
            return await _claude(system, messages)
        except Exception as e:
            log.warning("claude failed (%s), falling back to ollama", e)
            return await _ollama(system, messages)
    return await _ollama(system, messages)


async def generate(system: str, messages: list[dict]) -> str:
    """messages: [{'role':'user'|'assistant','content':str}, ...].

    Гарантированно завершается не позже LLM_OVERALL_TIMEOUT секунд — иначе
    обработчик сообщения мог бы зависнуть навсегда и бот молчал бы на текст.
    При истечении дедлайна/ошибке поднимается исключение, которое ловит
    on_message и шлёт пользователю человекочитаемый фолбэк.
    """
    backend = _resolve_backend()
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(
            _cascade(backend, system, messages), timeout=LLM_OVERALL_TIMEOUT
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
