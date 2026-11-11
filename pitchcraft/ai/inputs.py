"""Turn uploaded attachments into Claude content blocks plus plain text.

The plain text is also used by the numbers audit as a source corpus.
"""

from __future__ import annotations

import base64
import mimetypes
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..engine import DocxPackage, build_outline, merge_runs

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
TEXT_EXT = {".txt", ".md", ".eml", ".csv", ".tsv", ".json", ".xml", ".html", ".htm"}
SHEET_EXT = {".xlsx", ".xlsm"}
LEGACY_SHEET_EXT = {".xls", ".ods"}  # read natively (xlrd / ODF XML), LibreOffice as a fallback
SLIDE_EXT = {".pptx"}  # read natively, slide by slide
CONVERT_EXT = {".ppt", ".odp", ".doc", ".odt", ".rtf"}  # converted to PDF with LibreOffice
MAX_SHEET_ROWS = 2000
MAX_SHEET_COLS = 60
MAX_TEXT_CHARS = 400_000


@dataclass
class PreparedInputs:
    blocks: list[dict] = field(default_factory=list)
    text: str = ""
    names: list[str] = field(default_factory=list)


def _media_type(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"


def _pdf_text(path: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                              text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _xlsx_text(path: Path) -> str:
    """Read an .xlsx/.xlsm workbook into tab-separated text, one block per sheet (values, not formulas)."""
    import re
    import zipfile

    from lxml import etree

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    parser = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            sst = etree.fromstring(z.read("xl/sharedStrings.xml"), parser)
            for si in sst.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        wb = etree.fromstring(z.read("xl/workbook.xml"), parser)
        rels = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"), parser)
        target = {r.get("Id"): r.get("Target") for r in rels}
        blocks = []
        for sh in wb.findall("m:sheets/m:sheet", ns):
            if sh.get("state") in ("hidden", "veryHidden"):
                continue
            t = target.get(sh.get(f"{{{ns['r']}}}id"), "")
            part = "xl/" + t.lstrip("/").removeprefix("xl/")
            if part not in names:
                continue
            ws = etree.fromstring(z.read(part), parser)
            lines = []
            for row in ws.iter(f"{{{ns['m']}}}row"):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", ns):
                    ref = c.get("r") or ""
                    col_letters = re.match(r"[A-Z]+", ref)
                    col = 0
                    for ch in (col_letters.group(0) if col_letters else ""):
                        col = col * 26 + (ord(ch) - 64)
                    col = col - 1 if col else len(cells)
                    if col >= MAX_SHEET_COLS:
                        continue
                    typ = c.get("t")
                    v = c.find("m:v", ns)
                    if typ == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                        val = shared[int(v.text)]
                    elif typ == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                    else:
                        val = v.text if v is not None and v.text is not None else ""
                    cells[col] = " ".join(val.split())
                if any(x.strip() for x in cells.values()):
                    width = max(cells) + 1
                    lines.append("\t".join(cells.get(i, "") for i in range(width)).rstrip("\t"))
                if len(lines) >= MAX_SHEET_ROWS:
                    lines.append(f"(sheet truncated after {MAX_SHEET_ROWS} rows)")
                    break
            if lines:
                blocks.append(f"## Sheet: {sh.get('name')}\n" + "\n".join(lines))
    return "\n\n".join(blocks)


def _rows_to_text(name: str, rows: list[list[str]]) -> str:
    lines = []
    for r in rows[:MAX_SHEET_ROWS]:
        cells = [" ".join(str(c).split()) for c in r[:MAX_SHEET_COLS]]
        if any(cells):
            lines.append("\t".join(cells).rstrip("\t"))
    if len(rows) > MAX_SHEET_ROWS:
        lines.append(f"(sheet truncated after {MAX_SHEET_ROWS} rows)")
    return f"## Sheet: {name}\n" + "\n".join(lines) if lines else ""


def _xls_text(path: Path) -> str:
    """Old binary Excel (.xls)."""
    import xlrd

    book = xlrd.open_workbook(str(path), on_demand=True)
    blocks = []
    for sh in book.sheets():
        if getattr(sh, "visibility", 0):
            continue
        rows = []
        for i in range(min(sh.nrows, MAX_SHEET_ROWS + 1)):
            row = []
            for v in sh.row_values(i):
                if isinstance(v, float) and v.is_integer():
                    v = int(v)
                row.append("" if v is None else str(v))
            rows.append(row)
        if (b := _rows_to_text(sh.name, rows)):
            blocks.append(b)
    return "\n\n".join(blocks)


def _ods_text(path: Path) -> str:
    """OpenDocument spreadsheet (.ods): content.xml tables."""
    import zipfile

    from lxml import etree

    T = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    X = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    parser = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("content.xml"), parser)
    blocks = []
    for tbl in root.iter(f"{{{T}}}table"):
        rows = []
        for tr in tbl.iter(f"{{{T}}}table-row"):
            rep_r = min(int(tr.get(f"{{{T}}}number-rows-repeated", "1")), 50)
            row = []
            for tc in tr:
                if tc.tag not in (f"{{{T}}}table-cell", f"{{{T}}}covered-table-cell"):
                    continue
                rep_c = min(int(tc.get(f"{{{T}}}number-columns-repeated", "1")), MAX_SHEET_COLS)
                val = "\n".join("".join(p.itertext()) for p in tc.iter(f"{{{X}}}p"))
                row += [val] * rep_c
            while row and not row[-1].strip():
                row.pop()
            for _ in range(rep_r if row else 1):
                rows.append(row)
            if len(rows) > MAX_SHEET_ROWS:
                break
        if (b := _rows_to_text(tbl.get(f"{{{T}}}name", "Sheet"), rows)):
            blocks.append(b)
    return "\n\n".join(blocks)


def _pptx_text(path: Path) -> str:
    """PowerPoint (.pptx): text of each slide, in slide order, plus speaker notes."""
    import re
    import zipfile

    from lxml import etree

    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    parser = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        out = []
        for n in slides:
            root = etree.fromstring(z.read(n), parser)
            paras = ["".join(t.text or "" for t in p.iter(f"{{{A}}}t")) for p in root.iter(f"{{{A}}}p")]
            text = "\n".join(x for x in paras if x.strip())
            num = re.findall(r"\d+", n)[-1]
            notes = f"ppt/notesSlides/notesSlide{num}.xml"
            if notes in names:
                nroot = etree.fromstring(z.read(notes), parser)
                ntext = "\n".join("".join(t.text or "" for t in p.iter(f"{{{A}}}t")) for p in nroot.iter(f"{{{A}}}p"))
                ntext = "\n".join(x for x in ntext.splitlines() if x.strip() and not x.strip().isdigit())
                if ntext:
                    text += f"\n(notes) {ntext}"
            out.append(f"## Slide {num}\n{text}")
    return "\n\n".join(out)


def _office_to_pdf(path: Path, fmt: str = "pdf") -> Path | None:
    """Convert an office file with LibreOffice (to PDF for Claude to read, or to xlsx for sheets)."""
    import tempfile

    from ..engine.render import find_soffice

    exe = find_soffice()
    if not exe:
        return None
    out = Path(tempfile.mkdtemp(prefix="pf-conv-"))
    with tempfile.TemporaryDirectory() as profile:
        try:
            subprocess.run([exe, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", fmt,
                            "--outdir", str(out), str(path)], capture_output=True, timeout=180,
                           env={**__import__("os").environ, "HOME": profile})
        except (OSError, subprocess.SubprocessError):
            return None
    res = out / (path.stem + "." + fmt)
    return res if res.exists() else None


def prepare_inputs(files: list[Path]) -> PreparedInputs:
    out = PreparedInputs()
    texts: list[str] = []
    for f in files:
        mt = _media_type(f)
        ext = f.suffix.lower()
        out.names.append(f.name)
        if mt in IMAGE_TYPES:
            out.blocks.append({"type": "text", "text": f"Attachment (image): {f.name}"})
            out.blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mt,
                           "data": base64.standard_b64encode(f.read_bytes()).decode()},
            })
        elif ext == ".pdf":
            out.blocks.append({"type": "text", "text": f"Attachment (PDF): {f.name}"})
            out.blocks.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(f.read_bytes()).decode()},
            })
            texts.append(_pdf_text(f))
        elif ext == ".docx":
            pkg = DocxPackage.load(f)
            merge_runs(pkg.root)
            t = "\n".join(b.get("text", "") if b["kind"] == "p" else
                          "\n".join(" | ".join(c["text"] for c in r["cells"]) for r in b["rows"])
                          for b in build_outline(pkg.body).blocks)
            texts.append(t)
            out.blocks.append({"type": "text",
                               "text": f"<attachment name=\"{f.name}\" type=\"docx\">\n{t[:MAX_TEXT_CHARS]}\n</attachment>"})
        elif ext in SHEET_EXT or ext in LEGACY_SHEET_EXT:
            try:
                if ext in SHEET_EXT:
                    t = _xlsx_text(f)
                elif ext == ".xls":
                    t = _xls_text(f)
                else:
                    t = _ods_text(f)
                if not t:  # unusual file: let LibreOffice try
                    conv = _office_to_pdf(f, "xlsx")
                    t = _xlsx_text(conv) if conv else ""
                t = t[:MAX_TEXT_CHARS]
            except Exception:  # noqa: BLE001 - a damaged workbook should not stop the request
                t = ""
            if t:
                texts.append(t)
                out.blocks.append({"type": "text", "text": f"<attachment name=\"{f.name}\" type=\"spreadsheet\" format=\"tab-separated, one block per sheet\">\n{t}\n</attachment>"})
            else:
                out.blocks.append({"type": "text", "text": f"Attachment {f.name} is a spreadsheet that could not be read or is empty."})
        elif ext in SLIDE_EXT:
            try:
                t = _pptx_text(f)[:MAX_TEXT_CHARS]
            except Exception:  # noqa: BLE001
                t = ""
            if t:
                texts.append(t)
                out.blocks.append({"type": "text", "text": f"<attachment name=\"{f.name}\" type=\"slides\">\n{t}\n</attachment>"})
            else:
                out.blocks.append({"type": "text", "text": f"Attachment {f.name} has no readable slide text."})
        elif ext in CONVERT_EXT:
            pdf = _office_to_pdf(f)
            if pdf is not None:
                out.blocks.append({"type": "text", "text": f"Attachment ({ext[1:]} converted to PDF): {f.name}"})
                out.blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                                  "data": base64.standard_b64encode(pdf.read_bytes()).decode()}})
                texts.append(_pdf_text(pdf))
            else:
                out.blocks.append({"type": "text", "text": f"Attachment {f.name} could not be converted (LibreOffice is needed) and was skipped."})
        elif ext in TEXT_EXT or mt.startswith("text/"):
            t = f.read_text(errors="replace")[:MAX_TEXT_CHARS]
            texts.append(t)
            out.blocks.append({"type": "text",
                               "text": f"<attachment name=\"{f.name}\">\n{t}\n</attachment>"})
        else:
            out.blocks.append({"type": "text",
                               "text": f"Attachment {f.name} has an unsupported type and was skipped."})
    out.text = "\n".join(texts)
    return out
