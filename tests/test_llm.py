"""Тесты устойчивости LLM-слоя.

Главные гарантии:
  * generate() никогда не висит дольше LLM_OVERALL_TIMEOUT;
  * при падении бэкенда работает каскад фолбэков.
"""
import asyncio

import pytest

from chatcore import llm

MSGS = [{"role": "user", "content": "привет"}]


async def _fail(*_a, **_k):
    raise RuntimeError("backend down")


async def _ok(*_a, **_k):
    return "fallback reply"


@pytest.mark.asyncio
async def test_generate_honours_overall_timeout(monkeypatch):
    """Зависший бэкенд не должен подвешивать generate() навсегда."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm, "LLM_OVERALL_TIMEOUT", 1)

    async def _hang(*_a, **_k):
        await asyncio.sleep(60)

    monkeypatch.setattr(llm, "_ollama", _hang)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(llm.generate("sys", MSGS), timeout=5)


@pytest.mark.asyncio
async def test_cliproxy_cascades_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "cliproxy")
    monkeypatch.setattr(llm, "_cliproxy", _fail)
    monkeypatch.setattr(llm, "_grok", _fail)
    monkeypatch.setattr(llm, "_ollama", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


@pytest.mark.asyncio
async def test_claude_cascades_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude")
    monkeypatch.setattr(llm, "_claude", _fail)
    monkeypatch.setattr(llm, "_ollama", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


def test_resolve_backend_explicit(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    assert llm._resolve_backend() == "ollama"


def test_flatten_messages_uses_config_labels():
    """_flatten_messages берёт метки из chatcore.config."""
    from chatcore import config
    config.setup(assistant_label="Персона", user_label="Гость")
    msgs = [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Добрый день"},
    ]
    flat = llm._flatten_messages(msgs)
    assert "Гость: Привет" in flat
    assert "Персона: Добрый день" in flat
