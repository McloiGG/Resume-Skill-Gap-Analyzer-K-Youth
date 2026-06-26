from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL_ALIASES = {
    "deepseek-r1": "deepseek-r1:1.5b",
    "qwen3.5": "qwen3.5:4b",
}
REQUEST_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))


def prompt_model(model: str, prompt: str, num_predict: int | None = None) -> str:
    """Prompt a local Ollama model and return a text response."""
    clean_model = model.strip()
    clean_prompt = prompt.strip()

    if not clean_model:
        return "[Input Error] Model name is required."
    if not clean_prompt:
        return "[Input Error] Prompt is required."

    return _prompt_ollama(clean_model, clean_prompt, num_predict)


def _prompt_ollama(model: str, prompt: str, num_predict: int | None) -> str:
    try:
        resolved_model = _resolve_ollama_model(model)
        payload = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }
        if num_predict is not None:
            payload["options"] = {"num_predict": num_predict}

        response = _post_ollama_json(
            "/api/generate",
            payload,
        )
        text = response.get("response")
        if not isinstance(text, str):
            return f"[Ollama Error] Response did not include text: {response}"
        return text
    except Exception as exc:  # noqa: BLE001 - CLI must not expose stack traces.
        return f"[Ollama Error] {exc}"


def _resolve_ollama_model(model: str) -> str:
    if ":" in model:
        return model

    available_models = _list_ollama_models()
    if model in available_models:
        return model

    latest_model = f"{model}:latest"
    if latest_model in available_models:
        return latest_model

    for available_model in available_models:
        if available_model.startswith(f"{model}:"):
            return available_model

    return model


def _list_ollama_models() -> list[str]:
    try:
        response = _get_ollama_json("/api/tags")
    except Exception:  # noqa: BLE001 - fallback lets the final generate call report the real issue.
        return []

    models = response.get("models", [])
    if not isinstance(models, list):
        return []

    names = []
    for item in models:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _get_ollama_json(path: str) -> dict:
    ollama_host = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")
    with urllib.request.urlopen(
        f"{ollama_host}{path}", timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_ollama_json(path: str, payload: dict) -> dict:
    ollama_host = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).rstrip("/")
    request = urllib.request.Request(
        f"{ollama_host}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: uv run prompt_model.py <model> "<prompt>"')
        return

    model = sys.argv[1]
    prompt = " ".join(sys.argv[2:])
    response = prompt_model(model, prompt)
    print("\n--- RESPONSE ---\n")
    print(response)


if __name__ == "__main__":
    main()
