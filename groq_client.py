# -*- coding: utf-8 -*-
"""Talks to Groq's free cloud API (OpenAI-compatible) instead of a local
Ollama install -- needed because Streamlit Community Cloud can't run a
local LLM. Groq's free tier needs no credit card and is noticeably more
capable than an 8B local model, as a side benefit of this move.

The API key lives in Streamlit secrets (GROQ_API_KEY) and is never exposed
to the browser, same as the Supabase service-role key.
"""
import json
import re
import time

import requests
import streamlit as st

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile"


def is_available():
    try:
        return bool(st.secrets.get("GROQ_API_KEY"))
    except Exception:
        return False


def _api_key():
    return st.secrets["GROQ_API_KEY"]


def _post_chat(prompt, max_tokens, temperature, retries=2):
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=120)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))  # free-tier rate limit -- brief backoff and retry
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            last_error = e
            time.sleep(1)
    raise RuntimeError(
        f"No se pudo conectar con Groq (¿está bien configurada GROQ_API_KEY en Secrets?): {last_error}"
    )


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"[\{\[].*[\}\]]", text, re.S)
    if not match:
        raise ValueError(f"El modelo no devolvió JSON reconocible. Respuesta cruda:\n{text[:500]}")
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*([\}\]])", r"\1", candidate)
        return json.loads(repaired)


def generate_json(prompt, max_tokens=3000, temperature=0.4, retries=2):
    strict_prompt = prompt + (
        "\n\nRecuerda: responde ÚNICAMENTE con el JSON solicitado. "
        "No agregues explicaciones antes o después. No uses bloques de markdown."
    )
    last_error = None
    for attempt in range(retries + 1):
        raw = _post_chat(strict_prompt, max_tokens, temperature)
        try:
            return _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            strict_prompt = (
                prompt
                + "\n\nTu respuesta anterior no era JSON válido. Responde de nuevo, "
                  "ÚNICAMENTE el JSON, sin ningún otro texto:\n" + raw[:800]
            )
    raise last_error
