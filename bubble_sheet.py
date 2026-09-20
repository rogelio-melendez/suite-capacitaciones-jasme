# -*- coding: utf-8 -*-
"""Printable bubble-answer-sheet generator + reader (Optical Mark
Recognition). No AI, no internet, no third party -- just geometry and pixel
darkness, using OpenCV. This replaces the old "read circled letters with a
vision model" approach with something that is slower to set up (you must
print this specific sheet) but is free forever and essentially never
misreads a clearly-filled bubble.

Coordinate system: everything is defined in PDF points (72 pt = 1 inch) on
a US Letter page (612 x 792 pt), with the origin at the bottom-left (as
reportlab uses). The reader converts a scanned image to this same point
space via a 4-corner perspective transform, so the two halves of this file
(generate / read) always agree on where every bubble is.
"""
import json
from dataclasses import dataclass, asdict

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter, points
MARGIN = 40.0
MARKER_SIZE = 18.0  # solid black square fiducial markers, in points

# The 4 fiducial marker CENTERS, in point space -- reader aligns to these.
MARKERS = {
    "top_left": (MARGIN + MARKER_SIZE / 2, PAGE_H - MARGIN - MARKER_SIZE / 2),
    "top_right": (PAGE_W - MARGIN - MARKER_SIZE / 2, PAGE_H - MARGIN - MARKER_SIZE / 2),
    "bottom_left": (MARGIN + MARKER_SIZE / 2, MARGIN + MARKER_SIZE / 2),
    "bottom_right": (PAGE_W - MARGIN - MARKER_SIZE / 2, MARGIN + MARKER_SIZE / 2),
}

BUBBLE_RADIUS = 7.0
LETTERS = ["a", "b", "c", "d"]


@dataclass
class BubbleLayout:
    """One row per question; four (x, y) centers, one per option, in points."""
    question_num: int
    label_pos: tuple
    bubble_centers: dict  # {"a": (x,y), "b": (x,y), ...}


