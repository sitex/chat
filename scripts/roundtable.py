#!/usr/bin/env python3
"""Круглый стол персон chatcore.

Берёт тему и персон из семейства (../chat-*/data/persona.json) и прогоняет
обсуждение: каждая персона высказывается в своём стиле, видя все предыдущие
реплики, — соглашается, спорит, поддевает других. Участники пронумерованы
(1–11), к ним можно обращаться по номеру.

Порядок внутри круга живой: после каждой реплики выбирается следующий оратор —
тот, к кому обратились, или (по решению LLM-режиссёра) тот, кому явно есть что
ответить. Каждый высказывается ровно один раз за круг. --sequential возвращает
фиксированный порядок.

Движок — общий LLM-каскад chatcore.llm (backend из окружения: cliproxy →
grok → claude-cli → claude → ollama). Персональной инфраструктуры (config,
БД) не требует.

Режимы:
- обычный: печатает реплики в терминал, --rounds кругов, конец.
- --jsonl: каждое событие — JSON-строка в stdout (для manager-bot).
- --interactive: после каждого круга ждёт команду на stdin:
    MORE            — ещё круг
    STOP            — завершить стол
    <любой текст>   — реплика Ведущего, персоны реагируют новым кругом
  Тишина STDIN_TIMEOUT (600с) — стол закрывается сам.

Примеры:
    python scripts/roundtable.py
    python scripts/roundtable.py --topic "Свобода воли — иллюзия?" --rounds 2
    python scripts/roundtable.py --personas mentalist,acharya-das,sigma
    python scripts/roundtable.py --jsonl --interactive
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path

# chatcore установлен как пакет (pip install -e .), но на всякий случай
# добавим корень репо в путь, чтобы скрипт работал и без установки.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chatcore import llm

# Каталог с соседними ботами: <repo>/.. содержит chat-mentalist и т.д.
SIBLINGS = Path(__file__).resolve().parent.parent.parent

# Порядок = постоянные номера участников (1–11). Подобран так, чтобы скептик,
# духовные учителя, коучи и психолог сталкивались лбами.
DEFAULT_PERSONAS = [
    "mentalist",      # 1. Patrick Jane — скептик, «экстрасенсов не бывает»
    "acharya-das",    # 2. Ачарья Дас — ведический учитель, карма и Гита
    "sigma",          # 3. Dan — sigma-майндсет, «ты сам создаёшь себя»
    "socialself",     # 4. Мария — психолог по соцнавыкам
    "vishvanath",     # 5. Шри Вишванатх — духовный наставник
    "marni",          # 6. Marni — dating-коуч, прагматик
    "ifs",            # 7. IFS Guide — внутренние части, самолидерство
    "lukehawkins",    # 8. Luke Hawkins — трансформационный коуч
    "jacobs",         # 9. Lee Jacobs — «ненаписанная система»
    "mannix",         # 10. Edward Mannix — Compassion Key, клиринг
    "davidkey",       # 11. David Key — НЛП и гипнотерапия
]

# Отображаемые имена — фолбэк, если в persona.json name пустой.
NAME_FALLBACK = {
    "vishvanath": "Шри Вишванатх",
    "ifs": "Ричард Шварц",
}

# Явные переопределения имени для круглого стола (приоритет над persona.json).
NAME_OVERRIDE = {
    "ifs": "Ричард Шварц",
}

DEFAULT_TOPIC = "Судьба предопределена, или мы сами создаём свою жизнь?"
HOST_NAME = "Ведущий"
STDIN_TIMEOUT = 600  # сек тишины в --interactive до автозавершения
CONTEXT_LIMIT = 26   # сколько последних реплик персона видит в транскрипте

# Бэкенд LLM-режиссёра (выбор следующего оратора). Пусто → общий бэкенд.
# Режиссёр — не персона: инжект промпта Claude Code на cliproxy не вредит.
DIRECTOR_BACKEND = os.environ.get("DIRECTOR_BACKEND", "")

JSONL = False


def emit(event: dict) -> None:
    """Событие для manager-bot (--jsonl) — одна JSON-строка в stdout."""
    if JSONL:
        print(json.dumps(event, ensure_ascii=False), flush=True)


def say(text: str) -> None:
    """Человекочитаемый вывод: stdout в обычном режиме, stderr в --jsonl."""
    print(text, file=sys.stderr if JSONL else sys.stdout, flush=True)


def _section(block, lang: str = "ru") -> str:
    """Текст секции persona.json на нужном языке (с фолбэком).

    Блок бывает строкой, списком или dict {ru/en: str|list}.
    """
    if isinstance(block, str):
        return block
    if isinstance(block, list):
        return "\n".join(f"- {item}" for item in block)
    val = block.get(lang) or block.get("ru") or block.get("en")
    if isinstance(val, list):
        return "\n".join(f"- {item}" for item in val)
    return str(val)


def load_persona(key: str, num: int) -> dict:
    """Загрузить persona.json соседнего бота chat-<key>."""
    path = SIBLINGS / f"chat-{key}" / "data" / "persona.json"
    if not path.exists():
        raise FileNotFoundError(f"нет персоны: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    name = NAME_OVERRIDE.get(key) or data.get("name") or NAME_FALLBACK.get(key) or key
    return {"key": key, "num": num, "name": name, "data": data}


def roster(personas: list[dict]) -> str:
    """Нумерованный список участников."""
    return "\n".join(f"{p['num']}. {p['name']}" for p in personas)


def build_persona_prompt(persona: dict, personas: list[dict], topic: str) -> str:
    """Компактный system prompt: кто ты + правила круглого стола."""
    d = persona["data"]
    return "\n".join([
        _section(d["identity"]),
        "",
        "Характер:",
        _section(d["traits"]),
        "",
        "Стиль речи:",
        _section(d["speech_style"]),
        "",
        f"Ты — участник №{persona['num']} круглого стола ярких, непохожих "
        f"персонажей. Тема: «{topic}».",
        "Участники (по номерам):",
        roster(personas),
        "",
        "Правила:",
        "- Отвечай строго в своём характере и стиле, от первого лица.",
        "- Коротко: строго 1–2 предложения, не больше. Не пересказывай чужие слова — реагируй: "
        "соглашайся, спорь, поддевай.",
        "- Если отвечаешь кому-то конкретному — обращайся по имени или номеру "
        "(«№3»). Обращение к твоему номеру или имени — это вопрос тебе.",
        f"- Реплики «{HOST_NAME}» — от модератора стола; на его вопросы и "
        "вбросы отвечай в первую очередь.",
        "- Только по-русски. Верни ТОЛЬКО свою реплику, без пометок и имени "
        "в начале.",
    ])


def build_turn_message(topic: str, transcript: list[tuple[str, str]], me: str) -> str:
    """Сообщение-«очередь»: тема + сказанное + приглашение высказаться."""
    lines = [f"Тема обсуждения: «{topic}»", ""]
    if transcript:
        tail = transcript[-CONTEXT_LIMIT:]
        if len(transcript) > len(tail):
            lines.append(f"(ранее прозвучало ещё {len(transcript) - len(tail)} реплик)")
        lines.append("Что уже сказали участники:")
        for name, text in tail:
            lines.append(f"{name}: {text}")
        lines.append("")
        lines.append(f"Сейчас твоя очередь, {me}. Дай свою реплику — строго 1–2 предложения.")
    else:
        lines.append(f"Ты открываешь обсуждение, {me}. Дай свою первую реплику по теме — строго 1–2 предложения.")
    return "\n".join(lines)


# ── stdin-команды (--interactive) ────────────────────────────────────────────

_stdin_q: queue.Queue[str] = queue.Queue()


def _stdin_pump() -> None:
    for line in sys.stdin:
        _stdin_q.put(line.strip())


async def next_command(timeout: float) -> str | None:
    """Ждать команду со stdin до timeout; None = тишина/EOF → завершаемся."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            cmd = _stdin_q.get_nowait()
            if cmd:
                return cmd
        except queue.Empty:
            await asyncio.sleep(0.5)
    return None


