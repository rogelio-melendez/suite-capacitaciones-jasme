# -*- coding: utf-8 -*-
"""All the AI planning calls for the course generator wizard, running on
Groq's free cloud API (see groq_client.py) -- no cost, no credit card,
using a capable 70B model.

Design principle unchanged since this used Claude, then Ollama: the model
PROPOSES, the person CONFIRMS. Every dynamic exercise and every exam
question is always shown for the person to confirm or correct before it is
used for anything.
"""
import json

import groq_client as oc

# Groq's hosted 70B model has a much larger, more reliable context than a
# local 8B model -- but we still keep prompts reasonably sized so each
# wizard step stays fast and cheap on the free tier.
MAX_SOURCE_CHARS = 40_000


def _truncate(text):
    if len(text) <= MAX_SOURCE_CHARS:
        return text
    return (text[:MAX_SOURCE_CHARS] +
            "\n\n[...material truncado por longitud; si es muy largo, considera dividirlo...]")


def _call(prompt, max_tokens=2500):
    return oc.generate_json(prompt, max_tokens=max_tokens, temperature=0.3)


# =====================================================================
# STEP 1: Temario + objetivo de aprendizaje
# =====================================================================

def propose_temario_and_objetivo(source_text, course_title, user_temario=None, num_topics_hint=None):
    """If user_temario is given (list of strings), the model is only asked
    for the objetivo (and to sanity-check/lightly tidy the topic wording).
    Otherwise it proposes both from scratch."""
    source_text = _truncate(source_text)
    temario_instruction = (
        f"El usuario ya definió este temario, respétalo tal cual (puedes limpiar la redacción "
        f"pero no agregues ni quites temas): {json.dumps(user_temario, ensure_ascii=False)}"
        if user_temario else
        f"Propón un temario de {num_topics_hint or 'entre 5 y 9'} temas, en el orden lógico en que "
        f"deben impartirse, cubriendo el material fuente de forma completa."
    )
    prompt = f"""Eres un diseñador instruccional experto en capacitación técnica/normativa para empresas.

MATERIAL FUENTE (puede ser una ley, norma, reglamento o cualquier contenido técnico):
---
{source_text}
---

Curso a construir: "{course_title}"

{temario_instruction}

Además, redacta el objetivo de aprendizaje del curso: un párrafo que empiece con
"Al finalizar el curso, el participante será capaz de..." y resuma de forma completa
pero concisa lo que el participante sabrá hacer.

Devuelve ÚNICAMENTE un JSON (sin texto adicional, sin markdown) con esta forma:
{{"temario": ["Tema 1", "Tema 2", ...], "objetivo": "Al finalizar el curso..."}}
"""
    return _call(prompt, max_tokens=2000)


# =====================================================================
# STEP 2: Slide-budget allocation across topics
# =====================================================================

def allocate_slide_budget(source_text, temario, total_content_slides):
    """Splits the total content-slide budget (NOT counting title/dynamic/
    exercise slides -- just the "material" slides) across topics, roughly
    proportional to how much source material each topic covers."""
    source_text = _truncate(source_text)
    prompt = f"""Material fuente:
---
{source_text}
---

Temario del curso: {json.dumps(temario, ensure_ascii=False)}

Tienes un presupuesto total de {total_content_slides} diapositivas de CONTENIDO
(no cuentes portadas de tema, dinámicas ni ejercicios, solo diapositivas de
contenido explicativo) para repartir entre estos temas, de forma proporcional
a cuánto material fuente le corresponde a cada uno. Cada tema debe recibir
al menos 1 diapositiva.

Devuelve ÚNICAMENTE un JSON con esta forma exacta (un entero por tema, en el
mismo orden del temario, que sumen exactamente {total_content_slides}):
{{"allocation": [3, 5, 2, ...]}}
"""
    result = _call(prompt, max_tokens=500)
    allocation = result["allocation"]
    # Defensive rebalancing in case the model's sum drifts from the budget.
    diff = total_content_slides - sum(allocation)
    if diff != 0 and allocation:
        allocation[allocation.index(max(allocation))] += diff
    return allocation


# =====================================================================
# STEP 3: Content synthesis for one topic
# =====================================================================

