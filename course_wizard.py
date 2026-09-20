# -*- coding: utf-8 -*-
"""Step-by-step wizard: source material -> temario/objetivo -> content ->
dynamics -> exams -> final PPTX. Every AI proposal is shown for editing
before the next step runs, per the user's explicit request to review
everything along the way."""
import os
import tempfile
import time

import streamlit as st

from content_extractor import extract_text
import course_ai
from course_builder import build_course

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "Plantilla_JASME.pptx")


def _need_api_key():
    """Confirms Groq is reachable before starting a long wizard run."""
    import groq_client
    if not groq_client.is_available():
        st.error(
            "Falta configurar GROQ_API_KEY en Settings → Secrets de esta app en Streamlit Cloud. "
            "Consigue una clave gratis en console.groq.com/keys."
        )
        return True
    return False


def _call_ai(label, fn, *args, **kwargs):
    """Runs an AI call and, if it fails, shows the REAL error message right
    on the page (st.error is never redacted by Streamlit Cloud -- only
    uncaught exceptions are) instead of letting it crash the whole app with
    a generic censored message."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        st.error(f"❌ Ocurrió un error generando **{label}**.\n\nDetalle: `{e}`")
        st.info("Puedes intentar de nuevo dando clic al botón otra vez -- muchas veces es un hipo temporal de Groq.")
        st.stop()


def _init_state():
    st.session_state.setdefault("cw_step", 0)
    st.session_state.setdefault("cw_data", {})


def _reset():
    st.session_state.cw_step = 0
    st.session_state.cw_data = {}


def render():
    _init_state()
    st.header("Crear curso de capacitación")
    st.caption(
        "Sube el material fuente (ley, norma, reglamento o cualquier contenido técnico) y la app "
        "propone temario, objetivo, contenido, dinámicas y exámenes -- revisando y confirmando cada "
        "paso contigo antes de armar la presentación final con el formato JASME."
    )

    step = st.session_state.cw_step
    data = st.session_state.cw_data

    if st.session_state.cw_step > 0:
        if st.button("↩️ Empezar un curso nuevo (borra el progreso actual)"):
            _reset()
            st.rerun()
        st.divider()

    if step == 0:
        _step0_config()
    elif step == 1:
        _step1_temario_objetivo()
    elif step == 2:
        _step2_contenido()
    elif step == 3:
        _step3_dinamicas()
    elif step == 4:
        _step4_examenes()
    elif step == 5:
        _step5_generar()


# =====================================================================
# STEP 0 -- upload + basic configuration
# =====================================================================
def _step0_config():
    data = st.session_state.cw_data
    st.subheader("1. Material fuente y configuración")

    source_mode = st.radio("¿Cómo vas a dar el material fuente?", ["Subir archivo (PDF / Word / TXT)", "Pegar texto directamente"])
    source_text = None
    if source_mode == "Subir archivo (PDF / Word / TXT)":
        f = st.file_uploader("Material fuente", type=["pdf", "docx", "txt", "md"])
        if f is not None:
            with st.spinner("Extrayendo texto del archivo..."):
                try:
                    source_text = extract_text(f, f.name)
                except Exception as e:
                    st.error(f"No se pudo leer el archivo: {e}")
    else:
        source_text = st.text_area("Pega aquí el texto completo del material fuente", height=250)

    if source_text:
        st.success(f"Material listo ({len(source_text):,} caracteres).")

    course_title = st.text_input("Título del curso", placeholder="ej. NORMA Oficial Mexicana NOM-XXX-STPS-20XX")

    st.divider()
    st.markdown("**Temario**")
    temario_mode = st.radio("¿El temario lo das tú o lo propone la IA?", ["Que la IA lo proponga", "Yo doy el temario"], key="temario_mode")
    user_temario = None
    num_topics_hint = None
    if temario_mode == "Yo doy el temario":
        temario_text = st.text_area("Un tema por línea", height=150)
        user_temario = [line.strip() for line in temario_text.splitlines() if line.strip()]
    else:
        num_topics_hint = st.number_input("Número aproximado de temas", min_value=3, max_value=15, value=7)

    st.divider()
    st.markdown("**Objetivo de aprendizaje**")
    objetivo_mode = st.radio("¿El objetivo lo das tú o lo propone la IA?", ["Que la IA lo proponga", "Yo doy el objetivo"], key="objetivo_mode")
    user_objetivo = None
    if objetivo_mode == "Yo doy el objetivo":
        user_objetivo = st.text_area("Objetivo de aprendizaje", height=100)

    st.divider()
    st.markdown("**Secciones textuales (opcional)**")
    st.caption(
        "Si algún tema debe reproducirse literal (por ejemplo 'Objetivo' y 'Campo de aplicación' "
        "de una norma), escribe aquí el nombre exacto de esos temas, uno por línea. El resto del "
        "contenido se sintetiza normalmente."
    )
    verbatim_text = st.text_area("Temas que deben ir textuales", height=80, key="verbatim_topics")
    verbatim_topics = {line.strip().lower() for line in verbatim_text.splitlines() if line.strip()}

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        total_slides = st.number_input("Presupuesto de diapositivas de contenido", min_value=5, max_value=200, value=30,
                                        help="No cuenta portadas de tema, dinámicas ni exámenes -- solo diapositivas explicativas.")
    with col2:
        n_exam_inicial = st.number_input("Preguntas examen inicial", min_value=0, max_value=50, value=10)
    with col3:
        n_exam_final = st.number_input("Preguntas examen final", min_value=0, max_value=50, value=10)

    can_continue = bool(source_text) and bool(course_title.strip())
    if st.button("Generar propuesta de temario y objetivo →", type="primary", disabled=not can_continue):
        if _need_api_key():
            return
        data.update({
            "source_text": source_text,
            "course_title": course_title.strip(),
            "user_temario": user_temario,
            "user_objetivo": user_objetivo,
            "verbatim_topics": verbatim_topics,
            "total_slides": int(total_slides),
            "n_exam_inicial": int(n_exam_inicial),
            "n_exam_final": int(n_exam_final),
        })
        with st.spinner("Analizando el material y proponiendo temario + objetivo..."):
            proposal = _call_ai(
                "temario y objetivo", course_ai.propose_temario_and_objetivo,
                source_text, course_title.strip(), user_temario=user_temario, num_topics_hint=num_topics_hint,
            )
        data["temario"] = user_temario or proposal["temario"]
        data["objetivo"] = user_objetivo or proposal["objetivo"]
        st.session_state.cw_step = 1
        st.rerun()


# =====================================================================
# STEP 1 -- review temario + objetivo
# =====================================================================
def _step1_temario_objetivo():
    data = st.session_state.cw_data
    st.subheader("2. Revisa el temario y el objetivo")

    temario_text = st.text_area("Temario (un tema por línea, en orden)", value="\n".join(data["temario"]), height=200)
    objetivo_text = st.text_area("Objetivo de aprendizaje", value=data["objetivo"], height=120)

    if st.button("Continuar a contenido →", type="primary"):
        data["temario"] = [line.strip() for line in temario_text.splitlines() if line.strip()]
        data["objetivo"] = objetivo_text.strip()
        n_topics = len(data["temario"])

        with st.spinner("Repartiendo el presupuesto de diapositivas entre los temas..."):
            allocation = _call_ai(
                "el reparto de diapositivas", course_ai.allocate_slide_budget,
                data["source_text"], data["temario"], data["total_slides"],
            )

        topics = []
        progress = st.progress(0.0, text="Sintetizando contenido por tema...")
        for i, (topic_name, n_slides) in enumerate(zip(data["temario"], allocation)):
            if i > 0:
                time.sleep(2)  # respeta el límite de tokens/minuto del nivel gratuito de Groq
            is_verbatim = topic_name.strip().lower() in data["verbatim_topics"]
            content = _call_ai(
                f"el contenido del tema '{topic_name}'", course_ai.synthesize_topic_content,
                data["source_text"], topic_name, max(1, n_slides), verbatim=is_verbatim,
            )
            topics.append({
                "name": topic_name,
                "title": f"{i + 1}. {topic_name}",
                "content_titles": content["content_titles"],
                "content_slides": content["content_slides"],
                "verbatim": is_verbatim,
            })
            progress.progress((i + 1) / n_topics, text=f"Tema {i + 1} de {n_topics} listo...")
        progress.empty()
        data["topics"] = topics
        st.session_state.cw_step = 2
        st.rerun()


# =====================================================================
# STEP 2 -- review synthesized content per topic
# =====================================================================
def _step2_contenido():
    data = st.session_state.cw_data
    st.subheader("3. Revisa el contenido sintetizado de cada tema")

    for t_idx, topic in enumerate(data["topics"]):
        tag = " (textual)" if topic["verbatim"] else ""
        with st.expander(f"{topic['title']}{tag} — {len(topic['content_slides'])} diapositiva(s)", expanded=False):
            new_titles, new_slides = [], []
            for s_idx in range(len(topic["content_slides"])):
                st.markdown(f"**Diapositiva {s_idx + 1}**")
                title = st.text_input("Subtítulo", value=topic["content_titles"][s_idx], key=f"ct_{t_idx}_{s_idx}")
                bullets_text = st.text_area(
                    "Contenido (un bullet por línea)",
                    value="\n".join(topic["content_slides"][s_idx]),
                    height=120, key=f"cb_{t_idx}_{s_idx}",
                )
                new_titles.append(title)
                new_slides.append([b.strip() for b in bullets_text.splitlines() if b.strip()])
            topic["content_titles"] = new_titles
            topic["content_slides"] = new_slides

    if st.button("Continuar a dinámicas →", type="primary"):
        progress = st.progress(0.0, text="Diseñando una dinámica por tema...")
        n_topics = len(data["topics"])
        for i, topic in enumerate(data["topics"]):
            if i > 0:
                time.sleep(2)  # respeta el límite de tokens/minuto del nivel gratuito de Groq
            proposal = _call_ai(
                f"la dinámica del tema '{topic['name']}'", course_ai.propose_dynamic,
                data["source_text"], topic["name"], topic["content_slides"],
            )
            topic["dynamic_proposal"] = proposal
            progress.progress((i + 1) / n_topics, text=f"Dinámica {i + 1} de {n_topics} lista...")
        progress.empty()
        st.session_state.cw_step = 3
        st.rerun()


# =====================================================================
# STEP 3 -- review dynamics (confirm every answer)
# =====================================================================
def _verdict_options(tipo, categorias):
    if tipo == "verdadero_falso":
        return ["VERDADERO", "FALSO"]
    if tipo == "clasificar" and categorias:
        return list(categorias)
    return None  # caso_breve -> free text, no fixed options


def _step3_dinamicas():
    data = st.session_state.cw_data
    st.subheader("4. Revisa cada dinámica y confirma la respuesta correcta de cada ejercicio")
    st.caption("La IA propone; tú confirmas. Ningún ejercicio se da por bueno sin que elijas o edites su respuesta aquí.")

    for t_idx, topic in enumerate(data["topics"]):
        proposal = topic.get("dynamic_proposal", {})
        with st.expander(f"{topic['title']} — dinámica: {proposal.get('tipo', '?')}", expanded=False):
            instruction = st.text_area("Instrucción de la dinámica", value=proposal.get("instruccion", ""), key=f"dy_instr_{t_idx}")
            tipo = proposal.get("tipo", "caso_breve")
            categorias = proposal.get("categorias", [])
            options = _verdict_options(tipo, categorias)

            confirmed_exercises = []
            for e_idx, ex in enumerate(proposal.get("ejercicios", [])[:4]):
                st.markdown(f"**Ejercicio {e_idx + 1}**")
                statement = st.text_area("Enunciado", value=ex.get("enunciado", ""), height=70, key=f"dy_st_{t_idx}_{e_idx}")
                if options:
                    proposed = ex.get("respuesta_propuesta", "")
                    default_idx = options.index(proposed) if proposed in options else 0
                    verdict = st.radio("Respuesta correcta", options, index=default_idx,
                                        key=f"dy_v_{t_idx}_{e_idx}", horizontal=True)
                else:
                    verdict = st.text_input("Respuesta correcta (breve)", value=ex.get("respuesta_propuesta", "Respuesta"),
                                             key=f"dy_v_{t_idx}_{e_idx}")
                explanation = st.text_area("Explicación", value=ex.get("explicacion", ""), height=70, key=f"dy_e_{t_idx}_{e_idx}")
                confirmed_exercises.append({"statement": statement, "verdict": verdict, "explanation": explanation})

            topic["dynamic_final"] = {"instruction": instruction, "exercises": confirmed_exercises} if confirmed_exercises else None

    if st.button("Continuar a exámenes →", type="primary"):
        with st.spinner("Redactando el examen inicial..."):
            data["exam_inicial_proposal"] = (
                _call_ai("el examen inicial", course_ai.propose_exam,
                         data["source_text"], data["temario"], data["n_exam_inicial"], "inicial")
                if data["n_exam_inicial"] > 0 else []
            )
        time.sleep(2)  # respeta el límite de tokens/minuto del nivel gratuito de Groq
        with st.spinner("Redactando el examen final..."):
            data["exam_final_proposal"] = (
                _call_ai("el examen final", course_ai.propose_exam,
                         data["source_text"], data["temario"], data["n_exam_final"], "final")
                if data["n_exam_final"] > 0 else []
            )
        st.session_state.cw_step = 4
        st.rerun()


# =====================================================================
# STEP 4 -- review exams (confirm every correct answer)
# =====================================================================
def _review_exam(label, proposal_key, final_key):
    data = st.session_state.cw_data
    st.markdown(f"### {label}")
    proposal = data.get(proposal_key, [])
    if not proposal:
        st.caption("(Sin preguntas -- se pidieron 0.)")
        data[final_key] = []
        return
    confirmed = []
    for i, q in enumerate(proposal):
        with st.expander(f"Pregunta {i + 1}: {q['pregunta'][:70]}", expanded=False):
            qtext = st.text_area("Pregunta", value=q["pregunta"], key=f"{proposal_key}_q_{i}", height=60)
            opts = {}
            cols = st.columns(4)
            letters = ["a", "b", "c", "d"]
            for j, letter in enumerate(letters):
                with cols[j]:
                    opts[letter] = st.text_input(f"Opción {letter})", value=q["opciones"][j] if j < len(q["opciones"]) else "",
                                                  key=f"{proposal_key}_o_{i}_{letter}")
            proposed = q.get("respuesta_propuesta", "a")
            correct = st.radio("Respuesta correcta", letters, index=letters.index(proposed) if proposed in letters else 0,
                                format_func=lambda l: f"{l}) {opts[l]}", key=f"{proposal_key}_c_{i}", horizontal=True)
            confirmed.append((qtext, [opts[l] for l in letters], correct))
    data[final_key] = confirmed


def _step4_examenes():
    data = st.session_state.cw_data
    st.subheader("5. Revisa los exámenes y confirma la respuesta correcta de cada pregunta")
    _review_exam("Examen inicial", "exam_inicial_proposal", "exam_inicial_final")
    st.divider()
    _review_exam("Examen final", "exam_final_proposal", "exam_final_final")

    if st.button("Continuar a generar el curso →", type="primary"):
        st.session_state.cw_step = 5
        st.rerun()


# =====================================================================
# STEP 5 -- assemble and download
# =====================================================================
def _step5_generar():
    data = st.session_state.cw_data
    st.subheader("6. Generar la presentación final")
    st.caption("Última revisión antes de armar el archivo. Si algo se ve mal, regresa a un paso anterior.")

    st.write(f"**Curso:** {data['course_title']}")
    st.write(f"**Temas:** {len(data['topics'])}")
    st.write(f"**Preguntas examen inicial:** {len(data.get('exam_inicial_final', []))}")
    st.write(f"**Preguntas examen final:** {len(data.get('exam_final_final', []))}")

    st.divider()
    st.markdown("**Diseño de la presentación**")
    design_mode = st.radio(
        "¿Cómo quieres que se vea?",
        ["Plantilla JASME clásica (requiere que assets/Plantilla_JASME.pptx no haya cambiado de estructura)",
         "Diseño libre (generado desde cero, nunca se rompe, tú eliges los colores)"],
        key="design_mode",
    )
    style = None
    if design_mode.startswith("Diseño libre"):
        import deck_style
        style_source = st.radio("¿De dónde salen los colores/fuente?",
                                 ["Diseño limpio por default", "Copiar el estilo de una plantilla que subas", "Los especifico yo"],
                                 key="style_source")
        if style_source == "Copiar el estilo de una plantilla que subas":
            ref = st.file_uploader("Plantilla de referencia (.pptx)", type=["pptx"], key="style_ref_pptx")
            if ref is not None:
                with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
                    tmp.write(ref.read())
                    style = deck_style.extract_style_from_pptx(tmp.name)
                    os.unlink(tmp.name)
                st.success(f"Estilo extraído: color principal #{style.primary}, fuente {style.heading_font}.")
        elif style_source == "Los especifico yo":
            c1, c2, c3 = st.columns(3)
            with c1:
                primary = st.color_picker("Color principal", "#1E2761")
            with c2:
                accent = st.color_picker("Color de acento", "#C0392B")
            with c3:
                font = st.text_input("Fuente", "Calibri")
            style = deck_style.style_from_manual(primary=primary, accent=accent, heading_font=font, body_font=font)
        else:
            style = deck_style.default_style()

    st.divider()
    if st.button("🚀 Generar presentación", type="primary"):
        course_data = {
            "title": data["course_title"],
            "temario": data["temario"],
            "objetivo": data["objetivo"],
            "topics": [
                {
                    "title": t["title"],
                    "content_titles": t["content_titles"],
                    "content_slides": t["content_slides"],
                    "dynamic": t.get("dynamic_final"),
                }
                for t in data["topics"]
            ],
            "exam_inicial": [(q, opts) for (q, opts, _correct) in data.get("exam_inicial_final", [])],
            "exam_final": [(q, opts) for (q, opts, _correct) in data.get("exam_final_final", [])],
        }
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp_out:
            out_path = tmp_out.name

        if design_mode.startswith("Diseño libre"):
            import deck_style
            from freeform_builder import build_course_freeform
            with st.spinner("Generando la presentación (diseño libre)..."):
                build_course_freeform(out_path, course_data, style or deck_style.default_style())
        else:
            progress_box = st.empty()

            def _cb(msg):
                progress_box.info(msg)

            with st.spinner("Ensamblando la presentación (puede tardar uno o dos minutos)..."):
                build_course(TEMPLATE_PATH, out_path, course_data, progress_callback=_cb)
            progress_box.empty()

        with open(out_path, "rb") as f:
            st.download_button(
                "⬇️ Descargar curso (.pptx)",
                data=f.read(),
                file_name=f"Curso_{data['course_title'][:40].replace(' ', '_')}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        os.unlink(out_path)
        st.success("¡Listo! Revisa la presentación en PowerPoint antes de usarla en un curso real.")

    st.divider()
    st.markdown("**Hojas de respuestas para imprimir (opcional)**")
    st.caption("Genera la hoja de burbujas que tus participantes rellenarán a mano para cada examen.")
    import bubble_sheet
    colA, colB = st.columns(2)
    with colA:
        if data.get("exam_inicial_final") and st.button("📄 Hoja del examen inicial"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                bubble_sheet.generate_bubble_sheet(tmp.name, len(data["exam_inicial_final"]), data["course_title"], "Examen inicial")
                with open(tmp.name, "rb") as f:
                    st.download_button("⬇️ Descargar hoja (inicial)", data=f.read(),
                                        file_name="Hoja_respuestas_examen_inicial.pdf", mime="application/pdf",
                                        key="dl_hoja_inicial")
                os.unlink(tmp.name)
    with colB:
        if data.get("exam_final_final") and st.button("📄 Hoja del examen final"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                bubble_sheet.generate_bubble_sheet(tmp.name, len(data["exam_final_final"]), data["course_title"], "Examen final")
                with open(tmp.name, "rb") as f:
                    st.download_button("⬇️ Descargar hoja (final)", data=f.read(),
                                        file_name="Hoja_respuestas_examen_final.pdf", mime="application/pdf",
                                        key="dl_hoja_final")
                os.unlink(tmp.name)
