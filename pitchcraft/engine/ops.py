"""Deterministic edit operations.

The AI never writes XML. It returns a list of operations that point at ids
from the outline. Each new element is a deep copy of an existing element of
the same kind ("like"), so fonts, spacing, numbering, borders and shading all
come from the base document. Only text changes.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from lxml import etree
from pydantic import BaseModel, Field

from .ns import XML_SPACE, w, w14
from .outline import build_package_outline, para_text
from .package import DocxPackage

OpName = Literal["replace_text", "set_text", "insert_after", "insert_rows", "delete", "insert_table", "delete_range"]


class InsertItem(BaseModel):
    like: str = Field(description="Id of an existing paragraph or table to copy formatting from")
    text: Optional[str] = Field(default=None, description="Text for a copied paragraph. Use **x** for bold segments when the source mixes bold and normal runs")
    new_id: Optional[str] = Field(default=None, description="Optional id so later ops can refer to this new block, e.g. NEW1")


class Op(BaseModel):
    op: OpName
    find: Optional[str] = None
    replace: Optional[str] = None
    expect: Optional[int] = None
    target: Optional[str] = None
    anchor: Optional[str] = None
    like: Optional[str] = None
    items: Optional[list[InsertItem]] = None
    rows: Optional[list[list[str]]] = None
    targets: Optional[list[str]] = None
    new_id: Optional[str] = None
    reason: str = ""
    evidence: str = ""


class OpError(Exception):
    pass


@dataclass
class OpResult:
    index: int
    ok: bool
    error: str | None = None
    new_texts: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    package: DocxPackage
    results: list[OpResult]
    new_texts: list[str]

    @property
    def errors(self) -> list[OpResult]:
        return [r for r in self.results if not r.ok]


# ---------------- element helpers ----------------

_STRIP_TAGS = {
    w("bookmarkStart"),
    w("bookmarkEnd"),
    w("commentRangeStart"),
    w("commentRangeEnd"),
}


def clean_clone(el: etree._Element) -> etree._Element:
    """Deep copy without ids that must stay unique (paraId, bookmarks, comments)."""
    if el.find(f".//{w('drawing')}") is not None or el.find(f".//{w('pict')}") is not None:
        raise OpError("Cannot copy an element that contains an image")
    c = copy.deepcopy(el)
    for node in list(c.iter()):
        if not isinstance(node.tag, str):
            continue
        for attr in (w14("paraId"), w14("textId")):
            if attr in node.attrib:
                del node.attrib[attr]
        if node.tag in _STRIP_TAGS:
            node.getparent().remove(node)
        elif node.tag == w("r") and node.find(w("commentReference")) is not None:
            node.getparent().remove(node)
    return c


def _own_runs(p: etree._Element) -> list[etree._Element]:
    """Runs whose nearest paragraph is p (skips text boxes)."""
    out = []
    for r in p.iter(w("r")):
        anc = r.getparent()
        while anc is not None and anc.tag != w("p"):
            anc = anc.getparent()
        if anc is p:
            out.append(r)
    return out


def _new_run_like(p: etree._Element, src: etree._Element | None) -> etree._Element:
    """New run with the formatting of run `src`, or of the paragraph mark if there is no run."""
    r = etree.Element(w("r"))
    if src is not None:
        rpr = src.find(w("rPr"))
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
    else:
        ppr = p.find(w("pPr"))
        mark = ppr.find(w("rPr")) if ppr is not None else None
        if mark is not None:
            nr = etree.SubElement(r, w("rPr"))
            for child in mark:
                if child.tag in (w("ins"), w("del"), w("moveFrom"), w("moveTo"), w("rPrChange")):
                    continue
                nr.append(copy.deepcopy(child))
    return r


def _is_bold(r: etree._Element) -> bool:
    rpr = r.find(w("rPr"))
    if rpr is None:
        return False
    b = rpr.find(w("b"))
    return b is not None and b.get(w("val")) not in ("0", "false", "off")


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)


def _segments(text: str) -> list[tuple[bool, str]]:
    segs: list[tuple[bool, str]] = []
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            segs.append((False, text[pos : m.start()]))
        segs.append((True, m.group(1)))
        pos = m.end()
    if pos < len(text):
        segs.append((False, text[pos:]))
    return segs


def _text_run(r: etree._Element, text: str) -> None:
    for child in list(r):
        if child.tag != w("rPr"):
            r.remove(child)
    t = etree.SubElement(r, w("t"))
    t.text = text
    t.set(XML_SPACE, "preserve")


def set_paragraph_text(p: etree._Element, text: str) -> None:
    """Replace a paragraph's text, keeping its run formatting.

    Plain text goes into the first text run. Text with **bold** markers uses
    the paragraph's own bold and normal run formats.
    """
    text = re.sub(r"[\r\n]+", " ", text)
    runs = [r for r in _own_runs(p) if r.find(w("t")) is not None]
    if any(r.find(f".//{w('drawing')}") is not None for r in _own_runs(p)):
        raise OpError("Paragraph contains an image; edit its text with replace_text instead")
    segs = _segments(text) if "**" in text else [(None, text)]

    bold_run = next((r for r in runs if _is_bold(r)), None)
    plain_run = next((r for r in runs if not _is_bold(r)), None)
    first_run = runs[0] if runs else None

    # where new runs go: position of the first text run, else end of paragraph
    insert_parent, insert_index = p, len(p)
    if runs:
        insert_parent = runs[0].getparent()
        insert_index = list(insert_parent).index(runs[0])
    for r in runs:
        r.getparent().remove(r)
    # drop empty formatting-only runs left behind (but keep breaks/tabs/fields)
    for r in _own_runs(p):
        if all(c.tag == w("rPr") for c in r):
            r.getparent().remove(r)
    if insert_index > len(insert_parent):
        insert_index = len(insert_parent)

    new_runs = []
    for bold, seg in segs:
        if not seg:
            continue
        if bold is None:
            src = first_run
        elif bold:
            src = bold_run if bold_run is not None else first_run
        else:
            src = plain_run if plain_run is not None else first_run
        r = _new_run_like(p, src)
        if bold and bold_run is None:
            rp = r.find(w("rPr"))
            if rp is None:
                rp = etree.SubElement(r, w("rPr"))
                r.insert(0, rp)
            if rp.find(w("b")) is None:
                rp.insert(0, etree.Element(w("b")))
        _text_run(r, seg)
        new_runs.append(r)
    for i, r in enumerate(new_runs):
        insert_parent.insert(insert_index + i, r)


def set_cell_text(tc: etree._Element, text: str) -> None:
    paras = tc.findall(w("p"))
    if not paras:
        raise OpError("Cell has no paragraph")
    set_paragraph_text(paras[0], text)
    for extra in paras[1:]:
        tc.remove(extra)


def _vmerge(tc: etree._Element) -> etree._Element | None:
    tcpr = tc.find(w("tcPr"))
    return tcpr.find(w("vMerge")) if tcpr is not None else None


# ---------------- replace across runs ----------------

def _para_t_nodes(p: etree._Element) -> list[etree._Element]:
    nodes = []
    for r in _own_runs(p):
        nodes.extend(r.findall(w("t")))
    return nodes


def count_occurrences(root: etree._Element, find: str) -> int:
    n = 0
    for p in root.iter(w("p")):
        n += "".join(t.text or "" for t in _para_t_nodes(p)).count(find)
    return n


def replace_in_paragraph(p: etree._Element, find: str, repl: str) -> int:
    nodes = _para_t_nodes(p)
    texts = [t.text or "" for t in nodes]
    full = "".join(texts)
    if find not in full:
        return 0
    # char index -> (node index, offset)
    bounds = []
    pos = 0
    for i, s in enumerate(texts):
        bounds.append((pos, pos + len(s)))
        pos += len(s)

    def locate(ci: int, is_end: bool) -> tuple[int, int]:
        for i, (a, b) in enumerate(bounds):
            if is_end and a < ci <= b:
                return i, ci - a
            if not is_end and a <= ci < b:
                return i, ci - a
        return len(bounds) - 1, len(texts[-1])

    starts = []
    i = full.find(find)
    while i != -1:
        starts.append(i)
        i = full.find(find, i + len(find))
    for s in reversed(starts):
        e = s + len(find)
        si, so = locate(s, False)
        ei, eo = locate(e, True)
        if si == ei:
            t = texts[si]
            texts[si] = t[:so] + repl + t[eo:]
        else:
            texts[si] = texts[si][:so] + repl
            for k in range(si + 1, ei):
                texts[k] = ""
            texts[ei] = texts[ei][eo:]
    for node, t in zip(nodes, texts):
        node.text = t
        node.set(XML_SPACE, "preserve")
    return len(starts)


# ---------------- plan application ----------------

class Applier:
    def __init__(self, pkg: DocxPackage):
        self.pkg = pkg
        self.registry = dict(build_package_outline(pkg).registry)

    def get(self, ref: str | None, what: str) -> etree._Element:
        if not ref:
            raise OpError(f"Missing {what}")
        el = self.registry.get(ref)
        if el is None:
            raise OpError(f"Unknown id '{ref}' for {what}")
        if _locate(el, self.pkg) is None:
            raise OpError(f"Id '{ref}' was deleted by an earlier operation")
        return el

    def register_table(self, tid: str, tbl: etree._Element) -> None:
        self.registry[tid] = tbl
        for i, tr in enumerate(tbl.findall(w("tr"))):
            self.registry[f"{tid}.R{i}"] = tr
            for j, tc in enumerate(tr.findall(w("tc"))):
                self.registry[f"{tid}.R{i}.C{j}"] = tc

    # each op returns the new texts it wrote
    def replace_text(self, op: Op) -> list[str]:
        if not op.find:
            raise OpError("replace_text needs 'find'")
        if op.replace is None:
            raise OpError("replace_text needs 'replace'")
        n = sum(count_occurrences(r, op.find) for r in self.pkg.roots().values())
        if n == 0:
            raise OpError(f"Text not found: {op.find[:80]!r}")
        if op.expect is not None and n != op.expect:
            raise OpError(f"Expected {op.expect} match(es) of {op.find[:60]!r}, found {n}")
        for root in self.pkg.roots().values():
            for p in list(root.iter(w("p"))):
                replace_in_paragraph(p, op.find, op.replace)
        return [op.replace]

    def set_text(self, op: Op) -> list[str]:
        el = self.get(op.target, "target")
        if op.replace is None:
            raise OpError("set_text needs 'replace' (the new text)")
        if el.tag == w("p"):
            set_paragraph_text(el, op.replace)
        elif el.tag == w("tc"):
            if (vm := _vmerge(el)) is not None and vm.get(w("val")) != "restart":
                raise OpError("Cell is merged with the cell above; set the top cell instead")
            set_cell_text(el, op.replace)
        else:
            raise OpError("set_text target must be a paragraph or a table cell")
        return [op.replace]

    def insert_after(self, op: Op) -> list[str]:
        anchor = self.get(op.anchor, "anchor")
        if anchor.tag not in (w("p"), w("tbl")):
            raise OpError("insert_after anchor must be a paragraph or table")
        if not op.items:
            raise OpError("insert_after needs 'items'")
        texts = []
        cur = anchor
        for item in op.items:
            src = self.get(item.like, "item.like")
            if src.tag == w("p"):
                if item.text is None:
                    raise OpError(f"Item copying {item.like} needs 'text'")
                node = clean_clone(src)
                set_paragraph_text(node, item.text)
                texts.append(item.text)
            elif src.tag == w("tbl"):
                node = clean_clone(src)
            else:
                raise OpError(f"'{item.like}' is not a paragraph or table")
            cur.addnext(node)
            cur = node
            if item.new_id:
                if item.new_id in self.registry:
                    raise OpError(f"new_id '{item.new_id}' already used")
                if node.tag == w("tbl"):
                    self.register_table(item.new_id, node)
                else:
                    self.registry[item.new_id] = node
        return texts

    def insert_rows(self, op: Op) -> list[str]:
        tbl = self.get(op.target, "target table")
        if tbl.tag != w("tbl"):
            raise OpError("insert_rows target must be a table id")
        after = self.get(op.anchor, "anchor row")
        like = self.get(op.like, "like row")
        if after.tag != w("tr") or like.tag != w("tr"):
            raise OpError("insert_rows anchor and like must be row ids (T<n>.R<i>)")
        if after.getparent() is not tbl:
            raise OpError("Anchor row is not in the target table")
        if not op.rows:
            raise OpError("insert_rows needs 'rows'")
        texts = []
        cur = after
        for row in op.rows:
            tr = clean_clone(like)
            cells = tr.findall(w("tc"))
            if len(row) != len(cells):
                raise OpError(
                    f"Row has {len(row)} values but the copied row has {len(cells)} cells"
                )
            for tc, val in zip(cells, row):
                vm = _vmerge(tc)
                if vm is not None:
                    if vm.get(w("val")) == "restart":
                        del vm.attrib[w("val")]  # copies continue the merge above
                    if val.strip():
                        raise OpError("A value was given for a vertically merged cell; leave it empty")
                    continue
                set_cell_text(tc, val)
                if val.strip():
                    texts.append(val)
            cur.addnext(tr)
            cur = tr
        return texts

    def delete(self, op: Op) -> list[str]:
        if not op.targets:
            raise OpError("delete needs 'targets'")
        els = [self.get(t, "delete target") for t in op.targets]
        for el in els:
            if el.tag == w("tr"):
                self._delete_row(el)
            elif el.tag in (w("p"), w("tbl")):
                parent = el.getparent()
                if parent.tag == w("tc") and len(parent.findall(w("p"))) <= 1 and el.tag == w("p"):
                    raise OpError("Cannot delete the only paragraph of a cell")
                parent.remove(el)
            else:
                raise OpError("delete targets must be paragraphs, tables or rows")
        return []

    # ---- new table with its own shape, styled like an existing one ----
    def insert_table(self, op: Op) -> list[str]:
        """Build a table with any number of columns and rows, copying the look of table `like`.

        rows[0] is the header row. The header copies the like-table's first row,
        body rows copy its second row (or the first if it has one row). The total
        width is kept and split evenly across the new columns.
        """
        anchor = self.get(op.anchor, "anchor")
        if anchor.tag not in (w("p"), w("tbl")):
            raise OpError("insert_table anchor must be a paragraph or table")
        src = self.get(op.like, "like table")
        if src.tag != w("tbl"):
            raise OpError("insert_table like must be a table id")
        if not op.rows or not op.rows[0]:
            raise OpError("insert_table needs rows (the first row is the header)")
        ncols = max(len(r) for r in op.rows)
        if ncols > 20:
            raise OpError("A table can have at most 20 columns")
        rows = [list(r) + [""] * (ncols - len(r)) for r in op.rows]
        src_rows = src.findall(w("tr"))
        if not src_rows:
            raise OpError("The like table has no rows")
        head_tpl = src_rows[0]
        body_tpl = src_rows[1] if len(src_rows) > 1 else src_rows[0]

        tbl = etree.Element(w("tbl"))
        tblpr = src.find(w("tblPr"))
        if tblpr is not None:
            tbl.append(clean_clone(tblpr))
        total = 0
        grid_src = src.find(w("tblGrid"))
        if grid_src is not None:
            for gc in grid_src.findall(w("gridCol")):
                try:
                    total += int(float(gc.get(w("w"), "0")))
                except ValueError:
                    pass
        if not total:
            total = 9000
        col_w = total // ncols
        grid = etree.SubElement(tbl, w("tblGrid"))
        for _ in range(ncols):
            gc = etree.SubElement(grid, w("gridCol"))
            gc.set(w("w"), str(col_w))

        def make_row(tpl: etree._Element, values: list[str]) -> etree._Element:
            tr = clean_clone(tpl)
            cells = tr.findall(w("tc"))
            if not cells:
                raise OpError("The like table's rows have no cells")
            cell_tpl = cells[0]
            for c in cells:
                tr.remove(c)
            for v in values:
                tc = copy.deepcopy(cell_tpl)
                tcpr = tc.find(w("tcPr"))
                if tcpr is not None:
                    for tag in ("gridSpan", "vMerge", "hMerge"):
                        for x in tcpr.findall(w(tag)):
                            tcpr.remove(x)
                    tcw = tcpr.find(w("tcW"))
                    if tcw is None:
                        tcw = etree.Element(w("tcW"))
                        tcpr.insert(0, tcw)
                    tcw.set(w("w"), str(col_w))
                    tcw.set(w("type"), "dxa")
                for t in list(tc.findall(w("tbl"))):
                    tc.remove(t)
                if tc.find(w("p")) is None:
                    etree.SubElement(tc, w("p"))
                set_cell_text(tc, v)
                tr.append(tc)
            return tr

        texts = []
        tbl.append(make_row(head_tpl, rows[0]))
        texts += [v for v in rows[0] if v.strip()]
        for r in rows[1:]:
            tbl.append(make_row(body_tpl, r))
            texts += [v for v in r if v.strip()]
        anchor.addnext(tbl)
        if op.new_id:
            if op.new_id in self.registry:
                raise OpError(f"new_id '{op.new_id}' already used")
            self.register_table(op.new_id, tbl)
        return texts

    # ---- remove a whole stretch of the document (sections, pages) ----
    def delete_range(self, op: Op) -> list[str]:
        """Delete every body block from `anchor` to `target` inclusive (same container).

        Paragraphs that carry a section break keep their section properties (their
        text is cleared instead), so page size, orientation, headers and footers of
        the remaining sections are not disturbed.
        """
        first = self.get(op.anchor, "anchor (first block)")
        last = self.get(op.target, "target (last block)")
        parent = first.getparent()
        if last.getparent() is not parent:
            raise OpError("anchor and target must be blocks at the same level (both top-level, or in the same cell)")
        sibs = [c for c in parent if c.tag in (w("p"), w("tbl"), w("sdt"))]
        try:
            i, j = sibs.index(first), sibs.index(last)
        except ValueError:
            raise OpError("anchor and target must be paragraphs or tables")
        if j < i:
            raise OpError("target comes before anchor")
        doomed = sibs[i:j + 1]
        remaining = [c for c in parent if c.tag in (w("p"), w("tbl"))]
        if parent.tag == w("tc") and len([c for c in remaining if c not in doomed and c.tag == w("p")]) == 0:
            raise OpError("Cannot delete every paragraph of a cell")
        for el in doomed:
            if el.tag == w("p") and el.find(f"{w('pPr')}/{w('sectPr')}") is not None:
                for r in _own_runs(el):
                    r.getparent().remove(r)
                continue
            parent.remove(el)
        return []

    def _delete_row(self, tr: etree._Element) -> None:
        tbl = tr.getparent()
        rows = tbl.findall(w("tr"))
        idx = rows.index(tr)
        nxt = rows[idx + 1] if idx + 1 < len(rows) else None
        for j, tc in enumerate(tr.findall(w("tc"))):
            vm = _vmerge(tc)
            if vm is None or vm.get(w("val")) != "restart" or nxt is None:
                continue
            ncells = nxt.findall(w("tc"))
            if j < len(ncells) and (nvm := _vmerge(ncells[j])) is not None and nvm.get(w("val")) != "restart":
                nvm.set(w("val"), "restart")
                target = ncells[j]
                for p in target.findall(w("p")):
                    target.remove(p)
                for p in tc.findall(w("p")):
                    target.append(p)
        if len(rows) <= 1:
            raise OpError("Cannot delete the last row of a table")
        tbl.remove(tr)


def _index_path(el: etree._Element, root: etree._Element) -> tuple[int, ...] | None:
    path = []
    cur = el
    while cur is not root:
        parent = cur.getparent()
        if parent is None:
            return None  # detached (deleted earlier)
        path.append(parent.index(cur))
        cur = parent
    return tuple(reversed(path))


def _resolve(root: etree._Element, path: tuple[int, ...]) -> etree._Element:
    cur = root
    for i in path:
        cur = cur[i]
    return cur


def _locate(el: etree._Element, pkg: DocxPackage) -> tuple[str, tuple[int, ...]] | None:
    """(part name, index path) of an element still attached to one of the package roots."""
    for name, root in pkg.roots().items():
        path = _index_path(el, root)
        if path is not None:
            return name, path
    return None


def apply_plan(base: DocxPackage, ops: list[Op], skip_failed: bool = True) -> ApplyResult:
    """Apply ops in order to a copy of base.

    A failing op is rolled back completely (no partial edit) and reported.
    """
    pkg = base.clone()
    ap = Applier(pkg)
    results: list[OpResult] = []
    all_texts: list[str] = []
    for i, op in enumerate(ops):
        snap_root = copy.deepcopy(pkg.root)
        snap_aux = {k: copy.deepcopy(v) for k, v in pkg.aux.items()}
        locs = {k: _locate(el, pkg) for k, el in ap.registry.items()}
        try:
            texts = getattr(ap, op.op)(op)
            results.append(OpResult(index=i, ok=True, new_texts=texts))
            all_texts.extend(texts)
        except OpError as e:
            if not skip_failed:
                raise
            pkg.root, pkg.aux = snap_root, snap_aux
            ap.pkg = pkg
            roots = pkg.roots()
            ap.registry = {k: _resolve(roots[loc[0]], loc[1]) for k, loc in locs.items() if loc is not None}
            results.append(OpResult(index=i, ok=False, error=str(e)))
    return ApplyResult(package=pkg, results=results, new_texts=all_texts)


def plain_text(root) -> str:
    """Text of one XML root, or of a whole package (body, headers and footers)."""
    roots = root.roots().values() if isinstance(root, DocxPackage) else [root]
    return "\n".join(para_text(p) for r in roots for p in r.iter(w("p")))
