"""
core/image_engine.py - Zero-GPU scene artwork generation (AI Horde + stylized procedural fallback).
"""
import base64
import hashlib
import io
import math
import os
import random
import time
import requests
from PIL import Image, ImageDraw, ImageFilter
import config

MOOD_PALETTES = {
    "mystery": ((12, 18, 42), (38, 52, 102), (245, 194, 92)),
    "wonder": ((18, 36, 72), (62, 118, 168), (255, 224, 130)),
    "tension": ((36, 14, 28), (112, 34, 52), (255, 138, 76)),
    "triumph": ((28, 42, 84), (218, 128, 74), (255, 240, 178)),
}


def generate_scene_images(scenes: list, aspect: str = "9:16") -> list:
    """
    Generates distinct scene-by-scene artwork using Pollinations (Flux) as primary,
    AI Horde txt2img as secondary, and stylized procedural art as fallback.
    No img2img chaining so every scene has its own dynamic camera angle & composition.
    """
    import urllib.parse

    preset = config.ASPECT_PRESETS.get(aspect, config.ASPECT_PRESETS["9:16"])
    poly_w = preset["image_width"]
    poly_h = preset["image_height"]
    horde_w = min(poly_w, 512)
    horde_h = min(poly_h, 512)

    total = len(scenes)
    base_seed = random.randint(1000, 999999)

    for idx, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", idx)
        prompt = scene.get("full_image_prompt") or scene.get("visual_prompt", "storybook landscape")
        out_path = os.path.join(config.TEMP_DIR, f"scene_{scene_id:02d}.png")
        scene_seed = base_seed + idx * 101

        print(f"[image_engine] Scene {idx}/{total}: {prompt[:75]}...", flush=True)

        success = False
        # 1. Try Pollinations.ai (Flux, native aspect ratio, fast, zero GPU)
        try:
            encoded = urllib.parse.quote(prompt, safe="")
            url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width={poly_w}&height={poly_h}&model=flux&seed={scene_seed}&nologo=true"
            )
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 5000:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                img.save(out_path, "PNG")
                scene["image_path"] = out_path
                success = True
                print(f"[image_engine] Scene {scene_id} generated via Pollinations (Flux {poly_w}x{poly_h})", flush=True)
        except Exception as exc:
            print(f"[image_engine] Scene {scene_id} Pollinations skipped: {exc}", flush=True)

        # 2. Fallback to AI Horde txt2img (fresh composition per scene)
        if not success:
            try:
                img_data, used_model, _ = _request_horde_image(
                    prompt=prompt,
                    width=horde_w,
                    height=horde_h,
                    ref_image_path=None,
                    target_model=None,
                    seed=str(scene_seed),
                )
                _save_horde_image(img_data, out_path)
                scene["image_path"] = out_path
                success = True
                print(f"[image_engine] Scene {scene_id} generated via AI Horde ({used_model})", flush=True)
            except Exception as exc:
                print(f"[image_engine] Scene {scene_id} Horde skipped: {exc}", flush=True)

        # 3. Procedural fallback
        if not success:
            print(f"[image_engine] Rendering stylized procedural artwork for Scene {scene_id}...", flush=True)
            _render_procedural_scene(
                out_path=out_path,
                scene_id=scene_id,
                prompt=prompt,
                mood=scene.get("mood", "wonder"),
                aspect=aspect,
            )
            scene["image_path"] = out_path

    return scenes


