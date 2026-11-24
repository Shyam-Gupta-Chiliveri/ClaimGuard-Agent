"""Minimal OpenAI-compatible chat client (OpenAI, Ollama, Groq, OpenRouter, vLLM, LM Studio...).

Configure with environment variables:
  LLM_BASE_URL  e.g. https://api.openai.com/v1  or  http://ollama:11434/v1
  LLM_API_KEY   (Ollama accepts any value)
  LLM_MODEL     e.g. gpt-4o-mini, llama3.1:8b, qwen2.5:7b
"""

from __future__ import annotations

import os

import httpx


def configured() -> bool:
    return bool(os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_MODEL"))


def describe() -> dict:
    return {"mode": "llm" if configured() else "offline",
            "model": os.environ.get("LLM_MODEL") if configured() else "deterministic planner"}


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.1) -> dict:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    payload = {"model": os.environ["LLM_MODEL"], "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', 'none')}"}
    timeout = float(os.environ.get("LLM_TIMEOUT", "90"))
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]
