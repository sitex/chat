#!/usr/bin/env python3
"""Одноразовый скрипт: аватарка для Lee Jacobs (@unwritten_system_bot)."""
import asyncio, json, random, time, urllib.request, uuid, shutil
from pathlib import Path
from dotenv import dotenv_values
from telethon import TelegramClient, events

COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUTPUT = Path("/home/rocky/projects/claude-images/ComfyUI/output")
CHATS_DIR = Path("/home/rocky/projects/chats")
AVATARS_DIR = Path("/home/rocky/projects/chat/avatars")
BOTFATHER_ID = 93372553
STEPS = 20

BOT = {
    "username": "@unwritten_system_bot",
    "prefix": "lee_jacobs",
    "prompt": (
        "Professional portrait of Lee Jacobs, a thoughtful intense man in his late 40s, "
        "former trauma-informed healer and author, short greying hair, penetrating knowing eyes, "
        "calm grounded expression with quiet intensity, casual earthy henley or open-collar shirt, "
        "softly lit warm neutral background, introspective and authentic, high quality photography, realistic"
    ),
}


def _http_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def _http_post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def build_ernie_workflow(prompt, width=800, height=800, seed=None):
    if seed is None:
        seed = random.randint(0, 2**31)
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "ernie-image-turbo-UD-Q5_K_M.gguf"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "ernie-image-prompt-enhancer.safetensors", "type": "stable_diffusion"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "5": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "Flux2Scheduler", "inputs": {"steps": STEPS, "width": width, "height": height}},
        "7": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["3", 0]}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "10": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["8", 0], "guider": ["7", 0], "sampler": ["9", 0],
            "sigmas": ["6", 0], "latent_image": ["5", 0],
        }},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["4", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "avatar"}},
    }

def check_image_quality(path):
    try:
        from PIL import Image
        import numpy as np
        arr = np.array(Image.open(path).convert("RGB"), dtype=float)
        std, mean = arr.std(), arr.mean()
        print(f"  ✓ QC: mean={mean:.1f} std={std:.1f}")
        if std < 5:
            print("  ✗ QC FAIL: однотонное (std < 5)")
            return False
        if path.stat().st_size < 50_000:
            print(f"  ✗ QC FAIL: слишком маленький ({path.stat().st_size} bytes)")
            return False
        return True
    except Exception as e:
        print(f"  ! QC error: {e}")
        return True

def generate_image(prompt, prefix, max_retries=3):
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_retries + 1):
        seed = random.randint(0, 2**31)
        client_id = str(uuid.uuid4())
        workflow = build_ernie_workflow(prompt, seed=seed)
        print(f"  → Попытка {attempt}/{max_retries}, seed={seed}")
        resp = _http_post(f"{COMFY_URL}/prompt", {"prompt": workflow, "client_id": client_id})
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            print(f"  ✗ Нет prompt_id: {resp}")
            continue
        for _ in range(120):
            time.sleep(2)
            history = _http_get(f"{COMFY_URL}/history/{prompt_id}")
            if prompt_id not in history:
                continue
            for node_output in history[prompt_id].get("outputs", {}).values():
                for img in node_output.get("images", []):
                    subfolder = img.get("subfolder", "")
                    src = COMFY_OUTPUT / subfolder / img["filename"] if subfolder else COMFY_OUTPUT / img["filename"]
                    dst = AVATARS_DIR / f"{prefix}_attempt{attempt}.png"
                    shutil.copy2(src, dst)
                    print(f"  ✓ Изображение: {dst}")
                    if check_image_quality(dst):
                        final = AVATARS_DIR / f"{prefix}.png"
                        shutil.copy2(dst, final)
                        return final
                    print("  ↻ Низкое качество, повтор...")
            break
        else:
            print(f"  ✗ Таймаут попытки {attempt}")
    print(f"  ✗ Все попытки исчерпаны для {prefix}")
    return None

async def wait_botfather(client, timeout=15):
    future = asyncio.get_event_loop().create_future()
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

async def set_avatar(client, username, image_path):
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
    return "success" in r3.lower() or "set" in r3.lower() or "photo" in r3.lower()

async def main():
    creds = dotenv_values(str(CHATS_DIR / ".env"))
    api_id = int(creds["TELEGRAM_API_ID"])
    api_hash = creds["TELEGRAM_API_HASH"]
    session = str(CHATS_DIR / "session.session")

    async with TelegramClient(session, api_id, api_hash) as client:
        me = await client.get_me()
        print(f"✓ Авторизован: @{me.username}")
        print(f"\n=== {BOT['username']} ===")

        img_path = generate_image(BOT["prompt"], BOT["prefix"])
        if not img_path:
            print("✗ Генерация не удалась, выходим")
            return

        ok = await set_avatar(client, BOT["username"], img_path)
        if ok:
            print(f"\n✅ Аватарка установлена для {BOT['username']}")
            print(f"   Файл: {img_path}")
        else:
            print(f"\n✗ Не удалось установить аватарку")

if __name__ == "__main__":
    asyncio.run(main())
