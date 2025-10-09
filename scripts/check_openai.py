from __future__ import annotations

import json
import os
import sys

import httpx


OPENAI_DEFAULT_MODEL = "gpt-5"


def main() -> int:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 1

    model = os.getenv("HERETIX_OPENAI_HEALTH_MODEL", OPENAI_DEFAULT_MODEL)
    url = f"https://api.openai.com/v1/models/{model}"

    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
    except httpx.RequestError as exc:  # pragma: no cover - network failure path
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 2

    if resp.status_code != 200:
        detail = resp.text
        print(
            f"ERROR: status={resp.status_code} body={detail}",
            file=sys.stderr,
        )
        return 3

    try:
        payload = resp.json()
    except json.JSONDecodeError:
        print("ERROR: invalid JSON payload from OpenAI", file=sys.stderr)
        return 4

    provider_id = payload.get("id")
    print(f"openai_model={provider_id or model} status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
