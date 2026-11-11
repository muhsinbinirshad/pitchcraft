"""Structural checks for a .docx offered as a style template.

These run before any AI call and catch files that are not usable proposals:
broken packages, macro-enabled files, near-empty documents, documents with
no headings (nothing to copy section styles from).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .ns import w
from .outline import build_package_outline
from .package import DocxPackage, PackageError, merge_runs

MIN_WORDS = 300
MIN_PARAGRAPHS = 25


@dataclass
class Inspection:
    ok: bool                      # usable as a template (no hard failures)
    errors: list[str] = field(default_factory=list)    # hard failures
    warnings: list[str] = field(default_factory=list)  # usable but worth knowing
    stats: dict = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _heading_level(style: str | None, p) -> int | None:
    if style:
        s = style.lower().replace(" ", "")
        if s.startswith("heading") and s[7:].isdigit():
            return int(s[7:])
        if s == "title":
            return 0
    ppr = p.find(w("pPr"))
    ol = ppr.find(w("outlineLvl")) if ppr is not None else None
    if ol is not None:
        try:
            return int(ol.get(w("val"))) + 1
        except (TypeError, ValueError):
            return None
    return None


def inspect_docx(data: bytes) -> Inspection:
    try:
        pkg = DocxPackage.load(data)
    except PackageError as e:
        return Inspection(ok=False, errors=[str(e)])
    except Exception:  # noqa: BLE001 - any parse failure means unusable
        return Inspection(ok=False, errors=["The file could not be read as a Word document"])

    errors, warnings = [], []
    names = set(pkg.parts)
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        errors.append("The document contains macros. Save it as a normal .docx without macros.")
    rels = b"".join(v for k, v in pkg.parts.items() if k.endswith(".rels"))
    if b'TargetMode="External"' in rels and b"attachedTemplate" in rels:
        warnings.append("The document links to an external Word template.")
    if "word/styles.xml" not in names:
        warnings.append("The document has no style definitions, so new content may look plain.")

    for r in pkg.roots().values():
        merge_runs(r)
    outline = build_package_outline(pkg)
    paras = [b for b in outline.blocks if b["kind"] == "p" and not b.get("part")]
    tables = [b for b in outline.blocks if b["kind"] == "table" and not b.get("part")]
    words = sum(len(b["text"].split()) for b in paras)
    words += sum(len(c["text"].split()) for t in tables for r in t["rows"] for c in r["cells"])
    headings = []
    for b in paras:
        lvl = _heading_level(b.get("style"), outline.registry[b["id"]])
        if lvl is not None and b["text"].strip() and not b.get("toc"):
            headings.append(b["text"].strip()[:120])
    lists = sum(1 for b in paras if b.get("list"))
    images = sum(1 for b in paras if b.get("image"))

    if words < MIN_WORDS:
        errors.append(f"Only {words} words of text. A proposal template needs real content to copy styles from.")
    if len([b for b in paras if b["text"].strip()]) < MIN_PARAGRAPHS:
        warnings.append("Very few paragraphs; there may not be enough examples of each style.")
    if not headings:
        errors.append("No headings found. Section headings are needed so new sections can copy their style.")
    elif len(headings) < 3:
        warnings.append("Only a few headings found.")
    if not tables:
        warnings.append("No tables found. New tables (pricing, timelines) can't copy an existing table style.")
    if not lists:
        warnings.append("No bulleted or numbered lists found.")

    return Inspection(
        ok=not errors, errors=errors, warnings=warnings, headings=headings[:40],
        stats={"words": words, "paragraphs": len(paras), "headings": len(headings), "tables": len(tables),
               "lists": lists, "images": images, "headers_footers": len(pkg.aux)},
    )
