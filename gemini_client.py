# -*- coding: utf-8 -*-
"""Talks to Google's Gemini API (Google AI Studio, free tier) instead of
Groq. Same interface as the old groq_client.py (is_available/generate_json)
so course_ai.py barely had to change.

Uses gemini-3.1-flash-lite by default: as of this writing it is Google's
current STABLE (not preview) budget-tier model with no announced shutdown
date -- gemini-2.5-flash, which many guides still recommend, is already
scheduled to be retired on 2026-10-16. Model deprecation is a recurring
fact of life with every AI provider (we already hit this once with Groq),
so the model name is kept overridable via Streamlit secrets (GEMINI_MODEL)
without needing a code change if Google retires this one too.

The API key lives in Streamlit secrets (GEMINI_API_KEY) and is never
exposed to the browser.
"""
import json
import re
import time

import requests
import streamlit as st

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.1-flash-lite"


def _model_name():
    try:
        return st.secrets.get("GEMINI_MODEL", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


def is_available():
    try:
        return bool(st.secrets.get("GEMINI_API_KEY"))
    except Exception:
        return False


def _api_key():
    return st.secrets["GEMINI_API_KEY"]


def _post_generate(prompt, max_tokens, temperature, retries=2):
    url = GEMINI_URL_TEMPLATE.format(model=_model_name())
    headers = {"Content-Type": "application/json", "x-goog-api-key": _api_key()}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "topP": 1,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",  # forces pure JSON, no markdown fences
        },
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code == 429:
                last_error = f"429 (límite de solicitudes alcanzado): {r.text[:500]}"
                time.sleep(20 * (attempt + 1))  # free-tier limits are per-minute
                continue
            if r.status_code in (400, 401, 403, 404):
                raise RuntimeError(f"Gemini respondió {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            body = r.json()
            candidate = body["candidates"][0]
            finish_reason = candidate.get("finishReason")
            if finish_reason == "MAX_TOKENS":
                raise RuntimeError(
                    "Respuesta truncada por límite de tokens (MAX_TOKENS). Sube max_tokens en esta llamada."
                )
            if finish_reason in ("SAFETY", "RECITATION"):
                raise RuntimeError(f"Gemini bloqueó la respuesta ({finish_reason}).")
            parts = candidate.get("content", {}).get("parts", [])
            text = parts[0].get("text", "") if parts else ""
            if not text:
                raise RuntimeError(f"Gemini devolvió una respuesta vacía (finishReason={finish_reason}).")
            return text
        except RuntimeError:
            raise
        except requests.exceptions.Timeout as e:
            last_error = f"tiempo de espera agotado (60s): {e}"
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(1)
    raise RuntimeError(f"No se pudo conectar con Gemini después de {retries + 1} intentos. Última causa: {last_error}")


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
        raw = _post_generate(strict_prompt, max_tokens, temperature)
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
