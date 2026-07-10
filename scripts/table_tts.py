"""Озвучка реплик круглого стола через OmniVoice (туннель 127.0.0.1:8902)."""
from __future__ import annotations

import queue
import re
import subprocess
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


class TTSWorker:
    """Фоновый TTS-конвейер: очередь (text, key, deliver) → synth → send.

    Один поток — голосовые уходят строго в порядке постановки. deliver=False
    (прогрев) — синтез выполняется, результат отбрасывается.
    """

    def __init__(self, synth, send):
        self._synth = synth   # (text, key) -> bytes | None
        self._send = send     # (ogg: bytes) -> None
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def put(self, text: str, key: str, deliver: bool = True) -> None:
        self._q.put((text, key, deliver))

    def close(self) -> None:
        """Дослать sentinel; поток завершится, доработав очередь."""
        self._q.put(None)

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            text, key, deliver = item
            ogg = self._synth(text, key)
            if ogg and deliver:
                self._send(ogg)