def _request_horde_image(
    prompt: str,
    width: int = 512,
    height: int = 512,
    ref_image_path: str = None,
    target_model: str = None,
    denoising_strength: float = 0.60,
    seed: str = None,
):
    headers = {
        "Client-Agent": config.AI_HORDE_CLIENT_AGENT,
        "apikey": config.AI_HORDE_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": f"{prompt} ### {config.NEGATIVE_PROMPT}",
        "params": {
            "width": width,
            "height": height,
            "steps": 20,
            "sampler_name": "k_euler_a",
            "cfg_scale": 7.5,
        },
        "models": [target_model] if target_model else config.CARTOON_IMAGE_MODELS,
        "nsfw": False,
        "censor_nsfw": True,
        "r2": True,
    }
    if seed:
        payload["params"]["seed"] = str(seed)

    if ref_image_path and os.path.exists(ref_image_path):
        b64 = _encode_b64(ref_image_path, width, height)
        if b64:
            payload["source_image"] = b64
            payload["source_processing"] = "img2img"
            payload["params"]["denoising_strength"] = float(denoising_strength)

    post_res = requests.post(
        f"{config.AI_HORDE_BASE_URL}/generate/async",
        json=payload,
        headers=headers,
        timeout=20,
    )
    data = post_res.json()
    job_id = data.get("id")
    if not job_id:
        raise RuntimeError(f"Horde rejected job: {data}")

    start = time.time()
    while time.time() - start < 40:
        time.sleep(3)
        chk = requests.get(
            f"{config.AI_HORDE_BASE_URL}/generate/check/{job_id}",
            headers=headers,
            timeout=15,
        ).json()
        if chk.get("faulted"):
            raise RuntimeError(f"Horde job {job_id} faulted")
        if chk.get("done"):
            status = requests.get(
                f"{config.AI_HORDE_BASE_URL}/generate/status/{job_id}",
                headers=headers,
                timeout=15,
            ).json()
            gens = status.get("generations", [])
            if gens and gens[0].get("img"):
                return gens[0]["img"], gens[0].get("model", "stable_diffusion"), gens[0].get("seed", "0")
            raise RuntimeError("Horde returned empty generation")

    raise TimeoutError(f"Horde job {job_id} timed out after 40s")


def _encode_b64(path: str, max_w: int, max_h: int) -> str:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


def _save_horde_image(img_data: str, out_path: str):
    if img_data.startswith("http"):
        resp = requests.get(img_data, timeout=30)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
    else:
        img = Image.open(io.BytesIO(base64.b64decode(img_data)))
    img.convert("RGB").save(out_path, "PNG")


def _render_procedural_scene(out_path: str, scene_id: int, prompt: str, mood: str, aspect: str):
    """Creates a richly layered atmospheric storybook frame so CI never fails."""
    w, h = (720, 1280) if aspect == "9:16" else (1280, 720)
    top_col, bot_col, glow_col = MOOD_PALETTES.get(mood, MOOD_PALETTES["wonder"])

    digest = hashlib.sha256(f"{scene_id}:{prompt}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))

    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)

    # Vertical atmospheric sky gradient
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_col[0] + (bot_col[0] - top_col[0]) * t)
        g = int(top_col[1] + (bot_col[1] - top_col[1]) * t)
        b = int(top_col[2] + (bot_col[2] - top_col[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Glowing celestial orb / lantern core
    orb_x = int(w * rng.uniform(0.28, 0.72))
    orb_y = int(h * rng.uniform(0.24, 0.44))
    orb_r = int(min(w, h) * rng.uniform(0.11, 0.17))

    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)
    for mult, alpha in [(2.6, 28), (1.8, 55), (1.25, 110), (1.0, 220)]:
        rr = int(orb_r * mult)
        gdraw.ellipse(
            [orb_x - rr, orb_y - rr, orb_x + rr, orb_y + rr],
            fill=(glow_col[0], glow_col[1], glow_col[2], alpha),
        )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=14))
    img = Image.alpha_composite(img.convert("RGBA"), glow_layer)
    draw = ImageDraw.Draw(img)

    # Starlight & floating dust motes
    for _ in range(55):
        sx = rng.randint(0, w)
        sy = rng.randint(0, int(h * 0.75))
        sr = rng.randint(1, 4)
        alpha = rng.randint(90, 220)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 250, 230, alpha))

    # Layered parallax terrain / skyline silhouettes
    for layer_idx, (base_frac, shade, amp) in enumerate([
        (0.62, (top_col[0] + 18, top_col[1] + 18, top_col[2] + 28, 210), 0.08),
        (0.73, (top_col[0] + 8, top_col[1] + 10, top_col[2] + 18, 235), 0.06),
        (0.84, (8, 10, 18, 255), 0.04),
    ]):
        pts = [(0, h)]
        phase = rng.uniform(0, math.pi * 2)
        freq = rng.uniform(2.2, 4.5)
        for step in range(0, 25):
            px = int(w * step / 24)
            py = int(h * (base_frac + amp * math.sin(phase + freq * step / 24.0)))
            pts.append((px, py))
        pts.append((w, h))
        draw.polygon(pts, fill=shade)

    img.convert("RGB").save(out_path, "PNG")
