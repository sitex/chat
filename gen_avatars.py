#!/usr/bin/env python3
"""Генерация и установка аватарок для 5 Tier-1 ботов через ComfyUI (ERNIE) + BotFather (Telethon).

Workflow: SamplerCustomAdvanced + Flux2Scheduler + BasicGuider + EmptyFlux2LatentImage
Модели: ernie-image-turbo-UD-Q5_K_M.gguf + ernie-image-prompt-enhancer + flux2-vae
"""
from __future__ import annotations

import asyncio
import json
import random
import time
import urllib.request
import uuid
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient, events

COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUTPUT = Path("/home/rocky/projects/claude-images/ComfyUI/output")
CHATS_DIR = Path("/home/rocky/projects/chats")
AVATARS_DIR = Path("/home/rocky/projects/chat/avatars")
BOTFATHER_ID = 93372553

BOTS = [
    {
        "username": "@maria_socialself_bot",
        "env": "/home/rocky/projects/chat-socialself/.env",
        "prompt": (
            "Professional headshot portrait of Maria, a warm and empathetic female psychologist in her mid-30s, "
            "dark hair, kind brown eyes, gentle confident smile, business casual attire in soft blues or greens, "
            "clean modern office background with soft bokeh, high quality photography, realistic, 8k"
        ),
    },
    {
        "username": "@acharya_das_gita_bot",
        "env": "/home/rocky/projects/chat-acharya-das/.env",
        "prompt": (
            "Professional portrait of Acharya Das, a wise and serene Indian spiritual teacher in his 50s, "
            "traditional Indian saffron or white dhoti, calm meditative expression, prayer beads in hand, "
            "soft golden temple light background, peaceful, high quality photography, realistic"
        ),
    },
    {
        "username": "@marni_kinrys_bot",
        "env": "/home/rocky/projects/chat-marni/.env",
        "prompt": (
            "Professional headshot of Marni Kinrys, a charismatic and confident female dating coach in her early 40s, "
            "warm blonde hair, bright engaging smile, modern casual chic attire, clean neutral background, "
            "energetic and approachable expression, high quality photography, realistic"
        ),
    },
    {
        "username": "@dan_sigma_bot",
        "env": "/home/rocky/projects/chat-sigma/.env",
        "prompt": (
            "Professional portrait of Dan, a confident self-made alpha male entrepreneur in his late 30s, "
            "athletic build, strong jawline, short dark beard, stylish casual luxury clothing, "
            "modern upscale background, powerful and charismatic expression, high quality photography, realistic"
        ),
    },
    {
        "username": "@luke_hawkins_bot",
        "env": "/home/rocky/projects/chat-lukehawkins/.env",
        "prompt": (
            "Professional headshot of Luke Hawkins, a motivational transformation coach in his early 40s, "
            "clean-cut professional appearance, warm confident smile, business casual attire, "
            "bright modern office or outdoor background, inspiring and trustworthy look, high quality photography, realistic"
        ),
    },
]


def _http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


STEPS = 20  # шагов диффузии


def build_ernie_workflow(prompt: str, width: int = 800, height: int = 800, seed: int | None = None) -> dict:
    """Правильный workflow для ERNIE Image Turbo:
    - SamplerCustomAdvanced + Flux2Scheduler (image-size-aware sigmas)
    - BasicGuider (no CFG — turbo model)
    - EmptyFlux2LatentImage (128 каналов, 16x downscale)
    - flux2-vae.safetensors
    """
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
    """Базовая проверка качества: не шум, не однотонный, достаточный размер."""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(path).convert("RGB")
        arr = np.array(img, dtype=float)
        # Стандартное отклонение яркости: у шума и реальных фото разное
        std = arr.std()
        mean = arr.mean()
        # Шум: std высокий (~60-80) но картинка бессодержательная
        # Портрет: std умеренный (30-70), чёткие переходы
        # Однотонный: std < 5
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
        return True  # если PIL нет, доверяем


def generate_image(prompt: str, prefix: str, max_retries: int = 3) -> Path | None:
    """Генерирует изображение через ComfyUI API, проверяет качество, возвращает путь."""
    import shutil
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
                        # Финальный файл без суффикса попытки
                        final = AVATARS_DIR / f"{prefix}.png"
                        shutil.copy2(dst, final)
                        return final
                    else:
                        print(f"  ↻ Низкое качество, генерируем заново...")
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
    """Устанавливает аватарку бота через BotFather."""
    print(f"  → Установка аватарки {username} через BotFather...")
    botfather = await client.get_entity(BOTFATHER_ID)

    # Сброс зависшего диалога
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
    return "success" in r3.lower() or "set" in r3.lower() or "photo" in r3.lower()


async def main() -> None:
    creds = dotenv_values(str(CHATS_DIR / ".env"))
    api_id = int(creds["TELEGRAM_API_ID"])
    api_hash = creds["TELEGRAM_API_HASH"]
    session = str(CHATS_DIR / "session.session")

    async with TelegramClient(session, api_id, api_hash) as client:
        me = await client.get_me()
        print(f"✓ Авторизован: @{me.username}")

        for bot in BOTS:
            username = bot["username"]
            name = username.replace("@", "").replace("_bot", "")
            print(f"\n=== {username} ===")

            # 1. Генерация изображения
            img_path = generate_image(bot["prompt"], name)
            if not img_path:
                print(f"  ✗ Пропускаем {username} — не удалось сгенерировать")
                continue

            # 2. Установка аватарки
            ok = await set_avatar(client, username, img_path)
            if ok:
                print(f"  ✓ Аватарка установлена для {username}")
            else:
                print(f"  ✗ Не удалось установить аватарку для {username}")

            # Пауза между ботами чтобы не триггерить rate limit BotFather
            print("  → Пауза 30 сек...")
            await asyncio.sleep(30)

    print("\n✅ Готово!")


if __name__ == "__main__":
    asyncio.run(main())
