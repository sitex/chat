#!/usr/bin/env python3
"""Генерация и установка аватарки бота через ComfyUI (ERNIE) + BotFather (Telethon).

Зависимости (не входят в пакет chatcore):
    pip install telethon Pillow numpy

Использование:
    python scripts/gen_avatar.py --username @my_bot --prefix my_bot --prompt "Portrait of..."

Переменные окружения (опциональные переопределения путей):
    COMFY_URL      — адрес ComfyUI (по умолчанию http://127.0.0.1:8188)
    COMFY_OUTPUT   — папка с выходными файлами ComfyUI
    CHATS_DIR      — папка с .env и session.session
    AVATARS_DIR    — папка для сохранения аватарок
    BOTFATHER_ID   — числовой ID BotFather (по умолчанию 93372553)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient, events

COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
COMFY_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", "/home/rocky/projects/claude-images/ComfyUI/output"))
CHATS_DIR = Path(os.environ.get("CHATS_DIR", "/home/rocky/projects/chats"))
AVATARS_DIR = Path(os.environ.get("AVATARS_DIR", "/home/rocky/projects/chat/avatars"))
BOTFATHER_ID = int(os.environ.get("BOTFATHER_ID", "93372553"))

STEPS = 20


def _http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def build_ernie_workflow(prompt: str, width: int = 800, height: int = 800, seed: int | None = None) -> dict:
    if seed is None:
        seed = random.randint(0, 2**31)
    return {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": "ernie-image-turbo-UD-Q5_K_M.gguf"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "ernie-image-prompt-enhancer.safetensors", "type": "stable_diffusion"}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": prompt}},
        "4": {"class_type": "VAELoader",
              "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "5": {"class_type": "EmptyFlux2LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "Flux2Scheduler",
              "inputs": {"steps": STEPS, "width": width, "height": height}},
        "7": {"class_type": "BasicGuider",
              "inputs": {"model": ["1", 0], "conditioning": ["3", 0]}},
        "8": {"class_type": "RandomNoise",
              "inputs": {"noise_seed": seed}},
        "9": {"class_type": "KSamplerSelect",
              "inputs": {"sampler_name": "res_multistep"}},
        "10": {"class_type": "SamplerCustomAdvanced",
               "inputs": {
                   "noise": ["8", 0], "guider": ["7", 0],
                   "sampler": ["9", 0], "sigmas": ["6", 0],
                   "latent_image": ["5", 0],
               }},
        "11": {"class_type": "VAEDecode",
               "inputs": {"samples": ["10", 0], "vae": ["4", 0]}},
        "12": {"class_type": "SaveImage",
               "inputs": {"images": ["11", 0], "filename_prefix": "avatar"}},
    }


def check_image_quality(path: Path) -> bool:
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(path).convert("RGB")
        arr = np.array(img, dtype=float)
        std = arr.std()
        mean = arr.mean()
        print(f"  ✓ QC: mean={mean:.1f} std={std:.1f}")
        if std < 5:
            print("  ✗ QC FAIL: изображение однотонное (std < 5)")
            return False
        if path.stat().st_size < 50_000:
            print(f"  ✗ QC FAIL: файл слишком маленький ({path.stat().st_size} bytes)")
            return False
        return True
    except Exception as e:
        print(f"  ! QC error: {e}, пропускаем проверку")
        return True


def generate_image(prompt: str, prefix: str, max_retries: int = 3) -> Path | None:
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        seed = random.randint(0, 2**31)
        client_id = str(uuid.uuid4())
        workflow = build_ernie_workflow(prompt, seed=seed)

        print(f"  → Попытка {attempt}/{max_retries}, seed={seed}")
        resp = _http_post(f"{COMFY_URL}/prompt", {"prompt": workflow, "client_id": client_id})
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            print(f"  ✗ Не получен prompt_id: {resp}")
            continue

        for _ in range(120):  # до 4 мин
            time.sleep(2)
            history = _http_get(f"{COMFY_URL}/history/{prompt_id}")
            if prompt_id not in history:
                continue
            outputs = history[prompt_id].get("outputs", {})
            for node_output in outputs.values():
                for img in node_output.get("images", []):
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    src = COMFY_OUTPUT / subfolder / filename if subfolder else COMFY_OUTPUT / filename
                    dst = AVATARS_DIR / f"{prefix}_attempt{attempt}.png"
                    shutil.copy2(src, dst)
                    print(f"  ✓ Изображение: {dst}")
                    if check_image_quality(dst):
                        final = AVATARS_DIR / f"{prefix}.png"
                        shutil.copy2(dst, final)
                        return final
                    print("  ↻ Низкое качество, генерируем заново...")
            break
        else:
            print(f"  ✗ Таймаут попытки {attempt}")

    print(f"  ✗ Все попытки исчерпаны для {prefix}")
    return None


async def wait_botfather(client: TelegramClient, timeout: float = 15) -> str:
    future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    @client.on(events.NewMessage(from_users=BOTFATHER_ID))
    async def handler(event):
        if not future.done():
            future.set_result(event.raw_text or "")

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return ""
    finally:
        client.remove_event_handler(handler)


async def set_avatar(client: TelegramClient, username: str, image_path: Path) -> bool:
    print(f"  → Установка аватарки {username} через BotFather...")
    botfather = await client.get_entity(BOTFATHER_ID)

    await client.send_message(botfather, "/cancel")
    await asyncio.sleep(2)

    await client.send_message(botfather, "/setuserpic")
    r1 = await wait_botfather(client, timeout=10)
    print(f"    BotFather: {r1[:80]!r}")
    if not r1:
        return False

    await client.send_message(botfather, username)
    r2 = await wait_botfather(client, timeout=10)
    print(f"    BotFather: {r2[:80]!r}")
    if not r2:
        return False

    await client.send_file(botfather, str(image_path))
    r3 = await wait_botfather(client, timeout=15)
    print(f"    BotFather: {r3[:80]!r}")
    return "changed" in r3.lower() or "success" in r3.lower() or "set" in r3.lower() or "photo" in r3.lower()


async def main(username: str, prefix: str, prompt: str) -> None:
    creds = dotenv_values(str(CHATS_DIR / ".env"))
    api_id = int(creds["TELEGRAM_API_ID"])
    api_hash = creds["TELEGRAM_API_HASH"]
    session = str(CHATS_DIR / "session.session")

    print(f"\n=== {username} ===")
    print("Генерирую аватарку...")

    img_path = generate_image(prompt, prefix)
    if not img_path:
        print("  ✗ Не удалось сгенерировать аватарку")
        return

    print(f"  ✓ Сохранена: {img_path}")

    async with TelegramClient(session, api_id, api_hash) as client:
        me = await client.get_me()
        print(f"✓ Авторизован: @{me.username}")

        ok = await set_avatar(client, username, img_path)
        if ok:
            print(f"\n✅ Аватарка установлена для {username}")
        else:
            print(f"\n✗ Не удалось установить аватарку для {username}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генерация и установка аватарки бота через ComfyUI + BotFather")
    parser.add_argument("--username", required=True, help="Username бота, напр. @my_bot")
    parser.add_argument("--prefix", required=True, help="Префикс файла аватарки, напр. my_bot")
    parser.add_argument("--prompt", required=True, help="Текстовый промпт для генерации изображения")
    args = parser.parse_args()

    asyncio.run(main(args.username, args.prefix, args.prompt))
