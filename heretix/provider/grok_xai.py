from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from heretix.ratelimit import RateLimiter
from openai import OpenAI


_DEFAULT_GROK_MODEL = os.getenv("HERETIX_GROK_MODEL", "grok-4-fast-non-reasoning")
_REQUIRE_CONTEXT = os.getenv("HERETIX_GROK_REQUIRE_CONTEXT", "1").lower() not in {"0", "false", "no"}
_CONTEXT_MIN_ITEMS = max(1, int(os.getenv("HERETIX_GROK_CONTEXT_MIN_ITEMS", "4")))
_CONTEXT_MIN_WORDS = max(5, int(os.getenv("HERETIX_GROK_CONTEXT_MIN_WORDS", "15")))
_MAX_ATTEMPTS = max(1, int(os.getenv("HERETIX_GROK_MAX_ATTEMPTS", "3")))
_DEBUG_DIR_ENV = os.getenv("HERETIX_GROK_DEBUG_DIR")
_DEBUG_DIR = Path(_DEBUG_DIR_ENV).expanduser() if _DEBUG_DIR_ENV else None

_CONTEXT_REQUIREMENTS = (
    "CRITICAL: Your reasoning must be CONCRETE and ACCESSIBLE to a general audience.\n\n"
    "For EVERY reasoning bullet, you MUST:\n"
    "1. Name specific actors, companies, dates, or examples (e.g., 'Tesla announced in 2024...', not 'Companies have...')\n"
    "2. Use plain language—explain as if to someone with no technical background\n"
    "3. Make each bullet a full 15-20 word sentence explaining WHY this fact shifts the probability\n"
    "4. Avoid abstract statements like 'historical patterns suggest' or 'economic theory indicates'\n"
    "5. Instead say 'When X happened in YYYY, it resulted in Z, which suggests...'\n\n"
    "BAD: 'Tariffs typically increase costs.'\n"
    "GOOD: 'When Trump imposed steel tariffs in 2018, washing machine prices rose 12% within six months, documented by BLS.'\n\n"
    "Assume the reader knows NOTHING about economics, technology, or the topic—explain from first principles."
)
_CONTEXT_REMINDER = (
    "Your previous answer was too technical or vague. Re-write with CONCRETE EXAMPLES.\n\n"
    "Requirements:\n"
    "- Name specific companies, people, dates, or events\n"
    "- Explain WHY each fact matters in simple terms\n"
    "- Use 15-20 words per reasoning bullet\n"
    "- Write as if explaining to a smart 12-year-old\n\n"
    "Do NOT use jargon, abbreviations, or assume prior knowledge."
)


