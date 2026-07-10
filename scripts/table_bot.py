#!/usr/bin/env python3
"""table-bot — Telegram-демон круглого стола персон chatcore (VPS).

Отдельный бот только для /table: запускает scripts/roundtable.py
(--jsonl --interactive) subprocess'ом и стримит реплики персон в чат
отдельными сообщениями. Управление: кнопки «Ещё круг»/«Завершить»,
обычный текст при активном столе — реплика Ведущего, /stop — завершить.

Конфиг — ~/.table-bot.env (chmod 600):
    BOT_TOKEN=123456:ABC-...
    ALLOW_FROM=343350188            # id через запятую
    CLAUDE_CLI_BIN=/usr/bin/claude  # опционально

Запуск — systemd --user юнит scripts/systemd/table-bot.service.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import table_tts

HOME = Path.home()
ENV_FILE = HOME / ".table-bot.env"
OFFSET_FILE = HOME / ".table-bot.offset"
ROUNDTABLE_DIR = Path(__file__).resolve().parent.parent
ROUNDTABLE_SCRIPT = Path(__file__).resolve().parent / "roundtable.py"


def _env() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


CONF = _env()
API = f"https://api.telegram.org/bot{CONF['BOT_TOKEN']}"
ALLOW = {s.strip() for s in CONF.get("ALLOW_FROM", "").split(",") if s.strip()}
CLAUDE_CLI_BIN = CONF.get("CLAUDE_CLI_BIN", "/usr/bin/claude")
TTS_URL = CONF.get("TTS_URL", "http://127.0.0.1:8902")
TTS_TOKEN = CONF.get("TTS_TOKEN", "")


def api(method: str, **kwargs) -> dict:
    payload = {k: v for k, v in kwargs.items() if v is not None}
    try:
        r = httpx.post(f"{API}/{method}", json=payload, timeout=70)
        return r.json()
    except httpx.HTTPError:
        return {"ok": False}


def api_voice(chat: int, ogg: bytes) -> dict:
    try:
        r = httpx.post(f"{API}/sendVoice", data={"chat_id": chat},
                       files={"voice": ("reply.ogg", ogg, "audio/ogg")},
                       timeout=70)
        return r.json()
    except httpx.HTTPError:
        return {"ok": False}


# ── круглый стол ─────────────────────────────────────────────────────────────

# state: None | {"chat": int, "proc": Popen, "thread": Thread}
_table: dict | None = None
_table_lock = threading.Lock()

PERSONA_COUNT = 11  # участников в DEFAULT_PERSONAS движка


def parse_table_args(rest: str) -> tuple[str | None, str, str | None]:
    """'1,3,5: тема' → (personas, topic, error).

    Составом считаются только числа/запятые перед первым двоеточием —
    тема с двоеточием внутри не ломается.
    """
    head, sep, tail = rest.partition(":")
    if not sep or not head.strip() or head.strip(" ,0123456789"):
        return None, rest, None
    nums = [n for n in (t.strip() for t in head.split(",")) if n]
    bad = [n for n in nums if not 1 <= int(n) <= PERSONA_COUNT]
    if bad:
        return None, "", f"нет участника №{', №'.join(bad)} (есть 1–{PERSONA_COUNT})"
    uniq = list(dict.fromkeys(nums))
    if len(uniq) < 2:
        return None, "", "нужно минимум 2 участника"
    if not tail.strip():
        return None, "", "после списка участников укажите тему"
    return ",".join(uniq), tail.strip(), None

_TABLE_KB = {"inline_keyboard": [[
    {"text": "▶️ Ещё круг", "callback_data": "table:more"},
    {"text": "⏹ Завершить", "callback_data": "table:stop"},
]]}


def table_active(chat: int | None = None) -> bool:
    t = _table
    if t is None or t["proc"].poll() is not None:
        return False
    return chat is None or t["chat"] == chat


def start_table(chat: int, topic: str, personas: str | None = None) -> None:
    global _table
    with _table_lock:
        if table_active():
            api("sendMessage", chat_id=chat,
                text="Стол уже идёт. /stop — завершить его сначала.")
            return
        env = dict(os.environ,
                   LLM_BACKEND="claude-cli",
                   CLAUDE_CLI_BIN=CLAUDE_CLI_BIN,
                   CLAUDE_CLI_TIMEOUT="90",
                   LLM_OVERALL_TIMEOUT="120")
        proc = subprocess.Popen(
            [sys.executable, str(ROUNDTABLE_SCRIPT), "--jsonl", "--interactive",
             "--topic", topic]
            + (["--personas", personas] if personas else []),
            cwd=str(ROUNDTABLE_DIR), env=env, text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        tts_ok = bool(TTS_TOKEN) and table_tts.healthz(TTS_URL)
        th = threading.Thread(target=_table_reader, args=(chat, proc), daemon=True)
        _table = {"chat": chat, "proc": proc, "thread": th, "tts": tts_ok}
        th.start()


def table_send(text: str) -> bool:
    """Команда в stdin стола (MORE/STOP/реплика Ведущего)."""
    t = _table
    if t is None or t["proc"].poll() is not None:
        return False
    try:
        t["proc"].stdin.write(text + "\n")
        t["proc"].stdin.flush()
        return True
    except Exception:
        return False


def stop_table() -> None:
    global _table
    t = _table
    if t is None:
        return
    if not table_send("STOP"):
        t["proc"].kill()
    _table = None


def _table_say(chat: int, text: str, reply_markup: dict | None = None) -> None:
    r = api("sendMessage", chat_id=chat, text=text,
            parse_mode="Markdown", reply_markup=reply_markup)
    if not r.get("ok"):  # реплика сломала Markdown — шлём plain
        api("sendMessage", chat_id=chat, text=text, reply_markup=reply_markup)


def _table_reader(chat: int, proc: subprocess.Popen) -> None:
    global _table
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("event")
        if kind == "start":
            names = "\n".join(f"{p['num']}. {p['name']}"
                              for p in ev["participants"])
            _table_say(chat, f"🎙 *Круглый стол*: {ev['topic']}\n\n"
                             f"Участники:\n{names}\n\nПервый круг…")
        elif kind == "reply":
            _table_say(chat, f"*{ev['name']}:* {ev['text']}")
            if _table and _table.get("tts") and ev.get("key"):
                ogg = table_tts.synthesize_ogg(ev["text"], ev["key"], TTS_URL, TTS_TOKEN)
                if ogg:
                    api_voice(chat, ogg)
        elif kind == "error":
            _table_say(chat, f"⚠️ {ev['name']}: реплика выпала")
        elif kind == "round_done":
            _table_say(chat, f"Круг {ev['round']} завершён. Ещё круг, "
                             f"реплика Ведущего текстом — или завершаем?",
                       reply_markup=_TABLE_KB)
        elif kind == "done":
            _table_say(chat, f"🏁 Стол закрыт ({ev['replies']} реплик).")
    proc.wait()
    with _table_lock:
        if _table is not None and _table["proc"] is proc:
            _table = None


# ── обработка обновлений ─────────────────────────────────────────────────────

HELP = ("🎙 Бот круглого стола персон.\n\n"
        "/table <тема> — запустить стол (все 11 участников)\n"
        "/table 1,3,5: <тема> — стол выбранных участников (номера 1–11)\n"
        "/stop — завершить стол\n"
        "Обычный текст при активном столе — реплика Ведущего.")


def handle(update: dict) -> None:
    cq = update.get("callback_query")
    if cq:
        if str(cq.get("from", {}).get("id")) not in ALLOW:
            api("answerCallbackQuery", callback_query_id=cq["id"])
            return
        chat = cq["message"]["chat"]["id"]
        data = cq.get("data", "")
        if data == "table:more":
            api("answerCallbackQuery", callback_query_id=cq["id"], text="Ещё круг")
            table_send("MORE") or api("sendMessage", chat_id=chat,
                                      text="Стол уже закрыт.")
        elif data == "table:stop":
            api("answerCallbackQuery", callback_query_id=cq["id"], text="Завершаю")
            stop_table()
        else:
            api("answerCallbackQuery", callback_query_id=cq["id"])
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg["chat"]["id"]
    if str(msg.get("from", {}).get("id")) not in ALLOW:
        api("sendMessage", chat_id=chat, text="⛔ Доступ только для владельца.")
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text.startswith("/table"):
        rest = text[len("/table"):].strip()
        if not rest:
            api("sendMessage", chat_id=chat,
                text="Формат: /table <тема> или /table 1,3,5: <тема>. "
                     "Пример: /table Свобода воли — иллюзия?")
            return
        personas, topic, err = parse_table_args(rest)
        if err:
            api("sendMessage", chat_id=chat, text=f"⚠️ {err}")
            return
        start_table(chat, topic, personas)
        return
    if text == "/stop":
        if table_active():
            stop_table()
        else:
            api("sendMessage", chat_id=chat, text="Активного стола нет.")
        return
    if text.startswith("/"):
        api("sendMessage", chat_id=chat, text=HELP)
        return
    if table_active(chat):
        if table_send(text):
            api("sendMessage", chat_id=chat, text="🎙 Передал Ведущим. Новый круг…")
        else:
            api("sendMessage", chat_id=chat, text="Стол уже закрыт.")
        return
    api("sendMessage", chat_id=chat, text=HELP)


# ── главный цикл ─────────────────────────────────────────────────────────────

def load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def main() -> None:
    api("deleteWebhook")
    if not OFFSET_FILE.exists():  # первый старт — пропустить бэклог
        drained = api("getUpdates", offset=-1, timeout=0)
        ups = drained.get("result", []) if drained.get("ok") else []
        OFFSET_FILE.write_text(str((ups[-1]["update_id"] + 1) if ups else 0))
    offset = load_offset()
    print(f"table-bot: старт, offset={offset}", flush=True)
    while True:
        try:
            resp = api("getUpdates", offset=offset, timeout=30, limit=10)
            if not resp.get("ok"):
                time.sleep(3)
                continue
            for u in resp["result"]:
                offset = u["update_id"] + 1
                OFFSET_FILE.write_text(str(offset))
                handle(u)
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    main()
