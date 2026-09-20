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
# openai/gpt-oss-120b is Groq's current recommended flagship model (Sept 2026).
# llama-3.3-70b-versatile, which this used until now, was decommissioned by
# Groq on 2026-08-16. If Groq retires this one too in the future, override
# it without touching code by adding GROQ_MODEL to Streamlit secrets.
DEFAULT_MODEL = "openai/gpt-oss-120b"


def _model_name():
    try:
        return st.secrets.get("GROQ_MODEL", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


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
        "model": _model_name(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_error = None
    last_rate_limit_body = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
            if r.status_code == 429:
                last_rate_limit_body = r.text[:500]
                last_error = f"429 (límite de solicitudes alcanzado): {last_rate_limit_body}"
                # Groq's free-tier limits are per-minute -- a short backoff
                # rarely clears in time, so wait long enough for the window
                # to actually reset instead of retrying uselessly fast.
                time.sleep(20 * (attempt + 1))
                continue
            if r.status_code in (400, 401, 403, 404):
                # Client-side errors (bad key, bad/retired model name, etc.) will
                # never succeed on retry -- fail immediately with Groq's own
                # message instead of masking it behind 3 identical retries.
                raise RuntimeError(f"Groq respondió {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except RuntimeError:
            raise
        except requests.exceptions.Timeout as e:
            last_error = f"tiempo de espera agotado (60s): {e}"
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(1)
    if last_rate_limit_body:
        raise RuntimeError(
            f"Groq rechazó la solicitud por exceso de uso (límite gratuito por minuto/día). "
            f"Espera un momento y reintenta. Detalle: {last_rate_limit_body}"
        )
    raise RuntimeError(f"No se pudo conectar con Groq después de {retries + 1} intentos. Última causa: {last_error}")


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
