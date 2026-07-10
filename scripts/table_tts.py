"""Озвучка реплик круглого стола через OmniVoice (туннель 127.0.0.1:8902)."""
from __future__ import annotations

import concurrent.futures
import os
import queue
import re
import subprocess
import tempfile
import threading

import httpx

# Маппинг ключ персоны → speaker-имя OmniVoice (ALLOWED_SPEAKERS сервиса)
VOICE_BY_KEY: dict[str, str] = {
    "mentalist":   "table-mentalist",
    "acharya-das": "table-acharya-das",
    "sigma":       "table-sigma",
    "socialself":  "table-socialself",
    "vishvanath":  "table-vishvanath",
    "marni":       "table-marni",
    "ifs":         "table-ifs",
    "lukehawkins": "table-lukehawkins",
    "jacobs":      "table-jacobs",
    "mannix":      "Эдвард",
    "davidkey":    "table-davidkey",
}

# Markdown/emoji-мусор, который плохо читается вслух
_MD_RE = re.compile(r"[*_`~]")
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
_NUM_RE = re.compile(r"№\s*(\d+)")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")

# Сколько предложений от реплики озвучивать (0 = без ограничений).
TTS_MAX_SENTENCES = 3


def clean_for_tts(text: str) -> str:
    """Markdown-звёздочки, подчёркивания, эмодзи, «№3» → «номер 3» и т.п."""
    text = _MD_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _NUM_RE.sub(r"номер \1", text)
    return text.strip()


def healthz(url: str, timeout: float = 5) -> bool:
    """GET {url}/healthz → ok. Ошибка/таймаут → False."""
    try:
        r = httpx.get(f"{url}/healthz", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def synthesize_ogg(text: str, key: str, url: str, token: str) -> bytes | None:
    """POST /synthesize → WAV; ffmpeg → OGG-байты. Любая ошибка → None."""
    speaker = VOICE_BY_KEY.get(key)
    if not speaker:
        return None
    cleaned = clean_for_tts(text)
    if not cleaned:
        return None
    if TTS_MAX_SENTENCES:
        parts = _SENT_SPLIT.split(cleaned)
        cleaned = " ".join(parts[:TTS_MAX_SENTENCES])
    if not cleaned:
        return None
    try:
        r = httpx.post(
            f"{url}/synthesize",
            json={"text": cleaned, "speaker": speaker},
            headers={"X-TTS-Auth": token},
            timeout=180,  # холодный рестарт модели до минуты
        )
        if r.status_code != 200:
            return None
        wav_bytes = r.content
        if not wav_bytes:
            return None
    except Exception:
        return None

    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", "pipe:0",
             "-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB",
             "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
             "-loglevel", "error"],
            input=wav_bytes,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        return proc.stdout
    except Exception:
        return None


def concat_ogg(oggs: list[bytes]) -> bytes | None:
    """Склеить список OGG/Opus файлов в один через ffmpeg concat."""
    if not oggs:
        return None
    if len(oggs) == 1:
        return oggs[0]
    tmpfiles: list[str] = []
    list_path = ""
    try:
        for ogg in oggs:
            f = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
            f.write(ogg)
            f.close()
            tmpfiles.append(f.name)
        lf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        lf.write("\n".join(f"file '{p}'" for p in tmpfiles))
        lf.close()
        list_path = lf.name
        proc = subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_path,
             "-c", "copy", "-f", "ogg", "pipe:1", "-loglevel", "error"],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        return proc.stdout
    except Exception:
        return None
    finally:
        for p in tmpfiles:
            try:
                os.unlink(p)
            except OSError:
                pass
        if list_path:
            try:
                os.unlink(list_path)
            except OSError:
                pass


class TTSWorker:
    """Фоновый TTS-конвейер: очередь реплик → параллельный synth → накопление → send.

    deliver=False (прогрев) — synth вызывается немедленно, результат отброшен.
    end_round() — синтезирует реплики раунда параллельно, добавляет OGG в общий буфер.
    send_all()  — склеивает накопленные раунды в один файл и шлёт; сбрасывает буфер.
    """

    _FLUSH = object()  # конец раунда: синтез + накопление
    _SEND  = object()  # отправить всё накопленное одним файлом

    def __init__(self, synth, send, max_workers: int = 4):
        self._synth = synth       # (text, key) -> bytes | None
        self._send = send         # (ogg: bytes) -> None
        self._max_workers = max_workers
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def put(self, text: str, key: str, deliver: bool = True) -> None:
        self._q.put((text, key, deliver))

    def end_round(self) -> None:
        """Сигнал конца раунда: синтез реплик параллельно, OGG → буфер раундов."""
        self._q.put(self._FLUSH)

    def send_all(self) -> None:
        """Склеить все накопленные раунды в один OGG и отправить."""
        self._q.put(self._SEND)

    def close(self) -> None:
        """Дослать None-sentinel; поток завершится, доработав очередь."""
        self._q.put(None)

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _synth_parallel(self, items: list[tuple[str, str]]) -> list[bytes]:
        """Синтез всех реплик параллельно; возвращает OGG в исходном порядке."""
        n = len(items)
        results: list[bytes | None] = [None] * n
        workers = min(n, self._max_workers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._synth, t, k): i for i, (t, k) in enumerate(items)}
            for fut in concurrent.futures.as_completed(futs):
                try:
                    results[futs[fut]] = fut.result()
                except Exception:
                    pass
        return [r for r in results if r]

    def _run(self) -> None:
        pending: list[tuple[str, str]] = []  # реплики текущего раунда
        combined: list[bytes] = []           # OGG-ы завершённых раундов
        while True:
            item = self._q.get()
            if item is None:
                return
            if item is self._FLUSH:
                if pending:
                    oggs = self._synth_parallel(pending)
                    pending = []
                    if oggs:
                        ogg = concat_ogg(oggs)
                        if ogg:
                            combined.append(ogg)
                continue
            if item is self._SEND:
                if combined:
                    final = concat_ogg(combined)
                    if final:
                        self._send(final)
                    combined = []
                continue
            text, key, deliver = item
            if deliver:
                pending.append((text, key))
            else:
                self._synth(text, key)  # прогрев: результат отброшен
