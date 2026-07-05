"""Тесты устойчивости LLM-слоя.

Главные гарантии:
  * generate() никогда не висит дольше LLM_OVERALL_TIMEOUT;
  * при падении бэкенда работает каскад фолбэков.
"""
import asyncio

import pytest

from chatcore import llm

# ── регрессионные тесты (Phase 1, коммит 0d3bf66) ─────────────────────────────


class _FakeProc:
    def __init__(self, rc=0, stdout=b"ok response", stderr=b""):
        self.returncode = rc
        self._stdout = stdout
        self._stderr = stderr
        self.wait_called = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        pass

    async def wait(self):
        self.wait_called = True


class _HangProc:
    """Процесс с вечным communicate() — имитирует зависший подпроцесс."""
    def __init__(self):
        self.returncode = None
        self.wait_called = False
        self.killed = False

    async def communicate(self):
        await asyncio.sleep(9999)
        return b"", b""

    def kill(self):
        self.killed = True

    async def wait(self):
        self.wait_called = True

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


@pytest.mark.asyncio
async def test_claude_cli_cascades_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude-cli")
    monkeypatch.setattr(llm, "_claude_cli", _fail)
    monkeypatch.setattr(llm, "_cliproxy", _fail)
    monkeypatch.setattr(llm, "_ollama", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


@pytest.mark.asyncio
async def test_grok_cascades_to_claude_cli(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "grok")
    monkeypatch.setattr(llm, "_grok", _fail)
    monkeypatch.setattr(llm, "_claude_cli", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


@pytest.mark.asyncio
async def test_summarize_falls_back_to_cascade(monkeypatch):
    """summarize() при падении _summary_cli фолбэчит на LLM-каскад."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm, "_summary_cli", _fail)
    monkeypatch.setattr(llm, "_ollama", _ok)

    result = await llm.summarize("", [{"role": "user", "content": "тест"}], "ru")
    assert result == "fallback reply"


# ── регрессия 1: _claude_cli передаёт --model ─────────────────────────────────

@pytest.mark.asyncio
async def test_claude_cli_passes_model_flag(monkeypatch):
    """_claude_cli включает --model CLAUDE_CLI_MODEL в args subprocess."""
    captured: list = []

    async def _fake_exec(*args, **kwargs):
        captured.extend(args)
        return _FakeProc()

    monkeypatch.setattr(llm, "CLAUDE_CLI_MODEL", "opus")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    await llm._claude_cli("sys", MSGS)
    assert "--model" in captured
    assert "opus" in captured


# ── регрессия 2: _claude_cli поднимает RuntimeError при rc!=0, пустом выводе, /login ──

@pytest.mark.asyncio
async def test_claude_cli_raises_on_nonzero_rc(monkeypatch):
    async def _fake_exec(*args, **kwargs):
        return _FakeProc(rc=1, stdout=b"", stderr=b"auth error")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    with pytest.raises(RuntimeError, match="rc=1"):
        await llm._claude_cli("sys", MSGS)


@pytest.mark.asyncio
async def test_claude_cli_raises_on_empty_output(monkeypatch):
    async def _fake_exec(*args, **kwargs):
        return _FakeProc(rc=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    with pytest.raises(RuntimeError, match="invalid output"):
        await llm._claude_cli("sys", MSGS)


@pytest.mark.asyncio
async def test_claude_cli_raises_on_login_prompt(monkeypatch):
    async def _fake_exec(*args, **kwargs):
        return _FakeProc(rc=0, stdout=b"Please run /login to authenticate", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    with pytest.raises(RuntimeError, match="invalid output"):
        await llm._claude_cli("sys", MSGS)


# ── регрессия 3: каскад claude-cli → cliproxy → ollama ────────────────────────

@pytest.mark.asyncio
async def test_claude_cli_cascades_to_cliproxy(monkeypatch):
    """При падении _claude_cli — фолбэк на _cliproxy."""
    monkeypatch.setenv("LLM_BACKEND", "claude-cli")
    monkeypatch.setattr(llm, "_claude_cli", _fail)
    monkeypatch.setattr(llm, "_cliproxy", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


@pytest.mark.asyncio
async def test_claude_cli_cascades_to_ollama_when_cliproxy_also_fails(monkeypatch):
    """При падении и _claude_cli и _cliproxy — фолбэк на _ollama."""
    monkeypatch.setenv("LLM_BACKEND", "claude-cli")
    monkeypatch.setattr(llm, "_claude_cli", _fail)
    monkeypatch.setattr(llm, "_cliproxy", _fail)
    monkeypatch.setattr(llm, "_ollama", _ok)

    out = await llm.generate("sys", MSGS)
    assert out == "fallback reply"


# ── регрессия 4: guard суммаризатора ──────────────────────────────────────────

def test_summary_prompt_ru_has_guard():
    prompt = llm._summary_prompt("", [{"role": "user", "content": "привет"}], "ru")
    assert "техническая ошибка" in prompt


def test_summary_prompt_en_has_guard():
    prompt = llm._summary_prompt("", [{"role": "user", "content": "hi"}], "en")
    assert "technical glitch" in prompt


# ── Phase 1.1: _kill_and_reap вызывает wait() после kill() ────────────────────

@pytest.mark.asyncio
async def test_grok_timeout_calls_wait(monkeypatch):
    """При таймауте _grok должен вызывать wait() (не оставлять зомби)."""
    proc = _HangProc()

    async def _fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(llm, "GROK_TIMEOUT", 0.05)

    with pytest.raises((asyncio.TimeoutError, asyncio.CancelledError)):
        await llm._grok("sys", MSGS)

    assert proc.killed
    assert proc.wait_called


@pytest.mark.asyncio
async def test_claude_cli_timeout_calls_wait(monkeypatch):
    """При таймауте _claude_cli должен вызывать wait() (не оставлять зомби)."""
    proc = _HangProc()

    async def _fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(llm, "CLAUDE_CLI_TIMEOUT", 0.05)

    with pytest.raises((asyncio.TimeoutError, asyncio.CancelledError)):
        await llm._claude_cli("sys", MSGS)

    assert proc.killed
    assert proc.wait_called


@pytest.mark.asyncio
async def test_summary_cli_timeout_calls_wait(monkeypatch):
    """При таймауте _summary_cli должен вызывать wait() (не оставлять зомби)."""
    proc = _HangProc()

    async def _fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(llm, "SUMMARY_TIMEOUT", 0.05)

    with pytest.raises((asyncio.TimeoutError, asyncio.CancelledError)):
        await llm._summary_cli("some prompt")

    assert proc.killed
    assert proc.wait_called


# ── Phase 2.2: deadline-aware бюджет каскада ──────────────────────────────────

@pytest.mark.asyncio
async def test_budget_exhausted_before_fallback(monkeypatch):
    """Primary съедает бюджет → fallback не стартует, TimeoutError упоминает budget."""
    monkeypatch.setenv("LLM_BACKEND", "claude-cli")
    monkeypatch.setattr(llm, "LLM_OVERALL_TIMEOUT", 0.5)
    monkeypatch.setattr(llm, "_MIN_ATTEMPT_BUDGET", 0.3)

    async def _slow_fail(*_a, **_k):
        await asyncio.sleep(0.3)
        raise RuntimeError("primary failed")

    fallback_called = [False]

    async def _fallback(*_a, **_k):
        fallback_called[0] = True
        return "fallback reply"

    monkeypatch.setattr(llm, "_claude_cli", _slow_fail)
    monkeypatch.setattr(llm, "_cliproxy", _fallback)
    monkeypatch.setattr(llm, "_ollama", _fallback)

    with pytest.raises(asyncio.TimeoutError, match="budget"):
        await llm.generate("sys", MSGS)

    assert not fallback_called[0]


# ── Phase 3.1: reload_env() обновляет модульные константы ─────────────────────

def test_reload_env_updates_constants(monkeypatch):
    """reload_env() читает актуальное значение из os.environ."""
    monkeypatch.setenv("LLM_TIMEOUT", "7")
    llm.reload_env()
    assert llm.LLM_TIMEOUT == 7


def test_reload_env_restores_defaults(monkeypatch):
    """После снятия env-переменной reload_env() восстанавливает дефолт."""
    monkeypatch.setenv("LLM_TIMEOUT", "7")
    llm.reload_env()
    monkeypatch.delenv("LLM_TIMEOUT")
    llm.reload_env()
    assert llm.LLM_TIMEOUT == 25
