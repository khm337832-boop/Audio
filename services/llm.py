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
    """LLM ကို မခေါ်နိုင်တဲ့အခါ (key မရှိ / network / quota / model မရှိ)။"""


# Model တစ်ခု မရှိတော့တဲ့ error လား (အဟောင်း model ကို Google က ပိတ်လိုက်တာ)
_MODEL_GONE_MARKERS = (
    "404",
    "not_found",
    "no longer available",
    "is not found",
    "not supported",
    "unsupported model",
    "does not exist",
)

_working_model: str | None = None


def _model_gone(exc: Exception | str) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _MODEL_GONE_MARKERS)


def working_model() -> str | None:
    """နောက်ဆုံး အလုပ်လုပ်ခဲ့တဲ့ text model (မရသေးရင် None)။"""
    return _working_model


def describe_models() -> str:
    """Doctor/diagnostic အတွက် — သတ်မှတ်ထားတဲ့ model နဲ့ fallback စာရင်း။"""
    chain = config.gemini_model_candidates()
    used = _working_model or "(မ​စမ်းရသေး)"
    return f"model={chain[0]} fallbacks={','.join(chain[1:]) or '-'} working={used}"


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


def _old_model(temperature: float, max_output_tokens: int, model_name: str | None = None):
    """google-generativeai (SDK အဟောင်း) model — မရရင် None။"""
    try:
        import google.generativeai as genai
    except Exception:
        return None
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        return genai.GenerativeModel(
            model_name or config.GEMINI_MODEL,
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
    gone_models: list[str] = []

    global _working_model

    client = _new_client()
    if client is not None:
        candidates = config.gemini_model_candidates()
        if _working_model and _working_model in candidates:  # အလုပ်လုပ်ခဲ့တာကို ဦးစားပေး
            candidates = [_working_model] + [m for m in candidates if m != _working_model]
        last_exc: Exception | None = None
        for model_name in candidates:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"temperature": temperature, "max_output_tokens": max_output_tokens},
                )
                text = getattr(response, "text", None)
                if text:
                    if model_name != config.GEMINI_MODEL:
                        logger.warning("model `%s` မရတော့ပါ — `%s` ကို သုံးမယ် "
                                       "(GEMINI_MODEL ကို ပြောင်းထားနိုင်တယ်)",
                                       config.GEMINI_MODEL, model_name)
                    _working_model = model_name
                    break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if _model_gone(exc):
                    gone_models.append(model_name)
                    logger.info("model `%s` မရှိတော့ပါ — နောက်တစ်ခု စမ်းမယ်", model_name)
                    continue
                logger.warning("google-genai ခေါ်မရပါ (%s)", exc)
                break
        if not text and last_exc is not None and not gone_models:
            logger.warning("google-genai ခေါ်မရပါ (%s) — SDK အဟောင်းနဲ့ ပြန်ကြိုးစားမယ်", last_exc)

    if not text:
        last_exc: Exception | None = None
        for candidate in config.gemini_model_candidates():
            model = _old_model(temperature, max_output_tokens, candidate)
            if model is None:
                raise LLMUnavailable(
                    "Gemini SDK မရှိပါ — `pip install google-genai` (သို့) "
                    "`pip install google-generativeai`"
                )
            try:
                response = model.generate_content(prompt)
                text = getattr(response, "text", None)
                if text:
                    _working_model = candidate
                    break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if _model_gone(exc):
                    gone_models.append(candidate)
                    continue
                raise LLMUnavailable(f"Gemini ခေါ်မရပါ: {exc}") from exc
        if not text and last_exc is not None and gone_models:
            raise LLMUnavailable(
                f"Gemini model မရှိတော့ပါ ({last_exc}) — .env မှာ GEMINI_MODEL ကို "
                f"အသစ်တစ်ခု သတ်မှတ်ပါ (စမ်းထားတာ: {', '.join(gone_models) or config.GEMINI_MODEL})"
                " · `python main.py models` နဲ့ ရနိုင်တဲ့ model စာရင်း ကြည့်ပါ"
            )
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
