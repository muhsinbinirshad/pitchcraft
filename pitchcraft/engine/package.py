"""Load and save .docx packages, and normalize fragmented runs.

The package is kept as raw bytes for every part except word/document.xml,
which is parsed with lxml. Saving rewrites only document.xml, so headers,
footers, styles, numbering, media and themes stay byte-identical.
"""

from __future__ import annotations

import copy
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .ns import XML_SPACE, w

DOC_PART = "word/document.xml"
_PARSER = etree.XMLParser(huge_tree=True, remove_blank_text=False)


class PackageError(Exception):
    pass


def _is_aux(name: str) -> bool:
    """Header and footer parts, which hold editable text too."""
    base = name.rsplit("/", 1)[-1]
    return name.startswith("word/") and name.count("/") == 1 and base.endswith(".xml") and (
        base.startswith("header") or base.startswith("footer"))


@dataclass
class DocxPackage:
    parts: dict[str, bytes]
    order: list[str]
    root: etree._Element
    infos: dict[str, zipfile.ZipInfo] = field(default_factory=dict)
    aux: dict[str, etree._Element] = field(default_factory=dict)

    # ---------- io ----------
    @classmethod
    def load(cls, src: str | Path | bytes) -> "DocxPackage":
        data = src if isinstance(src, bytes) else Path(src).read_bytes()
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise PackageError("Not a valid .docx (zip) file") from e
        parts: dict[str, bytes] = {}
        order: list[str] = []
        infos: dict[str, zipfile.ZipInfo] = {}
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue  # folder entries: Word online rejects them
            if ".." in name.split("/") or name.startswith("/"):
                raise PackageError(f"Unsafe path in package: {name}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                continue  # symlink entry, untrusted
            parts[name] = zf.read(info)
            order.append(name)
            infos[name] = info
        if DOC_PART not in parts:
            raise PackageError("Package has no word/document.xml")
        root = etree.fromstring(parts[DOC_PART], _PARSER)
        aux = {}
        for name in order:
            if _is_aux(name):
                try:
                    aux[name] = etree.fromstring(parts[name], _PARSER)
                except etree.XMLSyntaxError:
                    continue
        return cls(parts=parts, order=order, root=root, infos=infos, aux=aux)

    def roots(self) -> dict[str, etree._Element]:
        """All editable XML roots: the document body part first, then headers/footers."""
        return {DOC_PART: self.root, **self.aux}

    def to_bytes(self) -> bytes:
        xml = etree.tostring(
            self.root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in self.order:
                if name == DOC_PART:
                    payload = xml
                elif name in self.aux:
                    payload = etree.tostring(self.aux[name], xml_declaration=True, encoding="UTF-8", standalone=True)
                else:
                    payload = self.parts[name]
                zf.writestr(name, payload)
        return buf.getvalue()

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(self.to_bytes())

    def clone(self) -> "DocxPackage":
        return DocxPackage(
            parts=dict(self.parts),
            order=list(self.order),
            root=copy.deepcopy(self.root),
            infos=dict(self.infos),
            aux={k: copy.deepcopy(v) for k, v in self.aux.items()},
        )

    @property
    def body(self) -> etree._Element:
        b = self.root.find(w("body"))
        if b is None:
            raise PackageError("document.xml has no w:body")
        return b


# ---------- normalization ----------

_MERGEABLE_CHILDREN = {w("rPr"), w("t")}


def _run_key(r: etree._Element) -> bytes | None:
    """Formatting key for a run, or None if the run holds more than text."""
    for child in r:
        if child.tag not in _MERGEABLE_CHILDREN:
            return None
    rpr = r.find(w("rPr"))
    return b"" if rpr is None else etree.tostring(rpr)


def merge_runs(root: etree._Element) -> int:
    """Merge adjacent text-only runs with identical formatting.

    Word splits visible phrases over many runs (spell-check marks, revision
    ids). Merging them makes text searchable without changing rendering.
    Returns the number of runs removed.
    """
    removed = 0
    for pe in list(root.iter(w("proofErr"))):
        pe.getparent().remove(pe)
    for p in root.iter(w("p")):
        prev = None
        prev_key = None
        for child in list(p):
            if child.tag != w("r"):
                prev = None
                continue
            key = _run_key(child)
            if key is not None and prev is not None and key == prev_key:
                t_prev = prev.find(w("t"))
                t_cur = child.find(w("t"))
                if t_cur is not None:
                    if t_prev is None:
                        t_prev = etree.SubElement(prev, w("t"))
                        t_prev.text = ""
                    t_prev.text = (t_prev.text or "") + (t_cur.text or "")
                    t_prev.set(XML_SPACE, "preserve")
                p.remove(child)
                removed += 1
                continue
            prev = child if key is not None else None
            prev_key = key
    return removed
