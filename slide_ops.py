"""Low-level OOXML slide duplication, self-contained (no dependency on any
external toolchain) so this works on a bare Streamlit server.

Ported from first principles: a .pptx is a zip of XML parts. Duplicating a
slide means: copy its slideN.xml (+ .rels minus any notes-slide link),
register it in [Content_Types].xml, add a relationship in
presentation.xml.rels, and insert a <p:sldId> into <p:sldIdLst>.
"""
import re
import shutil
import zipfile
from pathlib import Path


def extract_pptx(pptx_path, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pptx_path) as zf:
        zf.extractall(dest_dir)
    return dest_dir


def repack_pptx(unpacked_dir, out_path):
    unpacked_dir = Path(unpacked_dir)
    out_path = Path(out_path)
    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(unpacked_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(unpacked_dir))
    return out_path


NOTES_SLIDE_TYPE_RE = re.compile(r"""Type=["'][^"']*/relationships/notesSlide["']""")
RELATIONSHIP_RE = re.compile(r"<Relationship\b[^>]*?(?:/>|>.*?</Relationship\s*>)", re.DOTALL)
SLIDE_ID_MIN = 256
SLIDE_ID_MAX = 2147483647


def _get_next_slide_number(slides_dir: Path) -> int:
    existing = [int(m.group(1)) for f in slides_dir.glob("slide*.xml")
                if (m := re.match(r"slide(\d+)\.xml", f.name))]
    return max(existing) + 1 if existing else 1


def _find_slide_relationship(pres_rels: str, slide_name: str):
    for m in re.finditer(r"<Relationship\b[^>]*>", pres_rels):
        element = m.group(0)
        if re.search(rf'Target="(?:/ppt/)?slides/{re.escape(slide_name)}"', element):
            id_match = re.search(r'\bId="([^"]+)"', element)
            if id_match:
                return id_match.group(1)
    return None


def _rid_for_slide(unpacked_dir: Path, slide_name: str) -> str:
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
    rid = _find_slide_relationship(pres_rels_path.read_text(encoding="utf-8"), slide_name)
    if not rid:
        raise ValueError(f"{slide_name} has no relationship in presentation.xml.rels")
    return rid