# ── выбор следующего оратора ─────────────────────────────────────────────────

DIRECTOR_PROMPT = (
    "Ты — режиссёр круглого стола. По последним репликам выбери, кто из ещё "
    "не высказавшихся участников сейчас ответит уместнее всего: к кому "
    "обратились, кого задели, у кого явно есть что возразить или добавить. "
    "Ответь ТОЛЬКО номером участника, без пояснений."
)


def _addressed(text: str, remaining: list[dict]) -> dict | None:
    """Если в реплике прямо обратились к оставшемуся участнику — он и отвечает."""
    for p in remaining:
        if f"№{p['num']}" in text or re.search(rf"\b{re.escape(p['name'])}\b", text):
            return p
    return None


async def pick_next(
    remaining: list[dict], transcript: list[tuple[str, str]], topic: str
) -> dict:
    """Кто из оставшихся говорит следующим: прямое обращение → он; иначе LLM."""
    if len(remaining) == 1 or not transcript:
        return remaining[0]
    hit = _addressed(transcript[-1][1], remaining)
    if hit:
        return hit
    lines = [f"Тема: «{topic}»", "", "Последние реплики:"]
    for name, text in transcript[-6:]:
        lines.append(f"{name}: {text}")
    lines.append("")
    lines.append("Ещё не высказались в этом круге:")
    for p in remaining:
        lines.append(f"{p['num']}. {p['name']}")
    lines.append("")
    lines.append("Кто отвечает следующим? Только номер.")
    try:
        out = await llm.generate(
            DIRECTOR_PROMPT,
            [{"role": "user", "content": "\n".join(lines)}],
            backend=DIRECTOR_BACKEND or None,
        )
        m = re.search(r"\d+", out)
        if m:
            num = int(m.group())
            for p in remaining:
                if p["num"] == num:
                    return p
    except Exception:  # noqa: BLE001 — сломался режиссёр → идём по порядку
        pass
    return remaining[0]


