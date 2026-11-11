"""Build an id-addressed outline of a document.

Every top-level paragraph gets an id P<n>, every table T<n>, every row
T<n>.R<i> and every cell T<n>.R<i>.C<j>. The same normalized document always
yields the same ids, so a plan written against the outline can be applied
deterministically later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .ns import w


def _is_on(el: etree._Element | None) -> bool:
    if el is None:
        return False
    val = el.get(w("val"))
    return val not in ("0", "false", "off")


def run_text(r: etree._Element) -> str:
    out = []
    for child in r:
        if child.tag == w("t"):
            out.append(child.text or "")
        elif child.tag == w("tab"):
            out.append("\t")
    return "".join(out)


def para_text(p: etree._Element) -> str:
    """Plain text of a paragraph (all runs, including inside hyperlinks)."""
    return "".join(run_text(r) for r in p.iter(w("r")))


def para_display(p: etree._Element) -> str:
    """Text with **bold** markers when the paragraph mixes bold and normal runs."""
    segs: list[tuple[bool, str]] = []
    for r in p.iter(w("r")):
        t = run_text(r)
        if not t:
            continue
        rpr = r.find(w("rPr"))
        bold = rpr is not None and _is_on(rpr.find(w("b")))
        segs.append((bold, t))
    if not segs:
        return ""
    kinds = {b for b, t in segs if t.strip()}
    if len(kinds) <= 1:
        return "".join(t for _, t in segs)
    out = []
    for bold, t in segs:
        out.append(f"**{t}**" if bold and t.strip() else t)
    return "".join(out)


def para_style(p: etree._Element) -> str | None:
    ppr = p.find(w("pPr"))
    if ppr is None:
        return None
    ps = ppr.find(w("pStyle"))
    return ps.get(w("val")) if ps is not None else None


def para_list(p: etree._Element) -> str | None:
    ppr = p.find(w("pPr"))
    if ppr is None:
        return None
    num = ppr.find(w("numPr"))
    if num is None:
        return None
    nid = num.find(w("numId"))
    lvl = num.find(w("ilvl"))
    return f"{nid.get(w('val')) if nid is not None else '?'}/{lvl.get(w('val')) if lvl is not None else '0'}"


def cell_text(tc: etree._Element) -> str:
    texts = [para_text(p) for p in tc.iter(w("p"))]
    return " / ".join(t for t in texts if t.strip())


def cell_merge(tc: etree._Element) -> str | None:
    tcpr = tc.find(w("tcPr"))
    if tcpr is None:
        return None
    vm = tcpr.find(w("vMerge"))
    if vm is not None:
        return "restart" if vm.get(w("val")) == "restart" else "continue"
    return None


def cell_span(tc: etree._Element) -> int:
    tcpr = tc.find(w("tcPr"))
    if tcpr is not None:
        gs = tcpr.find(w("gridSpan"))
        if gs is not None:
            try:
                return int(gs.get(w("val")))
            except (TypeError, ValueError):
                return 1
    return 1


@dataclass
class Outline:
    registry: dict[str, etree._Element] = field(default_factory=dict)
    blocks: list[dict] = field(default_factory=list)

    def text(self, max_cell: int = 400) -> str:
        """Compact text form for the model."""
        lines: list[str] = []
        cur_part = None
        for b in self.blocks:
            if b.get("part") != cur_part:
                cur_part = b.get("part")
                kind = "page header" if "header" in (cur_part or "") else "page footer"
                lines.append(f"## {kind} ({cur_part}): repeats on pages; ids below start with its prefix")
            if b["kind"] == "p":
                tags = []
                if b.get("toc"):
                    tags.append("toc")
                if b.get("style"):
                    tags.append(b["style"])
                if b.get("list"):
                    tags.append(f"list:{b['list']}")
                if b.get("image"):
                    tags.append("image")
                if b.get("page_break"):
                    tags.append("page-break")
                tag = f"[{' '.join(tags)}] " if tags else ""
                body = b["display"] if b["display"].strip() else "(empty)"
                lines.append(f"{b['id']} {tag}{body}")
            else:
                lines.append(
                    f"{b['id']} [table {len(b['rows'])} rows]" + (" [toc]" if b.get("toc") else "")
                )
                for r in b["rows"]:
                    cells = []
                    for c in r["cells"]:
                        t = c["text"][:max_cell]
                        if c.get("merge") == "continue":
                            t = "⟨merged-above⟩"
                        if c.get("span", 1) > 1:
                            t += f" ⟨span {c['span']}⟩"
                        cells.append(t or "(empty)")
                    lines.append(f"  {r['id']} | " + " | ".join(cells))
        return "\n".join(lines)


def part_prefix(name: str) -> str:
    """word/header2.xml -> HDR2, word/footer1.xml -> FTR1."""
    base = name.rsplit("/", 1)[-1].removesuffix(".xml")
    num = "".join(ch for ch in base if ch.isdigit()) or "1"
    return ("HDR" if base.startswith("header") else "FTR") + num


def build_package_outline(pkg) -> Outline:
    """Body first, then every header and footer with its own id prefix."""
    out = build_outline(pkg.body)
    for name in sorted(pkg.aux):
        build_outline(pkg.aux[name], prefix=part_prefix(name) + ".", out=out, part=name)
    return out


def build_outline(body: etree._Element, prefix: str = "", out: Outline | None = None, part: str | None = None) -> Outline:
    out = out if out is not None else Outline()
    counters = {"p": 0, "t": 0}

    def add_para(p: etree._Element, toc: bool) -> None:
        counters["p"] += 1
        pid = f"{prefix}P{counters['p']}"
        out.registry[pid] = p
        style = para_style(p) or ""
        toc = toc or style.upper().startswith("TOC")
        out.blocks.append(
            {
                "id": pid,
                "kind": "p",
                "style": para_style(p),
                "list": para_list(p),
                "text": para_text(p),
                "display": para_display(p),
                "image": p.find(f".//{w('drawing')}") is not None
                or p.find(f".//{w('pict')}") is not None,
                "page_break": any(
                    br.get(w("type")) == "page" for br in p.iter(w("br"))
                ),
                "toc": toc,
                "part": part,
            }
        )

    def add_table(tbl: etree._Element, toc: bool) -> None:
        counters["t"] += 1
        tid = f"{prefix}T{counters['t']}"
        out.registry[tid] = tbl
        rows = []
        for i, tr in enumerate(tbl.findall(w("tr"))):
            rid = f"{tid}.R{i}"
            out.registry[rid] = tr
            cells = []
            for j, tc in enumerate(tr.findall(w("tc"))):
                cid = f"{rid}.C{j}"
                out.registry[cid] = tc
                cells.append(
                    {
                        "id": cid,
                        "text": cell_text(tc),
                        "merge": cell_merge(tc),
                        "span": cell_span(tc),
                    }
                )
            rows.append({"id": rid, "cells": cells})
        out.blocks.append({"id": tid, "kind": "table", "rows": rows, "toc": toc, "part": part})

    def walk(container: etree._Element, toc: bool) -> None:
        for child in container:
            if child.tag == w("p"):
                add_para(child, toc)
            elif child.tag == w("tbl"):
                add_table(child, toc)
            elif child.tag == w("sdt"):
                content = child.find(w("sdtContent"))
                gallery = child.find(f"{w('sdtPr')}//{w('docPartGallery')}")
                is_toc = gallery is not None and "Contents" in (gallery.get(w("val")) or "")
                if content is not None:
                    walk(content, toc or is_toc)

    walk(body, False)
    return out
