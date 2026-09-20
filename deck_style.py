# -*- coding: utf-8 -*-
"""A DeckStyle is just colors + fonts -- the one part of a .pptx that stays
stable across redesigns (it's the OOXML "theme"), unlike slide count or
placeholder layout, which change every time someone edits the template.

Pulling a DeckStyle from an uploaded reference deck, instead of reusing that
deck's actual slides, is what makes the course generator immune to the
"the template changed and now the app is broken" problem: the app never
depends on which slide is in which position ever again.
"""
import re
import zipfile
from dataclasses import dataclass, field


@dataclass
class DeckStyle:
    primary: str = "1E2761"      # dark, used for title slides / section headers
    secondary: str = "F2F2F2"    # light, used for content backgrounds
    accent: str = "C0392B"       # highlights, dynamic verdicts, key numbers
    text_dark: str = "262626"
    text_light: str = "FFFFFF"
    heading_font: str = "Calibri"
    body_font: str = "Calibri"
    background: str = "FFFFFF"   # content-slide background color


def default_style() -> DeckStyle:
    return DeckStyle()


def style_from_manual(primary=None, secondary=None, accent=None, heading_font=None, body_font=None, background=None):
    style = DeckStyle()
    if primary: style.primary = primary.lstrip("#").upper()
    if secondary: style.secondary = secondary.lstrip("#").upper()
    if accent: style.accent = accent.lstrip("#").upper()
    if heading_font: style.heading_font = heading_font
    if body_font: style.body_font = body_font
    if background: style.background = background.lstrip("#").upper()
    return style


_THEME_COLOR_TAGS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"]


def extract_style_from_pptx(pptx_path) -> DeckStyle:
    """Reads ppt/theme/theme1.xml directly from the zip -- no python-pptx
    object model needed, so this works even for decks with unusual/broken
    slide structures, as long as the theme part itself is well-formed."""
    with zipfile.ZipFile(pptx_path) as zf:
        theme_names = [n for n in zf.namelist() if re.match(r"ppt/theme/theme\d*\.xml$", n)]
        if not theme_names:
            return default_style()
        theme_xml = zf.read(sorted(theme_names)[0]).decode("utf-8", errors="replace")

    colors = {}
    for tag in _THEME_COLOR_TAGS:
        m = re.search(rf"<a:{tag}>\s*<a:srgbClr val=\"([0-9A-Fa-f]{{6}})\"", theme_xml)
        if not m:
            m = re.search(rf'<a:{tag}>\s*<a:sysClr val="[^"]*" lastClr="([0-9A-Fa-f]{{6}})"', theme_xml)
        if m:
            colors[tag] = m.group(1).upper()

    heading_font = _first_font(theme_xml, "majorFont") or "Calibri"
    body_font = _first_font(theme_xml, "minorFont") or "Calibri"

    dk1 = colors.get("dk1", "1A1A1A")
    lt1 = colors.get("lt1", "FFFFFF")
    dk2 = colors.get("dk2", colors.get("accent1", "1E2761"))
    accent = colors.get("accent2") or colors.get("accent1") or "C0392B"

    return DeckStyle(
        primary=dk2,
        secondary=lt1,
        accent=accent,
        text_dark=dk1,
        text_light=lt1,
        heading_font=heading_font,
        body_font=body_font,
        background=lt1,
    )


def _first_font(theme_xml, tag):
    m = re.search(rf'<a:{tag}>\s*<a:latin typeface="([^"]+)"', theme_xml)
    return m.group(1) if m else None
