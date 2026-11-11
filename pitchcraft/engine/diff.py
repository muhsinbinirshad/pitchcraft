"""Build a highlighted "changes" copy of a document for review (QA/QC).

The comparison follows the document's structure instead of flattening it:

  body blocks   paragraphs are compared with paragraphs, tables with tables
  tables        rows are matched by content; matched rows are compared cell by
                cell; removed rows are shown struck through in place
  cells         the paragraphs inside a cell are compared word by word

So removed text always appears where it was (a removed table row inside its
table, a removed paragraph between paragraphs), never inside an unrelated
cell. Inserted words get a green background, removed words are put back in
red strikethrough, whole new paragraphs/rows/tables are tinted. The copy is
for viewing only; it is rendered to PDF and never replaces the real document.
"""

from __future__ import annotations

import copy
import difflib
import re
from dataclasses import dataclass
from typing import Callable, Sequence

from lxml import etree

from .ns import XML_SPACE, w
from .outline import para_text
from .package import DocxPackage

ADD_FILL = "C6EFCE"   # green background for new text
DEL_FILL = "FFD7D5"   # light red background for removed text
DEL_COLOR = "B3261E"
MAX_REMOVED_SHOWN = 8
_TOKEN = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)
_WORDS = re.compile(r"\w+", re.UNICODE)


@dataclass
class DiffStats:
    changed: int = 0
    added: int = 0
    removed: int = 0


# ---------------------------------------------------------------- alignment

def align(a: Sequence[str], b: Sequence[str], sim: Callable[[int, int], float], threshold: float = 0.5,
          window: int = 40, pair_floor: float = 0.2) -> list[tuple[str, int | None, int | None]]:
    """Monotonic alignment of two sequences.

    Exact matches anchor the alignment (difflib); inside each non-matching
    region, every new item is paired with the most similar later old item
    above `threshold`. Returns ops: ("eq"|"chg", i, j), ("del", i, None), ("ins", None, j).
    """
    ops: list[tuple[str, int | None, int | None]] = []
    sm = difflib.SequenceMatcher(a=list(a), b=list(b), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops += [("eq", i1 + k, j1 + k) for k in range(i2 - i1)]
            continue
        # same number of items on both sides and each pair related: an in-place edit, pair in order
        if i2 - i1 == j2 - j1 and all(sim(i1 + k, j1 + k) >= pair_floor for k in range(i2 - i1)):
            ops += [("chg", i1 + k, j1 + k) for k in range(i2 - i1)]
            continue
        pending = list(range(i1, i2))
        for j in range(j1, j2):
            best, best_score = None, threshold
            for i in pending[:window]:
                sc = sim(i, j)
                if sc > best_score:
                    best, best_score = i, sc
            if best is None:
                ops.append(("ins", None, j))
                continue
            for i in [x for x in pending if x < best]:
                ops.append(("del", i, None))
            pending = [x for x in pending if x > best]
            ops.append(("chg", best, j))
        ops += [("del", i, None) for i in pending]
    return ops


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s)


def text_similarity(x: str, y: str) -> float:
    if not x.strip() and not y.strip():
        return 1.0
    if not x.strip() or not y.strip():
        return 0.0
    # compare real words only; shared spaces and punctuation must not make unrelated text look similar
    wx, wy = _WORDS.findall(x.lower()), _WORDS.findall(y.lower())
    if not wx or not wy:
        return 1.0 if x.strip() == y.strip() else 0.0
    sm = difflib.SequenceMatcher(a=wx, b=wy, autojunk=False)
    return sm.ratio() if sm.real_quick_ratio() >= 0.3 else 0.0


# ---------------------------------------------------------------- run helpers

def _own_runs(p: etree._Element) -> list[etree._Element]:
    out = []
    for r in p.iter(w("r")):
        anc = r.getparent()
        while anc is not None and anc.tag != w("p"):
            anc = anc.getparent()
        if anc is p and r.find(w("t")) is not None:
            out.append(r)
    return out


def _ensure_rpr(r: etree._Element) -> etree._Element:
    rpr = r.find(w("rPr"))
    if rpr is None:
        rpr = etree.Element(w("rPr"))
        r.insert(0, rpr)
    return rpr


def _shade(r: etree._Element, fill: str) -> None:
    rpr = _ensure_rpr(r)
    for old in rpr.findall(w("shd")) + rpr.findall(w("highlight")):
        rpr.remove(old)
    shd = etree.SubElement(rpr, w("shd"))
    shd.set(w("val"), "clear")
    shd.set(w("color"), "auto")
    shd.set(w("fill"), fill)