def compute_layout(num_questions: int):
    """Deterministic layout shared by the generator and the reader. Splits
    into two columns per page once a page can't fit everything in one."""
    header_h = 150.0
    footer_h = 60.0
    usable_top = PAGE_H - MARGIN - MARKER_SIZE - header_h
    usable_bottom = MARGIN + MARKER_SIZE + footer_h
    row_h = 22.0
    rows_per_col = int((usable_top - usable_bottom) // row_h)

    col_positions = [MARGIN + 30, PAGE_W / 2 + 15]
    bubble_gap = 22.0

    layouts = []
    for i in range(num_questions):
        col = i // rows_per_col
        row = i % rows_per_col
        if col >= 2:
            raise ValueError(
                f"{num_questions} preguntas no caben en una sola hoja con este diseño "
                f"(máximo {rows_per_col * 2}). Genera varias hojas o divide el examen."
            )
        x0 = col_positions[col]
        y = usable_top - row * row_h
        centers = {}
        for j, letter in enumerate(LETTERS):
            centers[letter] = (x0 + 55 + j * bubble_gap, y)
        layouts.append(BubbleLayout(question_num=i + 1, label_pos=(x0, y), bubble_centers=centers))
    return layouts


def layout_to_json(num_questions):
    layouts = compute_layout(num_questions)
    return json.dumps({
        "num_questions": num_questions,
        "markers": MARKERS,
        "bubble_radius": BUBBLE_RADIUS,
        "rows": [asdict(l) for l in layouts],
    })


def generate_bubble_sheet(output_path, num_questions, course_title, exam_label="Examen"):
    """Writes a ready-to-print PDF answer sheet for `num_questions` questions."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black

    c = canvas.Canvas(output_path, pagesize=(PAGE_W, PAGE_H))

    # Fiducial markers (solid black squares)
    for (cx, cy) in MARKERS.values():
        c.setFillColor(black)
        c.rect(cx - MARKER_SIZE / 2, cy - MARKER_SIZE / 2, MARKER_SIZE, MARKER_SIZE, fill=1, stroke=0)

    # Header
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN - MARKER_SIZE - 20, "HOJA DE RESPUESTAS")
    c.setFont("Helvetica", 11)
    c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN - MARKER_SIZE - 38, f"{exam_label} — {course_title}")

    c.setFont("Helvetica", 10)
    c.drawString(MARGIN + 30, PAGE_H - MARGIN - MARKER_SIZE - 65, "Nombre del participante:")
    c.line(MARGIN + 150, PAGE_H - MARGIN - MARKER_SIZE - 67, PAGE_W - MARGIN - 30, PAGE_H - MARGIN - MARKER_SIZE - 67)
    c.drawString(MARGIN + 30, PAGE_H - MARGIN - MARKER_SIZE - 90, "Fecha:")
    c.line(MARGIN + 80, PAGE_H - MARGIN - MARKER_SIZE - 92, MARGIN + 260, PAGE_H - MARGIN - MARKER_SIZE - 92)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(MARGIN + 30, PAGE_H - MARGIN - MARKER_SIZE - 108,
                 "Rellena por completo el círculo de tu respuesta. No hagas otras marcas dentro del recuadro de esquinas.")

    # Column headers (a b c d) once per column
    layouts = compute_layout(num_questions)
    seen_cols = set()
    c.setFont("Helvetica-Bold", 9)
    for l in layouts:
        col_x = l.label_pos[0]
        if col_x not in seen_cols:
            seen_cols.add(col_x)
            for j, letter in enumerate(LETTERS):
                bx, by = l.bubble_centers[letter]
                c.drawCentredString(bx, by + 14, letter.upper())

    # Question rows
    c.setFont("Helvetica", 10)
    for l in layouts:
        c.drawRightString(l.label_pos[0] - 6, l.label_pos[1] - 3, f"{l.question_num}.")
        for letter in LETTERS:
            bx, by = l.bubble_centers[letter]
            c.circle(bx, by, BUBBLE_RADIUS, stroke=1, fill=0)

    c.showPage()
    c.save()
    return output_path


# =====================================================================
# READER (OMR) -- OpenCV only, no AI
# =====================================================================

def _order_corners(pts):
    """pts: 4 (x,y) points, any order -> returns (tl, tr, br, bl)."""
    import numpy as np
    pts = np.array(pts, dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return tl, tr, br, bl


def _find_markers(gray_image):
    """Finds the 4 solid black square fiducials by contour area/shape,
    one per image quadrant (so we never confuse a marker with, say, a
    filled-in bubble near the middle of the page)."""
    import cv2
    h, w = gray_image.shape
    _, thresh = cv2.threshold(gray_image, 100, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (w * h) * 0.0002 or area > (w * h) * 0.01:
            continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / float(ch)
        if 0.7 < aspect < 1.4:  # roughly square
            fill_ratio = area / float(cw * ch)
            if fill_ratio > 0.7:  # solid, not a ring/circle outline
                candidates.append((x + cw / 2, y + ch / 2, area))

    if len(candidates) < 4:
        raise ValueError(
            f"Solo se detectaron {len(candidates)} de las 4 marcas de esquina. "
            "Verifica que la hoja completa (con las 4 esquinas negras) esté visible y bien iluminada en la imagen."
        )

    quadrants = {"top_left": [], "top_right": [], "bottom_left": [], "bottom_right": []}
    for (cx, cy, area) in candidates:
        vert = "top" if cy < h / 2 else "bottom"
        horiz = "left" if cx < w / 2 else "right"
        quadrants[f"{vert}_{horiz}"].append((cx, cy, area))

    picked = {}
    for quad, pts in quadrants.items():
        if not pts:
            raise ValueError(f"No se encontró la marca de esquina '{quad}'. Revisa que la imagen no esté recortada.")
        picked[quad] = max(pts, key=lambda p: p[2])[:2]  # largest candidate in that quadrant
    return picked


def read_bubble_sheet(image_path, num_questions, fill_threshold=0.35, ambiguous_margin=0.12):
    """Reads one scanned/photographed bubble sheet. Returns:
        {"answers": ["a", "", "c", ...],  # "" = blank/unreadable
         "warnings": [...],
         "name_crop_path": "<path to a cropped PNG of the handwritten name, for manual reading>"}
    """
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"No se pudo abrir la imagen: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    markers_px = _find_markers(gray)
    src_pts = np.array([
        markers_px["top_left"], markers_px["top_right"],
        markers_px["bottom_right"], markers_px["bottom_left"],
    ], dtype="float32")

    # Target space: same aspect/scale as the PDF, at WORK_DPI for crisp sampling.
    work_dpi = 200
    scale = work_dpi / 72.0
    dst_pts = np.array([
        [MARKERS["top_left"][0] * scale, (PAGE_H - MARKERS["top_left"][1]) * scale],
        [MARKERS["top_right"][0] * scale, (PAGE_H - MARKERS["top_right"][1]) * scale],
        [MARKERS["bottom_right"][0] * scale, (PAGE_H - MARKERS["bottom_right"][1]) * scale],
        [MARKERS["bottom_left"][0] * scale, (PAGE_H - MARKERS["bottom_left"][1]) * scale],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(gray, M, (int(PAGE_W * scale), int(PAGE_H * scale)))
    _, warped_bin = cv2.threshold(warped, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    layouts = compute_layout(num_questions)
    answers, warnings = [], []
    r_px = int(BUBBLE_RADIUS * scale)

    for l in layouts:
        fills = {}
        for letter, (x, y) in l.bubble_centers.items():
            px, py = int(x * scale), int(PAGE_H * scale - y * scale)
            roi = warped_bin[max(0, py - r_px):py + r_px, max(0, px - r_px):px + r_px]
            fills[letter] = (roi > 0).mean() if roi.size else 0.0

        ranked = sorted(fills.items(), key=lambda kv: kv[1], reverse=True)
        best_letter, best_fill = ranked[0]
        second_fill = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_fill < fill_threshold:
            answers.append("")
            warnings.append(f"Pregunta {l.question_num}: no se detectó ninguna respuesta marcada.")
        elif (best_fill - second_fill) < ambiguous_margin:
            answers.append("")
            warnings.append(f"Pregunta {l.question_num}: parecen marcadas dos opciones a la vez ({best_letter} y {ranked[1][0]}).")
        else:
            answers.append(best_letter)

    # Crop the handwritten name/date area as an image for manual reading.
    name_top = PAGE_H - MARGIN - MARKER_SIZE - 60
    name_bottom = PAGE_H - MARGIN - MARKER_SIZE - 100
    y1 = int((PAGE_H - name_top) * scale)
    y2 = int((PAGE_H - name_bottom) * scale)
    x1, x2 = int(MARGIN * scale), int((PAGE_W - MARGIN) * scale)
    name_crop = warped[y1:y2, x1:x2]
    name_crop_path = str(image_path) + ".name_crop.png"
    cv2.imwrite(name_crop_path, name_crop)

    return {"answers": answers, "warnings": warnings, "name_crop_path": name_crop_path}