def _add_to_content_types(unpacked_dir: Path, dest: str):
    p = unpacked_dir / "[Content_Types].xml"
    xml = p.read_text(encoding="utf-8")
    override = (f'<Override PartName="/ppt/slides/{dest}" '
                f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
    if f'PartName="/ppt/slides/{dest}"' not in xml:
        xml = xml.replace("</Types>", f"  {override}\n</Types>")
        p.write_text(xml, encoding="utf-8")


def _add_to_presentation_rels(unpacked_dir: Path, dest: str) -> str:
    p = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
    xml = p.read_text(encoding="utf-8")
    existing = _find_slide_relationship(xml, dest)
    if existing:
        return existing
    pres_xml = (unpacked_dir / "ppt" / "presentation.xml").read_text(encoding="utf-8")
    used = {int(n) for n in re.findall(r'\bId="rId(\d+)"', xml)}
    used |= {int(n) for n in re.findall(r'\br:id="rId(\d+)"', pres_xml)}
    rid = f"rId{max(used) + 1 if used else 1}"
    new_rel = (f'<Relationship Id="{rid}" '
               f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
               f'Target="slides/{dest}"/>')
    xml = xml.replace("</Relationships>", f"  {new_rel}\n</Relationships>")
    p.write_text(xml, encoding="utf-8")
    return rid


def _get_next_slide_id(unpacked_dir: Path) -> int:
    xml = (unpacked_dir / "ppt" / "presentation.xml").read_text(encoding="utf-8")
    used = {int(m) for m in re.findall(r'<p:sldId[^>]*\bid="(\d+)"', xml)}
    candidate = max((i for i in used if i >= SLIDE_ID_MIN), default=SLIDE_ID_MIN - 1) + 1
    if candidate <= SLIDE_ID_MAX and candidate not in used:
        return candidate
    for i in range(SLIDE_ID_MIN, SLIDE_ID_MAX + 1):
        if i not in used:
            return i
    raise RuntimeError("No slide id available")


def _insert_into_sld_id_lst(unpacked_dir: Path, slide_id: int, rid: str, after_rid=None):
    p = unpacked_dir / "ppt" / "presentation.xml"
    xml = p.read_text(encoding="utf-8")
    entry = f'<p:sldId id="{slide_id}" r:id="{rid}"/>'
    if after_rid:
        open_tag = re.search(rf'<p:sldId\b[^>]*r:id="{re.escape(after_rid)}"[^>]*>', xml)
        if not open_tag:
            raise ValueError(f"{after_rid} not found in sldIdLst")
        end = open_tag.end()
        if not open_tag.group(0).endswith("/>"):
            close = xml.find("</p:sldId>", end)
            end = close + len("</p:sldId>")
        xml = xml[:end] + entry + xml[end:]
    else:
        xml = xml.replace("</p:sldIdLst>", f"{entry}</p:sldIdLst>", 1)
    p.write_text(xml, encoding="utf-8")


def duplicate_slide(unpacked_dir, source: str, after: str = None) -> str:
    """Duplicate ppt/slides/<source> (e.g. 'slide19.xml'), optionally inserting
    right after ppt/slides/<after>. Returns the new slide's filename."""
    unpacked_dir = Path(unpacked_dir)
    slides_dir = unpacked_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    source_path = slides_dir / source
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    dest = f"slide{_get_next_slide_number(slides_dir)}.xml"
    after_rid = _rid_for_slide(unpacked_dir, after) if after else None

    shutil.copy2(source_path, slides_dir / dest)

    source_rels = rels_dir / f"{source}.rels"
    if source_rels.exists():
        dest_rels = rels_dir / f"{dest}.rels"
        shutil.copy2(source_rels, dest_rels)
        content = dest_rels.read_text(encoding="utf-8")
        content = RELATIONSHIP_RE.sub(
            lambda m: "" if NOTES_SLIDE_TYPE_RE.search(m.group(0)) else m.group(0), content
        )
        dest_rels.write_text(content, encoding="utf-8")

    _add_to_content_types(unpacked_dir, dest)
    rid = _add_to_presentation_rels(unpacked_dir, dest)
    slide_id = _get_next_slide_id(unpacked_dir)
    _insert_into_sld_id_lst(unpacked_dir, slide_id, rid, after_rid)
    return dest


def remove_slides(unpacked_dir, filenames):
    """Remove a set of slideN.xml from <p:sldIdLst> (their files are left on
    disk; call prune_unreferenced_slides() afterwards to delete them)."""
    unpacked_dir = Path(unpacked_dir)
    pres_rels = (unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels").read_text(encoding="utf-8")
    rids = {f: _find_slide_relationship(pres_rels, f) for f in filenames}
    p = unpacked_dir / "ppt" / "presentation.xml"
    xml = p.read_text(encoding="utf-8")
    for fname, rid in rids.items():
        if not rid:
            continue
        xml = re.sub(rf'<p:sldId\b[^>]*r:id="{re.escape(rid)}"[^>]*/>', "", xml)
    p.write_text(xml, encoding="utf-8")


def get_ordered_slide_files(unpacked_dir):
    """Read presentation.xml's <p:sldIdLst> (in order) and resolve each r:id to
    its slideN.xml filename via presentation.xml.rels. This is the ground
    truth for slide order -- python-pptx's own `part.partname` renumbers
    parts on load and cannot be used to recover the original filename."""
    unpacked_dir = Path(unpacked_dir)
    pres_xml = (unpacked_dir / "ppt" / "presentation.xml").read_text(encoding="utf-8")
    pres_rels = (unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels").read_text(encoding="utf-8")
    rid_to_file = {}
    for m in re.finditer(r"<Relationship\b[^>]*>", pres_rels):
        el = m.group(0)
        idm = re.search(r'Id="([^"]+)"', el)
        tgt = re.search(r'Target="(?:/ppt/)?slides/(slide\d+\.xml)"', el)
        if idm and tgt:
            rid_to_file[idm.group(1)] = tgt.group(1)
    ordered_rids = re.findall(r'<p:sldId\b[^>]*r:id="(rId\d+)"', pres_xml)
    return [rid_to_file[r] for r in ordered_rids if r in rid_to_file]


def prune_unreferenced_slides(unpacked_dir):
    """Delete slideN.xml (+rels) files no longer listed in <p:sldIdLst>, and
    any now-orphaned media. Call once, after all remove_slides() calls."""
    unpacked_dir = Path(unpacked_dir)
    slides_dir = unpacked_dir / "ppt" / "slides"
    pres_rels = (unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels").read_text(encoding="utf-8")
    pres_xml = (unpacked_dir / "ppt" / "presentation.xml").read_text(encoding="utf-8")
    referenced_rids = set(re.findall(r'<p:sldId\b[^>]*r:id="(rId\d+)"', pres_xml))

    referenced_files = set()
    for m in re.finditer(r"<Relationship\b[^>]*>", pres_rels):
        el = m.group(0)
        idm = re.search(r'Id="([^"]+)"', el)
        tgt = re.search(r'Target="(?:/ppt/)?slides/(slide\d+\.xml)"', el)
        if idm and tgt and idm.group(1) in referenced_rids:
            referenced_files.add(tgt.group(1))

    all_slide_files = {f.name for f in slides_dir.glob("slide*.xml")}
    orphans = all_slide_files - referenced_files
    used_media = set()
    for fname in referenced_files:
        rels_path = slides_dir / "_rels" / f"{fname}.rels"
        if rels_path.exists():
            for m in re.finditer(r'Target="\.\./media/([^"]+)"', rels_path.read_text(encoding="utf-8")):
                used_media.add(m.group(1))

    for fname in orphans:
        (slides_dir / fname).unlink(missing_ok=True)
        (slides_dir / "_rels" / f"{fname}.rels").unlink(missing_ok=True)
        ct_path = unpacked_dir / "[Content_Types].xml"
        ct = ct_path.read_text(encoding="utf-8")
        ct = ct.replace(
            f'<Override PartName="/ppt/slides/{fname}" '
            f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>',
            "",
        )
        ct_path.write_text(ct, encoding="utf-8")

    media_dir = unpacked_dir / "ppt" / "media"
    if media_dir.exists():
        for media_file in media_dir.iterdir():
            if media_file.name not in used_media:
                # Only prune if truly unused (defensive: skip if referenced elsewhere,
                # e.g. by slide masters/layouts) -- check broadly first.
                referenced_elsewhere = False
                for rels_file in (unpacked_dir / "ppt").rglob("_rels/*.rels"):
                    if media_file.name in rels_file.read_text(encoding="utf-8"):
                        referenced_elsewhere = True
                        break
                if not referenced_elsewhere:
                    media_file.unlink()