def score_claim(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str | None = None,
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Call xAI Grok (OpenAI-compatible) to score a claim under a paraphrase.

    Returns a dict with keys: raw (parsed JSON), meta (provider_model_id,
    prompt_sha256, response_id, created), and timing fields (latency_ms).
    """

    target_model = (model or _DEFAULT_GROK_MODEL).strip() or _DEFAULT_GROK_MODEL

    paraphrased = paraphrase_text.replace("{CLAIM}", claim)
    user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", claim)
    schema_instructions = (
        "Return ONLY JSON matching this schema. WRITE IN PLAIN, CONVERSATIONAL LANGUAGE—"
        "pretend you're explaining to a friend who knows nothing about the topic:\n\n"
        "{ \"prob_true\": 0..1, \"confidence_self\": 0..1, "
        "\"assumptions\": [string], "
        "\"reasoning_bullets\": [3-6 strings - EACH MUST BE 15-20 WORDS, NAME SPECIFIC EXAMPLES], "
        "\"contrary_considerations\": [2-4 strings - CONCRETE COUNTEREXAMPLES WITH DATES/NAMES], "
        "\"ambiguity_flags\": [string] }\n\n"
        "TONE REQUIREMENTS:\n"
        "- Use simple words (not 'utilizing', say 'using')\n"
        "- Explain abbreviations ('EV' → 'electric vehicle')\n"
        "- Give specific examples with numbers and dates\n"
        "- Write like explaining to a curious non-expert\n\n"
        "Output the JSON object only."
    )
    base_instructions = system_text + "\n\n" + schema_instructions + "\n\n" + _CONTEXT_REQUIREMENTS
    prompt_sha256 = hashlib.sha256((base_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    # Prepare client (OpenAI SDK pointed to xAI)
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"))

    attempts: List[Dict[str, Any]] = []
    raw_obj: Dict[str, Any] = {}
    provider_model_id = target_model
    response_id: str | None = None
    created_ts: float = float(int(time.time()))
    latency_ms = 0
    reminder_suffix = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        instructions = base_instructions if not reminder_suffix else base_instructions + "\n\n" + reminder_suffix
        text, provider_model_id, response_id, created_ts, latency_ms = _invoke_xai(
            client=client,
            target_model=target_model,
            instructions=instructions,
            user_text=user_text,
            max_output_tokens=max_output_tokens,
        )
        raw_obj = _parse_json(text)
        needs_context = _REQUIRE_CONTEXT and _needs_richer_context(raw_obj)

        attempts.append(
            {
                "attempt": attempt,
                "instructions": instructions,
                "needs_context": needs_context,
                "raw_text": text,
                "parsed": raw_obj,
                "latency_ms": latency_ms,
                "response_id": response_id,
            }
        )

        if not needs_context:
            break
        reminder_suffix = _CONTEXT_REMINDER

    _write_debug_record(
        {
            "claim": claim,
            "model": target_model,
            "prompt_sha256": prompt_sha256,
            "attempts": attempts,
            "timestamp": time.time(),
        }
    )

    return {
        "raw": raw_obj if isinstance(raw_obj, dict) else {},
        "meta": {
            "provider_model_id": provider_model_id or target_model,
            "prompt_sha256": prompt_sha256,
            "response_id": response_id,
            "created": created_ts,
        },
        "timing": {"latency_ms": latency_ms},
    }


def _invoke_xai(
    *,
    client: OpenAI,
    target_model: str,
    instructions: str,
    user_text: str,
    max_output_tokens: int,
) -> Tuple[str, str, str | None, float, int]:
    """Call Grok Responses API with fallback to Chat Completions."""
    t0 = time.time()
    text: str = ""
    provider_model_id = target_model
    response_id: str | None = None
    created_ts: float = float(int(time.time()))

    try:
        _XAI_RATE_LIMITER.acquire()
        resp = client.responses.create(
            model=target_model,
            instructions=instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            max_output_tokens=max_output_tokens,
            temperature=0,
        )
        text = _extract_text_from_responses(resp)
        provider_model_id = getattr(resp, "model", target_model)
        response_id = getattr(resp, "id", None) or getattr(resp, "response_id", None)
        created_ts = float(getattr(resp, "created", int(time.time())))
    except Exception:
        _XAI_RATE_LIMITER.acquire()
        chat = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=max_output_tokens,
        )
        try:
            msg = chat.choices[0].message  # type: ignore[attr-defined]
            text = getattr(msg, "content", None) or ""
        except Exception:
            text = ""
        provider_model_id = getattr(chat, "model", target_model)
        response_id = getattr(chat, "id", None)
        created_ts = float(getattr(chat, "created", int(time.time())))

    latency_ms = int((time.time() - t0) * 1000)
    return text or "", provider_model_id, response_id, created_ts, latency_ms


def _extract_text_from_responses(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if text:
        return text
    try:
        for o in getattr(resp, "output", []) or []:
            if getattr(o, "type", None) == "message":
                for part in getattr(o, "content", []) or []:
                    if getattr(part, "type", None) == "output_text":
                        candidate = getattr(part, "text", None)
                        if candidate:
                            return candidate
    except Exception:
        return ""
    return ""


def _parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return {}
    return {}


def _needs_richer_context(payload: Dict[str, Any]) -> bool:
    if not payload:
        return True
    bullets = payload.get("reasoning_bullets")
    if not isinstance(bullets, list) or len(bullets) < _CONTEXT_MIN_ITEMS:
        return True
    rich = 0
    for item in bullets:
        if isinstance(item, str) and len(item.split()) >= _CONTEXT_MIN_WORDS:
            rich += 1
    if rich < _CONTEXT_MIN_ITEMS:
        return True
    contrary = payload.get("contrary_considerations")
    if isinstance(contrary, list) and contrary:
        has_contrary = any(isinstance(c, str) and len(c.split()) >= _CONTEXT_MIN_WORDS for c in contrary)
        if not has_contrary:
            return True
    return False


def _write_debug_record(record: Dict[str, Any]) -> None:
    if not _DEBUG_DIR:
        return
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"grok_{int(time.time() * 1000)}_{secrets.token_hex(4)}.json"
        path = _DEBUG_DIR / fname
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    except Exception:
        pass


_XAI_RATE_LIMITER = RateLimiter(
    rate_per_sec=float(os.getenv("HERETIX_XAI_RPS", "1")),
    burst=int(os.getenv("HERETIX_XAI_BURST", "2")),
)
