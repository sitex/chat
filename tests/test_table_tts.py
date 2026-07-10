"""Unit-тесты для scripts/table_tts.py."""
from __future__ import annotations

import sys
import time as _time
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


# ── concat_ogg ───────────────────────────────────────────────────────────────


def test_concat_ogg_single_passthrough():
    """Один файл — возвращается без склейки."""
    data = b"OggS\x00fake"
    assert table_tts.concat_ogg([data]) is data


def test_concat_ogg_empty_returns_none():
    assert table_tts.concat_ogg([]) is None


def test_concat_ogg_multiple_calls_ffmpeg(tmp_path):
    """Несколько файлов → ffmpeg concat → возвращает вывод."""
    fake_combined = b"OggS\x00combined"
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = fake_combined
    with patch("table_tts.subprocess.run", return_value=proc) as mrun:
        result = table_tts.concat_ogg([b"OggS\x00a", b"OggS\x00b"])
    assert result == fake_combined
    cmd = mrun.call_args[0][0]
    assert "concat" in cmd


# ── TTSWorker ─────────────────────────────────────────────────────────────────


def _slow_synth(delay: float = 0.05):
    """Фейковый synth с задержкой — для проверки порядка."""
    def synth(text: str, key: str) -> bytes:
        _time.sleep(delay)
        return text.encode()
    return synth


def _collect_send() -> tuple[list, callable]:
    received: list = []
    def send(ogg: bytes) -> None:
        received.append(ogg)
    return received, send


def test_tts_worker_end_round_sends_combined():
    """put x3 + end_round → send вызван один раз (concat)."""
    received, send = _collect_send()

    def synth(text: str, key: str) -> bytes:
        return text.encode()

    with patch("table_tts.concat_ogg", side_effect=lambda oggs: b"".join(oggs)) as mc:
        w = table_tts.TTSWorker(synth=synth, send=send)
        w.put("А", "sigma")
        w.put("Б", "sigma")
        w.put("В", "sigma")
        w.end_round()
        w.close()
        w.join(timeout=5)
    assert len(received) == 1
    mc.assert_called_once()
    args = mc.call_args[0][0]
    assert args == [b"\xd0\x90", b"\xd0\x91", b"\xd0\x92"]


def test_tts_worker_two_rounds_two_sends():
    """Два end_round → два send-вызова."""
    received, send = _collect_send()

    def synth(text: str, key: str) -> bytes:
        return text.encode()

    with patch("table_tts.concat_ogg", side_effect=lambda oggs: b"".join(oggs)):
        w = table_tts.TTSWorker(synth=synth, send=send)
        w.put("Р1А", "sigma")
        w.end_round()
        w.put("Р2А", "sigma")
        w.end_round()
        w.close()
        w.join(timeout=5)
    assert len(received) == 2


def test_tts_worker_deliver_false_not_accumulated():
    """deliver=False (прогрев): synth вызван, в буфер не попадает."""
    synth_calls: list = []

    def synth(text: str, key: str) -> bytes:
        synth_calls.append(text)
        return text.encode()

    received, send = _collect_send()
    with patch("table_tts.concat_ogg", side_effect=lambda oggs: b"".join(oggs)):
        w = table_tts.TTSWorker(synth=synth, send=send)
        w.put("прогрев", "mentalist", deliver=False)
        w.end_round()
        w.close()
        w.join(timeout=5)
    assert synth_calls == ["прогрев"]
    assert received == []


def test_tts_worker_synth_none_skipped_in_round():
    """synth → None не попадает в буфер; остальные склеиваются."""
    call_count = [0]

    def synth(text: str, key: str):
        call_count[0] += 1
        return None if text == "пустой" else text.encode()

    received, send = _collect_send()
    with patch("table_tts.concat_ogg", side_effect=lambda oggs: b"".join(oggs)):
        w = table_tts.TTSWorker(synth=synth, send=send)
        w.put("пустой", "sigma")
        w.put("живой", "sigma")
        w.end_round()
        w.close()
        w.join(timeout=5)
    assert call_count[0] == 2
    assert len(received) == 1


def test_tts_worker_close_without_end_round_no_send():
    """close() без end_round — накопленные OGG отбрасываются, send не вызван."""
    received, send = _collect_send()
    w = table_tts.TTSWorker(synth=_slow_synth(0.01), send=send)
    for i in range(3):
        w.put(str(i), "sigma")
    w.close()
    w.join(timeout=5)
    assert received == []
