"""Gemini wrapper — SDK အသစ် (`google-genai`) ကို ဦးစားပေး၊ မရရင် အဟောင်း (`google-generativeai`)။

API key မရှိရင် / ခေါ်လို့မရရင် `LLMUnavailable` ကို ပစ်တယ် —
ခေါ်တဲ့သူက template fallback ကို ပြန်သုံးနိုင်တယ်။
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import config

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """LLM ကို မခေါ်နိုင်တဲ့အခါ (key မရှိ / network / quota)။"""


def available() -> bool:
    return config.llm_available()


# --------------------------------------------------------------------- backends
def _new_client():
    """google-genai (SDK အသစ်) client — မရရင် None။"""
    try:
        from google import genai
    except Exception:
        return None
    try:
        return genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as exc:  # pragma: no cover
        logger.debug("google-genai client မရပါ: %s", exc)
        return None


def _old_model(temperature: float, max_output_tokens: int):
    """google-generativeai (SDK အဟောင်း) model — မရရင် None။"""
    try:
        import google.generativeai as genai
    except Exception:
        return None
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        return genai.GenerativeModel(
            config.GEMINI_MODEL,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("generativeai model မရပါ: %s", exc)
        return None


def generate_text(
    prompt: str,
    *,
    temperature: float = 0.9,
    max_output_tokens: int = 2048,
) -> str:
    if not available():
        raise LLMUnavailable("offline mode (DRY_RUN/FORCE_MOCK သို့ API key မရှိ)")
    if not config.GEMINI_API_KEY:
        raise LLMUnavailable("GEMINI_API_KEY မရှိပါ")

    text: str | None = None

    client = _new_client()
    if client is not None:
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config={"temperature": temperature, "max_output_tokens": max_output_tokens},
            )
            text = getattr(response, "text", None)
        except Exception as exc:
            logger.warning("google-genai ခေါ်မရပါ (%s) — SDK အဟောင်းနဲ့ ပြန်ကြိုးစားမယ်", exc)

    if not text:
        model = _old_model(temperature, max_output_tokens)
        if model is None:
            raise LLMUnavailable(
                "Gemini SDK မရှိပါ — `pip install google-genai` (သို့) "
                "`pip install google-generativeai`"
            )
        try:
            response = model.generate_content(prompt)
            text = getattr(response, "text", None)
        except Exception as exc:
            raise LLMUnavailable(f"Gemini ခေါ်မရပါ: {exc}") from exc

    if not text:
        raise LLMUnavailable("Gemini က ဗလာပြန်ပါတယ်")
    return text.strip()


def generate_json(prompt: str, *, temperature: float = 0.7, max_output_tokens: int = 2048) -> Any:
    """LLM ပြန်တဲ့ စာသားထဲက JSON ကို ဆွဲထုတ်ပေးတယ် (code fence ပါ ရှိနိုင်တယ်)။"""
    raw = generate_text(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
    match = _FENCE.search(raw)
    if match:
        raw = match.group(1)
    raw = raw.strip()
    start_candidates = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if start_candidates:
        start = min(start_candidates)
        end = max(raw.rfind("}"), raw.rfind("]"))
        if end > start:
            raw = raw[start: end + 1]
    try:
        return json.loads(raw)
    except Exception as exc:
        raise LLMUnavailable(f"JSON ဖတ်မရပါ: {exc}") from exc


def validate_key(api_key: str | None = None) -> tuple[bool, str]:
    """Key ကို လျင်မြန်စွာ စစ်ဆေးခြင်း (setup wizard အတွက်)။"""
    key = api_key or config.GEMINI_API_KEY
    if not key:
        return False, "key မရှိပါ"
    try:
        import requests

        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": key},
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"အင်တာနက်ချိတ်ဆက်မှု မရပါ: {exc}"
    if response.status_code != 200:
        return False, f"Google က ငြင်းပယ်တယ် ({response.status_code})"
    models = [m.get("name", "") for m in response.json().get("models", [])]
    return True, f"model {len(models)} ခု ရတယ်"
