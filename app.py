import os
import tempfile

import pandas as pd
import streamlit as st

from forms_parser import parse_forms_excel
from report_builder import build_workbook
import groq_client
import bubble_sheet
import auth
import supabase_client as sb

st.set_page_config(page_title="JASME Capacitación", page_icon="✅", layout="wide")

auth.require_login()  # blocks everything below until logged in -- no public signup exists


def _ai_ready_banner():
    """Shows a persistent, unmissable banner if the cloud AI key is missing
    -- most confusion here would be 'I forgot to add the Groq key in
    Secrets', so we check this eagerly instead of failing deep inside a
    wizard step."""
    if not groq_client.is_available():
        st.error(
            "🔴 Falta configurar GROQ_API_KEY en Settings → Secrets de esta app en Streamlit "
            "Cloud. Consigue una clave gratis en console.groq.com/keys. Esto solo afecta a "
            "'Crear curso de capacitación' -- calificar exámenes no la necesita."
        )


def load_configs():
    try:
        return sb.list_exam_configs()
    except Exception as e:
        st.error(f"No se pudieron leer las claves de examen guardadas en Supabase: {e}")
        return {}


def rows_to_dataframe(rows, nq):
    cols = ["Modalidad", "Nombre"] + [f"P{i}" for i in range(1, nq + 1)]
    return pd.DataFrame(rows, columns=cols)


def dataframe_to_rows(df):
    return df.fillna("").astype(str).values.tolist()


LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "jasme_logo.png")
st.image(LOGO, width=220)
st.title("JASME Capacitación")

auth.logout_button()

menu_options = ["Calificar exámenes", "Crear / editar clave de un examen", "Crear curso de capacitación"]
if auth.is_admin():
    menu_options.append("⚙️ Administrar usuarios")
modo = st.sidebar.radio("¿Qué quieres hacer?", menu_options)
st.sidebar.divider()

if modo == "⚙️ Administrar usuarios":
    auth.render_admin_panel()
    st.stop()

# =====================================================================
# MODO: crear curso de capacitación completo (temario, contenido, dinámicas, exámenes)
# =====================================================================
if modo == "Crear curso de capacitación":
    _ai_ready_banner()
    import course_wizard
    course_wizard.render()
    st.stop()