def synthesize_topic_content(source_text, topic_name, n_slides, verbatim=False):
    """Returns {"content_titles": [...], "content_slides": [[bullet, ...], ...]}
    with exactly n_slides entries in each list.
    If verbatim=True, the content must be the literal source text for this
    topic (e.g. "Objetivo" / "Campo de aplicación" of a legal norm), not a
    synthesis -- still split across n_slides if it doesn't fit on one."""
    source_text = _truncate(source_text)
    mode_instruction = (
        "IMPORTANTE: este tema debe reproducirse TEXTUAL, tal cual aparece en el material "
        "fuente, sin sintetizar ni parafrasear -- solo puedes dividirlo en varias diapositivas "
        "si no cabe en una."
        if verbatim else
        "Sintetiza el contenido: usa bullets breves y claros, sin saturar cada diapositiva "
        "(máximo 4-5 bullets por diapositiva, cada uno de una o dos líneas)."
    )
    prompt = f"""Material fuente completo:
---
{source_text}
---

Vas a preparar el contenido de UNA sección de un curso de capacitación: "{topic_name}".

Tienes exactamente {n_slides} diapositiva(s) de contenido para este tema. {mode_instruction}

Devuelve ÚNICAMENTE un JSON con esta forma exacta ({n_slides} elementos en cada lista):
{{"content_titles": ["Subtítulo de la diapositiva 1", ...],
  "content_slides": [["bullet 1", "bullet 2", ...], ...]}}
"""
    result = _call(prompt, max_tokens=3000)
    # Defensive: pad/truncate to exactly n_slides if the model drifts.
    titles = (result.get("content_titles") or [])[:n_slides]
    slides = (result.get("content_slides") or [])[:n_slides]
    while len(titles) < n_slides:
        titles.append(topic_name)
    while len(slides) < n_slides:
        slides.append(["(completar contenido)"])
    return {"content_titles": titles, "content_slides": slides}


# =====================================================================
# STEP 4: Dynamic (exercises) proposal for one topic
# =====================================================================

def propose_dynamic(source_text, topic_name, topic_bullets):
    """Proposes ONE dynamic (up to 4 exercises) for a topic, picking the
    pattern (verdadero/falso, clasificar/relacionar, caso breve) that best
    fits the kind of content. Every exercise's answer is a PROPOSAL the
    person must confirm in the review screen -- never auto-trusted."""
    source_text = _truncate(source_text)
    content_summary = "\n".join(f"- {b}" for slide in topic_bullets for b in slide)
    prompt = f"""Material fuente (para contexto y para que las respuestas sean correctas):
---
{source_text}
---

Tema: "{topic_name}"
Contenido ya preparado para este tema:
{content_summary}

Diseña UNA dinámica de repaso para este tema, de máximo 4 ejercicios, eligiendo
el patrón que mejor se ajuste al tipo de contenido:
- "verdadero_falso": afirmaciones a evaluar como verdaderas o falsas (bueno para definiciones/datos).
- "clasificar": el participante debe decidir a cuál de 2 categorías corresponde algo
  (bueno cuando el contenido distingue claramente dos roles o dos tipos de algo,
  ej. "patrón o trabajador", "medida técnica o administrativa").
- "caso_breve": un caso o pregunta breve con una respuesta correcta a determinar
  (bueno para procedimientos o para aplicar un criterio).

Devuelve ÚNICAMENTE un JSON con esta forma exacta:
{{"tipo": "verdadero_falso" | "clasificar" | "caso_breve",
  "instruccion": "Texto que se muestra en la diapositiva de transición 'Dinámica'.",
  "categorias": ["CATEGORIA_A", "CATEGORIA_B"],
  "ejercicios": [
    {{"enunciado": "...", "respuesta_propuesta": "VERDADERO" | "FALSO" | "CATEGORIA_A" | "CATEGORIA_B" | "texto de respuesta breve",
      "explicacion": "por qué es la respuesta correcta, en 1-2 frases"}},
    ... (2 a 4 ejercicios)
  ]}}
Nota: "categorias" solo aplica (y es obligatorio) cuando tipo="clasificar"; para los otros
tipos devuélvelo como lista vacía.
"""
    return _call(prompt, max_tokens=2500)


# =====================================================================
# STEP 5: Exam questions (initial / final)
# =====================================================================

def propose_exam(source_text, temario, n_questions, exam_label="inicial"):
    """Returns a list of {"pregunta":.., "opciones": [4 strings], "respuesta_propuesta": "a"|"b"|"c"|"d"}.
    Generated in small batches (not all N at once) -- local models are far
    less reliable than Claude at getting a long, uniform JSON list right in
    a single shot."""
    source_text = _truncate(source_text)
    batch_size = 4
    all_questions = []
    for start in range(0, n_questions, batch_size):
        count = min(batch_size, n_questions - start)
        avoid = ""
        if all_questions:
            previous = "; ".join(q["pregunta"][:60] for q in all_questions[-8:])
            avoid = f"\nNo repitas estas preguntas ya usadas: {previous}"
        prompt = f"""Material fuente:
---
{source_text}
---

Temario del curso: {json.dumps(temario, ensure_ascii=False)}

Redacta exactamente {count} preguntas de opción múltiple (4 opciones cada una, solo una
correcta) para el examen {exam_label} de este curso. Basa cada pregunta y su respuesta
correcta ÚNICAMENTE en el material fuente proporcionado -- no inventes datos que no
estén ahí.{avoid}

Devuelve ÚNICAMENTE un JSON con esta forma exacta:
{{"preguntas": [
   {{"pregunta": "...", "opciones": ["...", "...", "...", "..."], "respuesta_propuesta": "a"}},
   ...
]}}
"""
        result = _call(prompt, max_tokens=1500)
        all_questions.extend(result["preguntas"][:count])
    return all_questions
