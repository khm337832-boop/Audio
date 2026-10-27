"""ပုံဖန်တီးခြင်း — Gemini/Imagen ရှိရင် အဲဒါနဲ့၊ မရှိရင် PIL နဲ့ procedural ပုံ။

`generate_scene_image()` ကို ဗီဒီယိုအခန်းပုံရော thumbnail base ပုံအတွက်ပါ သုံးတယ်။
"""

from __future__ import annotations

import colorsys
import hashlib
import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _seed_from(prompt: str, seed: int | None) -> int:
    if seed is not None:
        return int(seed)
    return int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)


def _hsv_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


def _procedural_image(prompt: str, path: Path, width: int, height: int, seed: int | None) -> Path:
    """API မပါဘဲ လုံခြုံစွာ ထုတ်ပေးတဲ့ gradient + bokeh background ပုံ။"""
    from PIL import Image, ImageDraw, ImageFilter

    rnd = _seed_from(prompt, seed)
    hue = (rnd % 360) / 360.0

    img = Image.new("RGB", (width, height), _hsv_rgb(hue, 0.55, 0.18))
    draw = ImageDraw.Draw(img)

    top = _hsv_rgb(hue, 0.65, 0.30)
    bottom = _hsv_rgb(hue + 0.08, 0.75, 0.06)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)

    glow = Image.new("RGB", (width, height), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for i in range(7):
        cx = (rnd >> (i * 3)) % width
        cy = (rnd >> (i * 5)) % height
        radius = width // (6 + i)
        color = _hsv_rgb(hue + 0.05 * i, 0.6, 0.55)
        gdraw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=tuple(int(c * 0.45) for c in color),
        )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(12, width // 24)))
    img = Image.blend(img, glow, 0.55)

    draw = ImageDraw.Draw(img)
    for i in range(26):
        cx = (rnd >> (i + 1)) % width
        cy = (rnd >> (i * 2 + 3)) % height
        r = 2 + ((rnd >> i) % 5)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 90))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG" if path.suffix.lower() == ".png" else "JPEG", quality=92)
    logger.info("procedural ပုံ ထုတ်ပြီး: %s", path)
    return path


def _save_inline_image(response, path: Path) -> bool:
    """generate_content က ပြန်တဲ့ inline image ကို ဖိုင်အဖြစ် သိမ်းတယ်။"""
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return True
    # SDK အဟောင်း/အခြားပုံစံ
    generated = getattr(response, "generated_images", None)
    if generated:
        image_bytes = generated[0].image.image_bytes
        if image_bytes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            return True
    return False


def _gemini_image(prompt: str, path: Path, width: int, height: int) -> Path | None:
    """Gemini image model နဲ့ ပုံထုတ်တယ်။ မရရင် None (procedural ကို ဆက်သုံး)。

    `models.generate_images` (Imagen) က Gemini Developer API မှာ မရတော့ပါ —
    ဒါကြောင့် `generate_content` + image model (gemini-*-image) ကို ဦးစားပေးတယ်။
    """
    if not config.llm_available():
        return None
    try:
        from google import genai  # type: ignore
    except Exception:
        logger.info("google-genai SDK မရှိပါ — procedural ပုံ သုံးမယ်")
        return None

    client = None
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini client မရပါ (%s)", exc)
        return None

    aspect = f"{width}:{height}"
    for model_name in config.gemini_image_candidates():
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_modalities": ["IMAGE"],
                    "image_config": {"aspect_ratio": "16:9" if aspect == "1280:720" else aspect},
                },
            )
            if _save_inline_image(response, path):
                logger.info("Gemini ပုံ ထုတ်ပြီး (%s): %s", model_name, path)
                return path
            logger.info("`%s` က ပုံ မ​ပြန်ပါ — နောက်တစ်ခု စမ်းမယ်", model_name)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if any(m in text.lower() for m in ("404", "not_found", "not supported",
                                               "no longer available", "unsupported")):
                logger.info("image model `%s` မရပါ — နောက်တစ်ခု စမ်းမယ်", model_name)
                continue
            logger.warning("Gemini ပုံ မထုတ်နိုင်ပါ (%s) — procedural သုံးမယ်", exc)
            break

    # နောက်ဆုံး ကြိုးစားချက် — Imagen (အချို့ project မှာ ရနိုင်)
    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config={"number_of_images": 1, "aspect_ratio": "16:9"},
        )
        if _save_inline_image(response, path):
            logger.info("Imagen ပုံ ထုတ်ပြီး: %s", path)
            return path
    except Exception as exc:  # noqa: BLE001
        logger.info("Imagen မရပါ (%s) — procedural သုံးမယ်", exc)
    return None


def generate_scene_image(
    prompt: str,
    output_path: str | Path,
    *,
    width: int = 1280,
    height: int = 720,
    seed: int | None = None,
) -> Path:
    """Prompt → ပုံဖိုင်။ API မရရင် procedural placeholder ပြန်ပေးတယ် (pipeline မရပ်ဘူး)။"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        logger.debug("ပုံ ရှိပြီးသား: %s", path)
        return path

    if config.llm_available():
        result = _gemini_image(prompt, path, width, height)
        if result:
            return result
    return _procedural_image(prompt, path, width, height, seed)