# =====================================================================
# MODO: crear o editar la clave de un examen (captura manual, sin IA)
# =====================================================================
if modo == "Crear / editar clave de un examen":
    st.header("Crear la clave de respuestas de un examen nuevo")
    st.caption(
        "Escribe las preguntas y opciones del examen (o pégalas desde un documento). "
        "Esto no necesita IA -- es una captura directa."
    )

    if "new_exam_n" not in st.session_state:
        st.session_state.new_exam_n = 10

    title = st.text_input("Título / nombre del examen", key="new_exam_title")
    n_questions = st.number_input("Número de preguntas", min_value=1, max_value=60,
                                   value=st.session_state.new_exam_n, key="new_exam_n")

    st.subheader("Preguntas")
    st.caption("Escribe cada pregunta, sus 4 opciones, y marca cuál es la correcta.")
    questions, options_list, answer_key = [], [], []
    missing = []
    for i in range(int(n_questions)):
        with st.expander(f"Pregunta {i + 1}", expanded=(i == 0)):
            qtext = st.text_area("Pregunta", key=f"newq_text_{i}", height=60)
            cols = st.columns(4)
            opts = {}
            for j, letter in enumerate(["a", "b", "c", "d"]):
                with cols[j]:
                    opts[letter] = st.text_input(f"Opción {letter})", key=f"newq_opt_{i}_{letter}")
            correct = st.radio("¿Cuál opción es la correcta?", ["a", "b", "c", "d"],
                                format_func=lambda l: f"{l}) {opts[l]}", key=f"newq_correct_{i}",
                                horizontal=True, index=None)
            questions.append(qtext)
            options_list.append(opts)
            answer_key.append(correct or "")
            if not qtext.strip() or not correct:
                missing.append(i + 1)

    st.subheader("Criterio de aprobación")
    c1, c2 = st.columns(2)
    with c1:
        op = st.selectbox("Operador", [">=", ">", "<=", "<", "=="], index=0)
    with c2:
        threshold = st.number_input("Puntaje mínimo (aciertos)", min_value=0, max_value=int(n_questions), value=min(8, int(n_questions)))

    if missing:
        st.warning(f"Falta completar la pregunta y/o la respuesta correcta de: {missing}")

    save_clicked = st.button("Guardar esta clave de examen", type="primary", disabled=bool(missing) or not title.strip())
    if save_clicked:
        nom_id = title.strip().upper().replace(" ", "-")
        new_config = {
            "nom_id": nom_id, "title": title.strip(),
            "approve_operator": op, "approve_threshold": int(threshold),
            "questions": questions, "options": options_list, "answer_key": answer_key,
        }
        try:
            sb.save_exam_config(new_config)
            st.success(f"Clave guardada como '{title}'. Ya está disponible en 'Calificar exámenes' "
                       f"para todo tu equipo (queda guardada de forma permanente en Supabase).")
            st.session_state["_just_saved_config"] = new_config
        except Exception as e:
            st.error(f"No se pudo guardar en Supabase: {e}")

    saved_config = st.session_state.get("_just_saved_config")
    if saved_config:
        st.divider()
        st.subheader("Generar hoja de respuestas para imprimir")
        st.caption("Genera la hoja de burbujas que tus participantes van a rellenar a mano.")
        if st.button("📄 Generar PDF de hoja de respuestas"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                bubble_sheet.generate_bubble_sheet(tmp.name, len(saved_config["questions"]), saved_config["title"])
                tmp_path = tmp.name
            with open(tmp_path, "rb") as f:
                st.download_button("⬇️ Descargar hoja de respuestas (PDF)", data=f.read(),
                                    file_name=f"Hoja_respuestas_{saved_config['nom_id']}.pdf", mime="application/pdf")
            os.unlink(tmp_path)

    st.stop()

# =====================================================================
# MODO: calificar exámenes (hojas de burbujas escaneadas / fotos, y Excel de Forms)
# =====================================================================
st.caption(
    "Sube las fotos/escaneos de las hojas de respuestas (burbujas) y/o el Excel de respuestas "
    "remotas (Google/Microsoft Forms). La app lee las respuestas, te deja revisarlas y genera el "
    "Excel final con el formato JASME."
)

configs = load_configs()

with st.sidebar:
    st.header("1. Examen")
    exam_choice = st.selectbox("Norma / examen", list(configs.keys()) + ["➕ Subir configuración nueva (.json)"])
    if exam_choice == "➕ Subir configuración nueva (.json)":
        uploaded_cfg = st.file_uploader("Config JSON (preguntas, opciones, clave)", type=["json"])
        config = json.load(uploaded_cfg) if uploaded_cfg else None
    else:
        config = configs[exam_choice]

    st.divider()
    st.header("2. Archivos")
    sheet_files = st.file_uploader(
        "Hojas de respuestas escaneadas o fotografiadas (una imagen por participante)",
        type=["png", "jpg", "jpeg"], accept_multiple_files=True,
    )
    forms_file = st.file_uploader("Respuestas remotas (Excel de Forms)", type=["xlsx", "xls"])

    st.divider()
    extract_clicked = st.button("Extraer respuestas", type="primary", use_container_width=True,
                                 disabled=(config is None or (not sheet_files and forms_file is None)))

if config is None:
    st.info("Selecciona o sube la configuración del examen en la barra lateral para empezar.")
    st.stop()

nq = len(config["questions"])

if "rows" not in st.session_state:
    st.session_state.rows = []
    st.session_state.warnings = []
    st.session_state.name_crops = {}

if extract_clicked:
    all_rows, all_warnings = [], []
    name_crops = {}

    if forms_file is not None:
        with st.spinner("Leyendo respuestas remotas del Excel..."):
            rows, warnings = parse_forms_excel(forms_file, config, modalidad="Remoto")
            all_rows += rows
            all_warnings += warnings

    if sheet_files:
        progress = st.progress(0.0, text="Leyendo hojas de respuestas...")
        for i, sheet_file in enumerate(sheet_files):
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(sheet_file.name)[-1], delete=False) as tmp:
                tmp.write(sheet_file.read())
                tmp_path = tmp.name
            try:
                result = bubble_sheet.read_bubble_sheet(tmp_path, nq)
                placeholder_name = f"(revisar imagen: {sheet_file.name})"
                all_rows.append(["Presencial", placeholder_name] + result["answers"])
                name_crops[placeholder_name] = result["name_crop_path"]
                for w in result["warnings"]:
                    all_warnings.append(f"{sheet_file.name}: {w}")
            except Exception as e:
                all_warnings.append(f"{sheet_file.name}: no se pudo leer ({e}). Revisar manualmente.")
                all_rows.append(["Presencial", f"(revisar imagen: {sheet_file.name})"] + [""] * nq)
            progress.progress((i + 1) / len(sheet_files), text=f"Hoja {i + 1} de {len(sheet_files)}...")
        progress.empty()

    st.session_state.rows = all_rows
    st.session_state.warnings = all_warnings
    st.session_state.name_crops = name_crops

if st.session_state.rows:
    st.subheader("Revisa y corrige las respuestas antes de generar el reporte")
    st.caption(
        "Los nombres de los participantes que escaneaste aparecen como '(revisar imagen: archivo.png)' "
        "-- ábrelos abajo para ver el recorte de su nombre escrito a mano y escríbelo en la tabla."
    )
    if st.session_state.name_crops:
        with st.expander("🖼️ Ver los nombres escritos a mano", expanded=False):
            for label, crop_path in st.session_state.name_crops.items():
                st.write(label)
                if os.path.exists(crop_path):
                    st.image(crop_path)
    if st.session_state.warnings:
        with st.expander(f"⚠️ {len(st.session_state.warnings)} elementos a revisar", expanded=True):
            for w in st.session_state.warnings:
                st.write("- " + w)

    df = rows_to_dataframe(st.session_state.rows, nq)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, height=420)

    st.subheader("Generar reporte final")
    if st.button("Generar Excel", type="primary"):
        rows = dataframe_to_rows(edited_df)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_out:
            out_path = tmp_out.name
        build_workbook(config, rows, out_path)
        with open(out_path, "rb") as f:
            st.download_button(
                "⬇️ Descargar Excel",
                data=f.read(),
                file_name=f"Reporte_Examen_{config['nom_id']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        os.unlink(out_path)
        st.success("Reporte generado. Descárgalo arriba.")
else:
    st.info("Sube al menos un archivo y da clic en 'Extraer respuestas' para comenzar.")