def _strike(r: etree._Element) -> None:
    rpr = _ensure_rpr(r)
    for tag in ("strike", "dstrike", "color"):
        for old in rpr.findall(w(tag)):
            rpr.remove(old)
    etree.SubElement(rpr, w("strike"))
    c = etree.SubElement(rpr, w("color"))
    c.set(w("val"), DEL_COLOR)
    _shade(r, DEL_FILL)


def _deleted_run(like: etree._Element | None, text: str) -> etree._Element:
    r = etree.Element(w("r"))
    if like is not None and like.find(w("rPr")) is not None:
        r.append(copy.deepcopy(like.find(w("rPr"))))
    t = etree.SubElement(r, w("t"))
    t.text = text
    t.set(XML_SPACE, "preserve")
    _strike(r)
    return r


def _tint(el: etree._Element, fill: str = ADD_FILL) -> None:
    """Shade every non-empty run inside a paragraph, row or table."""
    for r in el.iter(w("r")):
        t = r.find(w("t"))
        if t is not None and (t.text or "").strip():
            _shade(r, fill)


def _strike_all(el: etree._Element) -> None:
    for r in el.iter(w("r")):
        if r.find(w("t")) is not None:
            _strike(r)


def _clean_copy(el: etree._Element) -> etree._Element:
    c = copy.deepcopy(el)
    for node in list(c.iter()):
        if isinstance(node.tag, str) and node.tag in (w("bookmarkStart"), w("bookmarkEnd"),
                                                      w("commentRangeStart"), w("commentRangeEnd")):
            node.getparent().remove(node)
    return c


# ---------------------------------------------------------------- paragraphs

def _split_runs(p: etree._Element, cuts: set[int]) -> list[tuple[int, int, etree._Element]]:
    """Split the paragraph's text runs at character offsets; return (start, end, run)."""
    out = []
    pos = 0
    for r in _own_runs(p):
        t = r.find(w("t"))
        text = t.text or ""
        start, end = pos, pos + len(text)
        inner = sorted(c - start for c in cuts if start < c < end)
        if not inner:
            out.append((start, end, r))
        else:
            bounds = [0, *inner, len(text)]
            parent = r.getparent()
            idx = parent.index(r)
            pieces = []
            for x, y in zip(bounds, bounds[1:]):
                nr = copy.deepcopy(r)
                for extra in nr.findall(w("t"))[1:]:
                    nr.remove(extra)
                nt = nr.find(w("t"))
                nt.text = text[x:y]
                nt.set(XML_SPACE, "preserve")
                pieces.append((start + x, start + y, nr))
            parent.remove(r)
            for k, (_, _, nr) in enumerate(pieces):
                parent.insert(idx + k, nr)
            out.extend(pieces)
        pos = end
    return out