# ── прогон ───────────────────────────────────────────────────────────────────

async def run_round(
    personas: list[dict],
    prompts: dict[str, str],
    topic: str,
    transcript: list[tuple[str, str]],
    sequential: bool = False,
) -> None:
    remaining = list(personas)
    while remaining:
        p = remaining.pop(0) if sequential else None
        if p is None:
            p = await pick_next(remaining, transcript, topic)
            remaining.remove(p)
        name = p["name"]
        user_msg = build_turn_message(topic, transcript, name)
        try:
            reply = await llm.generate(prompts[p["key"]], [{"role": "user", "content": user_msg}])
        except Exception as exc:  # noqa: BLE001 — одна упавшая реплика не рушит стол
            emit({"event": "error", "name": name, "text": str(exc) or exc.__class__.__name__})
            say(f"! {name}: пропущено ({exc.__class__.__name__})")
            continue
        reply = reply.strip()
        transcript.append((name, reply))
        emit({"event": "reply", "num": p["num"], "key": p["key"], "name": name, "text": reply})
        say(f"\n\033[1m{name}:\033[0m {reply}")


async def run(
    personas: list[dict], topic: str, rounds: int, interactive: bool,
    sequential: bool = False,
) -> list[tuple[str, str]]:
    prompts = {p["key"]: build_persona_prompt(p, personas, topic) for p in personas}
    transcript: list[tuple[str, str]] = []
    emit({
        "event": "start",
        "topic": topic,
        "backend": llm.active_backend(),
        "participants": [{"num": p["num"], "name": p["name"]} for p in personas],
    })

    if interactive:
        threading.Thread(target=_stdin_pump, daemon=True).start()
        round_no = 0
        while True:
            round_no += 1
            await run_round(personas, prompts, topic, transcript, sequential)
            emit({"event": "round_done", "round": round_no})
            cmd = await next_command(STDIN_TIMEOUT)
            if cmd is None or cmd.upper() == "STOP":
                break
            if cmd.upper() == "MORE":
                continue
            # любой другой текст — реплика Ведущего, реагируем новым кругом
            transcript.append((HOST_NAME, cmd))
            emit({"event": "host", "text": cmd})
    else:
        for r in range(1, rounds + 1):
            if rounds > 1:
                say(f"\n{'=' * 60}\n  РАУНД {r}\n{'=' * 60}")
            await run_round(personas, prompts, topic, transcript, sequential)

    emit({"event": "done", "replies": len(transcript)})
    return transcript


def to_markdown(topic: str, transcript: list[tuple[str, str]], backend: str) -> str:
    out = [f"# Круглый стол: {topic}", "", f"_Движок: {backend}_", ""]
    for name, text in transcript:
        out.append(f"**{name}:** {text}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    global JSONL
    ap = argparse.ArgumentParser(description="Круглый стол персон chatcore")
    ap.add_argument("--topic", default=DEFAULT_TOPIC, help="тема обсуждения")
    ap.add_argument("--rounds", type=int, default=1, help="сколько кругов (без --interactive)")
    ap.add_argument(
        "--personas",
        default=",".join(DEFAULT_PERSONAS),
        help="ключи через запятую (chat-<key>) или номера 1–11",
    )
    ap.add_argument("--jsonl", action="store_true", help="события JSON-строками в stdout")
    ap.add_argument("--interactive", action="store_true", help="команды через stdin после каждого круга")
    ap.add_argument("--sequential", action="store_true",
                    help="фиксированный порядок вместо выбора режиссёром")
    ap.add_argument("--out", help="сохранить транскрипт в markdown-файл")
    args = ap.parse_args()
    JSONL = args.jsonl

    personas = []
    for token in (t.strip() for t in args.personas.split(",") if t.strip()):
        # номер участника (1–11) или ключ
        if token.isdigit() and not 1 <= int(token) <= len(DEFAULT_PERSONAS):
            say(f"! нет участника №{token} (есть 1–{len(DEFAULT_PERSONAS)})")
            continue
        key = DEFAULT_PERSONAS[int(token) - 1] if token.isdigit() else token
        num = DEFAULT_PERSONAS.index(key) + 1 if key in DEFAULT_PERSONAS else len(personas) + 1
        try:
            personas.append(load_persona(key, num))
        except FileNotFoundError as exc:
            say(f"! {exc}")
    if len(personas) < 2:
        sys.exit("нужно минимум 2 персоны")

    backend = llm.active_backend()
    say(f"Тема: «{args.topic}»")
    say(f"Участники ({len(personas)}):\n{roster(personas)}")
    say(f"Backend: {backend} | interactive={args.interactive}")

    transcript = asyncio.run(
        run(personas, args.topic, args.rounds, args.interactive, args.sequential))

    if args.out:
        Path(args.out).write_text(to_markdown(args.topic, transcript, backend), encoding="utf-8")
        say(f"\n→ сохранено: {args.out}")


if __name__ == "__main__":
    main()
