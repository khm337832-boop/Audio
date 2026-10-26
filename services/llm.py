"""Gemini (google-generativeai) အတွက် ပါးလှပ်တဲ့ wrapper။

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


def _model(temperature: float, max_output_tokens: int):
    try:
        import google.generativeai as genai
    except Exception as exc:  # pragma: no cover - optional dependency
        raise LLMUnavailable(f"google-generativeai မရှိပါ: {exc}") from exc

    if not config.GEMINI_API_KEY:
        raise LLMUnavailable("GEMINI_API_KEY မရှိပါ")

    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(
        config.GEMINI_MODEL,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        },
    )


def generate_text(prompt: str, *, temperature: float = 0.9, max_output_tokens: int = 2048) -> str:
    if not available():
        raise LLMUnavailable("offline mode (DRY_RUN/FORCE_MOCK သို့ API key မရှိ)")
    try:
        response = _model(temperature, max_output_tokens).generate_content(prompt)
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(f"Gemini ခေါ်မရပါ: {exc}") from exc

    text = getattr(response, "text", None)
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
            raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except Exception as exc:
        raise LLMUnavailable(f"JSON ဖတ်မရပါ: {exc}") from exc
