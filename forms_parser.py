"""Parses a Google Forms / Microsoft Forms Excel export of exam responses.

Assumes: one row per respondent, one column with their name, and (in order)
one column per question holding the full text of the option they chose
(this is how Google/Microsoft Forms export multiple-choice answers).
Timestamp / score / email columns are auto-skipped.

Returns rows in the same shape report_builder.build_workbook expects:
    [modalidad, nombre, ans1, ans2, ..., ansN]  (ansN = lowercase letter or '')
plus a parallel list of per-cell confidence flags, so the UI can highlight
anything that needs a human check.
"""
import difflib
import re
import pandas as pd

SKIP_HEADER_PATTERNS = [
    "marca temporal", "timestamp", "puntuaci", "score", "calificaci",
    "correo electr", "email", "hora de inicio", "hora de finalizaci",
    "id de respuesta", "empresa donde", "nombre de la empresa", "fecha del curso",
]
NAME_HEADER_PATTERNS = ["nombre", "participante", "apellido", "name"]


def _normalize(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"[^\w\sáéíóúñ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _best_letter(cell_text, options_dict, min_ratio=0.55):
    raw = str(cell_text or "").strip()
    prefix_match = re.match(r"^\s*([abcdABCD])\s*[\.\)]", raw)
    if prefix_match:
        letter = prefix_match.group(1).lower()
        if letter in options_dict:
            return letter, 1.0

    norm_cell = _normalize(cell_text)
    if not norm_cell:
        return "", 0.0
    best_letter, best_ratio = "", 0.0
    for letter, opt_text in options_dict.items():
        norm_opt = _normalize(opt_text)
        if not norm_opt:
            continue
        if norm_cell == norm_opt:
            return letter, 1.0
        if norm_opt in norm_cell or norm_cell in norm_opt:
            ratio = 0.95
        else:
            ratio = difflib.SequenceMatcher(None, norm_cell, norm_opt).ratio()
        if ratio > best_ratio:
            best_letter, best_ratio = letter, ratio
    if best_ratio < min_ratio:
        return "", best_ratio
    return best_letter, best_ratio


def parse_forms_excel(file_path_or_buffer, config, modalidad="Remoto"):
    """Returns (rows, warnings)
    rows: list of [modalidad, nombre, ans1..ansN]
    warnings: list of human-readable strings for low-confidence matches
    """
    df = pd.read_excel(file_path_or_buffer)
    columns = list(df.columns)

    name_col = None
    for col in columns:
        low = str(col).lower()
        if any(p in low for p in NAME_HEADER_PATTERNS):
            name_col = col
            break
    if name_col is None:
        # fall back: first column that isn't an obvious skip column
        for col in columns:
            low = str(col).lower()
            if not any(p in low for p in SKIP_HEADER_PATTERNS):
                name_col = col
                break

    answer_cols = []
    for col in columns:
        if col == name_col:
            continue
        low = str(col).lower()
        if any(p in low for p in SKIP_HEADER_PATTERNS):
            continue
        answer_cols.append(col)

    nq = len(config["questions"])
    answer_cols = answer_cols[:nq]  # keep only the first N question-like columns, in order

    rows = []
    warnings = []
    for idx, record in df.iterrows():
        name = str(record.get(name_col, "")).strip()
        if not name or name.lower() == "nan":
            continue
        answers = []
        for qi, col in enumerate(answer_cols):
            cell_val = record.get(col, "")
            letter, ratio = _best_letter(cell_val, config["options"][qi])
            answers.append(letter)
            if ratio < 0.8:
                warnings.append(
                    f"Fila {idx+2}, '{name}', pregunta {qi+1}: no se reconoció con certeza "
                    f"la respuesta ('{cell_val}'). Revisar manualmente."
                )
        while len(answers) < nq:
            answers.append("")
        rows.append([modalidad, name] + answers)

    return rows, warnings