def mark_paragraph(p: etree._Element, old: str, new: str, stats: DiffStats) -> None:
    """Word-level diff inside one paragraph of the new document."""
    if old == new:
        return
    a, b = _tokens(old), _tokens(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    offs = [0]
    for tok in b:
        offs.append(offs[-1] + len(tok))
    added: list[tuple[int, int]] = []
    removed: list[tuple[int, str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("replace", "insert") and "".join(b[j1:j2]).strip():
            added.append((offs[j1], offs[j2]))
        if op in ("replace", "delete") and "".join(a[i1:i2]).strip():
            removed.append((offs[j1], "".join(a[i1:i2])))
    if not added and not removed:
        return
    stats.changed += 1
    cuts = {x for rng in added for x in rng} | {pos for pos, _ in removed}
    pieces = _split_runs(p, cuts)
    for s, e, r in pieces:
        if any(s >= a0 and e <= a1 for a0, a1 in added) and (r.find(w("t")).text or "").strip():
            _shade(r, ADD_FILL)
    for pos, text in sorted(removed, key=lambda x: -x[0]):
        target = next((r for s, e, r in pieces if s >= pos), None)
        like = target if target is not None else (pieces[-1][2] if pieces else None)
        dr = _deleted_run(like, text)
        if target is not None:
            target.addprevious(dr)
        elif pieces:
            pieces[-1][2].addnext(dr)
        else:
            p.append(dr)


def _note_paragraph(like: etree._Element | None, text: str) -> etree._Element:
    p = etree.Element(w("p"))
    if like is not None and like.find(w("pPr")) is not None:
        ppr = copy.deepcopy(like.find(w("pPr")))
        for tag in ("numPr", "pStyle"):
            for x in ppr.findall(w(tag)):
                ppr.remove(x)
        p.append(ppr)
    r = _deleted_run(None, text)
    rpr = r.find(w("rPr"))
    for old in rpr.findall(w("strike")):
        rpr.remove(old)
    etree.SubElement(rpr, w("i"))
    p.append(r)
    return p


# ---------------------------------------------------------------- blocks

def _blocks(container: etree._Element) -> list[etree._Element]:
    """Direct paragraphs and tables of a container (sdt content flattened)."""
    out = []
    for child in container:
        if child.tag in (w("p"), w("tbl")):
            out.append(child)
        elif child.tag == w("sdt"):
            content = child.find(w("sdtContent"))
            if content is not None:
                out.extend(_blocks(content))
    return out


def _rows(tbl: etree._Element) -> list[etree._Element]:
    return tbl.findall(w("tr"))


def _cells(tr: etree._Element) -> list[etree._Element]:
    return tr.findall(w("tc"))


def _text(el: etree._Element) -> str:
    if el.tag == w("p"):
        return para_text(el)
    if el.tag == w("tc"):
        return "\n".join(para_text(p) for p in el.iter(w("p")))
    if el.tag == w("tr"):
        return " | ".join(_text(c) for c in _cells(el))
    return "\n".join(_text(r) for r in _rows(el))


def _is_tabbed(p: etree._Element) -> bool:
    """TOC-style lines: inline word marks would break their dotted tab leaders."""
    style = p.find(f"{w('pPr')}/{w('pStyle')}")
    if style is not None and (style.get(w("val")) or "").upper().startswith("TOC"):
        return True
    tabs = p.find(f"{w('pPr')}/{w('tabs')}")
    if tabs is not None and any((t.get(w("leader")) or "none") not in ("none", "") for t in tabs.findall(w("tab"))):
        return True
    return False


def _own_text(p: etree._Element) -> str:
    """Text of the paragraph itself, without text boxes anchored in it."""
    return "".join((r.find(w("t")).text or "") for r in _own_runs(p))


def _textboxes(p: etree._Element) -> list[etree._Element]:
    """Text box contents anchored in a paragraph (DrawingML and VML fallback alike)."""
    return [t for t in p.iter(w("txbxContent"))]


def _key(el: etree._Element) -> str:
    return ("P:" if el.tag == w("p") else "T:") + _text(el)


def _span(tr: etree._Element) -> int:
    n = 0
    for tc in _cells(tr):
        gs = tc.find(f"{w('tcPr')}/{w('gridSpan')}")
        n += int(gs.get(w("val"), "1")) if gs is not None else 1
    return n


def _diff_cell(old_tc: etree._Element, new_tc: etree._Element, stats: DiffStats) -> None:
    _diff_blocks(_blocks(old_tc), _blocks(new_tc), new_tc, stats, in_cell=True)


def _diff_table(old_t: etree._Element, new_t: etree._Element, stats: DiffStats) -> None:
    orows, nrows = _rows(old_t), _rows(new_t)
    ok = [_text(r) for r in orows]
    nk = [_text(r) for r in nrows]
    ops = align(ok, nk, lambda i, j: text_similarity(ok[i], nk[j]), threshold=0.55)
    grid = _span(nrows[0]) if nrows else 0
    leftover: list[etree._Element] = []
    state = {"last": None}
    pending: list[etree._Element] = []

    def flush(before: etree._Element | None) -> None:
        for old_r in pending:
            if not _text(old_r).strip():
                continue
            stats.removed += 1
            if _span(old_r) != grid:
                leftover.append(old_r)  # different column layout: listed under the table
                continue
            copy_r = _clean_copy(old_r)
            for vm in list(copy_r.iter(w("vMerge"))):
                vm.getparent().remove(vm)
            _strike_all(copy_r)
            if before is not None:
                before.addprevious(copy_r)
            elif state["last"] is not None:
                state["last"].addnext(copy_r)
                state["last"] = copy_r
            else:
                new_t.append(copy_r)
        pending.clear()

    for op, i, j in ops:
        if op == "del":
            pending.append(orows[i])
            continue
        flush(nrows[j])
        if op == "ins":
            if nk[j].strip():
                _tint(nrows[j])
                stats.added += 1
        elif op == "chg":
            oc, nc = _cells(orows[i]), _cells(nrows[j])
            for k in range(min(len(oc), len(nc))):
                _diff_cell(oc[k], nc[k], stats)
            for extra in nc[len(oc):]:
                _tint(extra)
            for extra in oc[len(nc):]:
                txt = _text(extra).strip()
                paras = nc[-1].findall(w("p")) if nc else []
                if txt and paras:
                    paras[-1].addnext(_note_paragraph(paras[-1], txt))
        state["last"] = nrows[j]
    flush(None)

    if leftover:
        texts = [_text(r).replace("\n", " ") for r in leftover]
        shown = texts[:MAX_REMOVED_SHOWN]
        notes = [_note_paragraph(None, "Removed row: " + t) for t in shown]
        if len(texts) > len(shown):
            notes.append(_note_paragraph(None, f"… and {len(texts) - len(shown)} more removed rows"))
        anchor = new_t
        for n in notes:
            anchor.addnext(n)
            anchor = n


def _insert_removed(old_blocks: list[etree._Element], before: etree._Element | None,
                    container: etree._Element, after: etree._Element | None, stats: DiffStats, in_cell: bool) -> None:
    items = [b for b in old_blocks if _text(b).strip()]
    if not items:
        return
    limit = 4 if in_cell else MAX_REMOVED_SHOWN
    shown = items[:limit]
    nodes: list[etree._Element] = []
    for b in shown:
        c = _clean_copy(b)
        for vm in list(c.iter(w("vMerge"))):
            vm.getparent().remove(vm)
        _strike_all(c)
        nodes.append(c)
    stats.removed += len(items)
    if len(items) > len(shown):
        like = next((n for n in nodes if n.tag == w("p")), None)
        nodes.append(_note_paragraph(like, f"… and {len(items) - len(shown)} more removed"))
    for n in nodes:
        if before is not None:
            before.addprevious(n)
        elif after is not None:
            after.addnext(n)
            after = n
        else:
            sect = container.find(w("sectPr"))
            if sect is not None:
                sect.addprevious(n)
            else:
                container.append(n)


def _diff_paragraph(old_p: etree._Element, new_p: etree._Element, stats: DiffStats) -> None:
    ot, nt = _own_text(old_p), _own_text(new_p)
    if ot != nt:
        long_rewrite = len(_WORDS.findall(ot)) >= 8 and len(_WORDS.findall(nt)) >= 8 and text_similarity(ot, nt) < 0.4
        if _is_tabbed(new_p) or _is_tabbed(old_p) or long_rewrite:
            # TOC lines and mostly rewritten paragraphs: show the old line struck above the new one
            c = _clean_copy(old_p)
            for tb in list(c.iter(w("drawing"))) + list(c.iter(w("pict"))):
                tb.getparent().remove(tb)
            if _own_text(c).strip():
                _strike_all(c)
                new_p.addprevious(c)
            for r in _own_runs(new_p):
                if (r.find(w("t")).text or "").strip():
                    _shade(r, ADD_FILL)
            stats.changed += 1
        else:
            mark_paragraph(new_p, ot, nt, stats)
    # text boxes anchored in the paragraph (cover titles, call-outs): compare their content too
    otb, ntb = _textboxes(old_p), _textboxes(new_p)
    for k in range(min(len(otb), len(ntb))):
        _diff_blocks(_blocks(otb[k]), _blocks(ntb[k]), ntb[k], stats, in_cell=True)
    for extra in ntb[len(otb):]:
        _tint(extra)


def _diff_blocks(olds: list[etree._Element], news: list[etree._Element], container: etree._Element,
                 stats: DiffStats, in_cell: bool = False) -> None:
    ok = [_key(b) for b in olds]
    nk = [_key(b) for b in news]

    def sim(i: int, j: int) -> float:
        if olds[i].tag != news[j].tag:
            return 0.0
        if olds[i].tag == w("tbl"):
            ro, rn = _rows(olds[i]), _rows(news[j])
            same_grid = bool(ro) and bool(rn) and _span(ro[0]) == _span(rn[0])
            same_head = bool(ro) and bool(rn) and _text(ro[0]) == _text(rn[0])
            base = text_similarity(ok[i][2:], nk[j][2:])
            return base + (0.25 if same_grid else -0.2) + (0.2 if same_head else 0.0)
        return text_similarity(ok[i][2:], nk[j][2:])

    ops = align(ok, nk, sim, threshold=0.5)
    pending: list[etree._Element] = []
    last_new: etree._Element | None = None
    for op, i, j in ops:
        if op == "del":
            pending.append(olds[i])
            continue
        if pending:
            _insert_removed(pending, news[j], container, last_new, stats, in_cell)
            pending = []
        nb = news[j]
        if op == "ins":
            if _text(nb).strip():
                _tint(nb)
                stats.added += 1
        elif op == "chg":
            if nb.tag == w("p"):
                _diff_paragraph(olds[i], nb, stats)
            else:
                _diff_table(olds[i], nb, stats)
        last_new = nb
    if pending:
        _insert_removed(pending, None, container, last_new, stats, in_cell)


def build_diff(old: DocxPackage, new: DocxPackage) -> tuple[DocxPackage, DiffStats]:
    """Return a marked-up copy of `new` showing what changed since `old`."""
    out = new.clone()
    stats = DiffStats()
    _diff_blocks(_blocks(old.body), _blocks(out.body), out.body, stats)
    for name, root in out.aux.items():  # page headers and footers
        if name in old.aux:
            _diff_blocks(_blocks(old.aux[name]), _blocks(root), root, stats, in_cell=True)
    return out, stats
