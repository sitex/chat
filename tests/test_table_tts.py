"""Unit-тесты для scripts/table_tts.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# table_tts живёт в scripts/, добавляем в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import table_tts

# roundtable.py нужен только для импорта DEFAULT_PERSONAS — без chatcore
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── синхронизация VOICE_BY_KEY ↔ DEFAULT_PERSONAS ────────────────────────────

def test_voice_by_key_covers_all_default_personas():
    """Каждая персона DEFAULT_PERSONAS должна быть в VOICE_BY_KEY."""
    from scripts.roundtable import DEFAULT_PERSONAS
    missing = [k for k in DEFAULT_PERSONAS if k not in table_tts.VOICE_BY_KEY]
    assert not missing, f"Не покрыты голосом: {missing}"


# ── clean_for_tts ─────────────────────────────────────────────────────────────

def test_clean_strips_markdown():
    assert table_tts.clean_for_tts("*жирный* и _курсив_") == "жирный и курсив"


def test_clean_strips_backticks():
    assert "`" not in table_tts.clean_for_tts("`код`")


def test_clean_strips_emoji():
    result = table_tts.clean_for_tts("Привет 🙂 мир")
    assert "🙂" not in result
    assert "Привет" in result


def test_clean_converts_number_sign():
    assert "номер 3" in table_tts.clean_for_tts("Обращаюсь к №3")


def test_clean_strips_number_sign_with_space():
    assert "номер 7" in table_tts.clean_for_tts("Ответил № 7")


def test_clean_plain_text_unchanged():
    text = "Всё просто и понятно."
    assert table_tts.clean_for_tts(text) == text


# ── healthz ───────────────────────────────────────────────────────────────────

def test_healthz_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("table_tts.httpx.get", return_value=mock_resp) as m:
        assert table_tts.healthz("http://127.0.0.1:8902") is True
        m.assert_called_once_with("http://127.0.0.1:8902/healthz", timeout=5)


def test_healthz_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("table_tts.httpx.get", return_value=mock_resp):
        assert table_tts.healthz("http://127.0.0.1:8902") is False


def test_healthz_exception():
    with patch("table_tts.httpx.get", side_effect=Exception("conn refused")):
        assert table_tts.healthz("http://127.0.0.1:8902") is False


# ── synthesize_ogg ────────────────────────────────────────────────────────────

_FAKE_WAV = b"RIFF....WAVEfmt "
_FAKE_OGG = b"OggS...."


def _make_http_ok(wav: bytes = _FAKE_WAV):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = wav
    return resp


def _make_ffmpeg_ok(ogg: bytes = _FAKE_OGG):
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = ogg
    return proc


def test_synthesize_ogg_happy_path():
    with patch("table_tts.httpx.post", return_value=_make_http_ok()) as mhttp, \
         patch("table_tts.subprocess.run", return_value=_make_ffmpeg_ok()):
        result = table_tts.synthesize_ogg("Проверка.", "sigma", "http://x", "tok")
        assert result == _FAKE_OGG
        # speaker должен быть table-sigma
        call_json = mhttp.call_args.kwargs.get("json") or mhttp.call_args[1].get("json", {})
        assert call_json["speaker"] == "table-sigma"
        assert call_json["text"] == "Проверка."


def test_synthesize_ogg_mannix_uses_edward():
    with patch("table_tts.httpx.post", return_value=_make_http_ok()) as mhttp, \
         patch("table_tts.subprocess.run", return_value=_make_ffmpeg_ok()):
        table_tts.synthesize_ogg("Текст.", "mannix", "http://x", "tok")
        call_json = mhttp.call_args.kwargs.get("json") or mhttp.call_args[1].get("json", {})
        assert call_json["speaker"] == "Эдвард"


def test_synthesize_ogg_unknown_key_returns_none():
    result = table_tts.synthesize_ogg("Текст.", "nonexistent", "http://x", "tok")
    assert result is None


def test_synthesize_ogg_empty_text_returns_none():
    result = table_tts.synthesize_ogg("", "sigma", "http://x", "tok")
    assert result is None


def test_synthesize_ogg_empty_after_clean_returns_none():
    # текст из одних звёздочек и эмодзи
    result = table_tts.synthesize_ogg("*** 🙂 ***", "sigma", "http://x", "tok")
    assert result is None


def test_synthesize_ogg_http_non_200_returns_none():
    resp = MagicMock()
    resp.status_code = 503
    resp.content = b""
    with patch("table_tts.httpx.post", return_value=resp):
        result = table_tts.synthesize_ogg("Текст.", "sigma", "http://x", "tok")
        assert result is None


def test_synthesize_ogg_http_empty_body_returns_none():
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b""
    with patch("table_tts.httpx.post", return_value=resp):
        result = table_tts.synthesize_ogg("Текст.", "sigma", "http://x", "tok")
        assert result is None


def test_synthesize_ogg_http_exception_returns_none():
    with patch("table_tts.httpx.post", side_effect=Exception("timeout")):
        result = table_tts.synthesize_ogg("Текст.", "sigma", "http://x", "tok")
        assert result is None


def test_synthesize_ogg_ffmpeg_nonzero_returns_none():
    proc = MagicMock()
    proc.returncode = 1
    proc.stdout = b""
    with patch("table_tts.httpx.post", return_value=_make_http_ok()), \
         patch("table_tts.subprocess.run", return_value=proc):
        result = table_tts.synthesize_ogg("Текст.", "sigma", "http://x", "tok")
        assert result is None


def test_synthesize_ogg_ffmpeg_exception_returns_none():
    with patch("table_tts.httpx.post", return_value=_make_http_ok()), \
         patch("table_tts.subprocess.run", side_effect=Exception("ffmpeg not found")):
        result = table_tts.synthesize_ogg("Текст.", "sigma", "http://x", "tok")
        assert result is None


def test_synthesize_ogg_markdown_cleaned_before_send():
    """clean_for_tts вызывается: text с markdown уходит на сервис без звёздочек."""
    with patch("table_tts.httpx.post", return_value=_make_http_ok()) as mhttp, \
         patch("table_tts.subprocess.run", return_value=_make_ffmpeg_ok()):
        table_tts.synthesize_ogg("*жирный* текст", "sigma", "http://x", "tok")
        call_json = mhttp.call_args.kwargs.get("json") or mhttp.call_args[1].get("json", {})
        assert "*" not in call_json["text"]
        assert "жирный текст" in call_json["text"]
