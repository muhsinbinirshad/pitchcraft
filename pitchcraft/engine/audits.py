"""Checks that run after a plan is applied.

- numbers: every number written by the plan must exist in the sources
  (base document, inputs, answers, instructions). Catches invented figures.
- stale: values the plan said it changed must not remain anywhere.
- style: every paragraph/run format in the output already exists in the base.
- structure: table rows match their grid; the XML re-parses.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from lxml import etree

from .ns import w
from .outline import build_outline, para_text
from .package import DocxPackage

_NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _norm_num(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def numbers_in(text: str) -> set[str]:
    return {_norm_num(m.group(0)) for m in _NUM_RE.finditer(text)}


@dataclass
class Finding:
    check: str
    level: str  # "pass" | "warn" | "fail"
    message: str
    details: list[str] = field(default_factory=list)


def _derivation(n: str, known: set[str]) -> str | None:
    """Explain n as a sum or difference of two known numbers (e.g. 225 = 195 + 30)."""
    try:
        target = float(n)
    except ValueError:
        return None
    vals = sorted({float(k) for k in known if k.replace(".", "", 1).isdigit() and 0 < float(k) < 1e9})
    vs = set(vals)
    for a in vals:
        if target - a in vs and target - a > 0:
            return f"{_fmt(a)} + {_fmt(target - a)}"
        if a - target in vs and a - target > 0:
            return f"{_fmt(a)} - {_fmt(a - target)}"
    return None


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def audit_numbers(new_texts: list[str], corpus: str) -> Finding:
    known = numbers_in(corpus)
    unverified: dict[str, str] = {}
    derived: dict[str, str] = {}
    for t in new_texts:
        for n in numbers_in(t):
            if n in known or len(n) == 1:
                continue  # single digits (counts, step numbers) are too noisy
            if "." in n and all(part in known or len(part) <= 2 for part in n.split(".")):
                continue  # section numbers like 6.10
            how = _derivation(n, known)
            if how:
                derived[n] = how
            else:
                unverified.setdefault(n, t[:160])
    notes = [f"{n} = {how} (computed from source numbers)" for n, how in derived.items()]
    if not unverified:
        msg = "Every number written by the plan appears in the sources"
        msg += " or is computed from them." if derived else "."
        return Finding("numbers", "pass", msg, notes)
    return Finding(
        "numbers",
        "warn",
        f"{len(unverified)} number(s) not found in any source. Check they are correct.",
        [f"{n}: “{ctx}”" for n, ctx in unverified.items()] + notes,
    )


def audit_stale(out_text: str, fact_changes: list[dict]) -> Finding:
    left = []
    for fc in fact_changes:
        old = (fc.get("old") or "").strip()
        new = (fc.get("new") or "").strip()
        if not old or old == new:
            continue
        # count only matches that are not part of the new value
        hits = out_text.count(old) - (out_text.count(new) if old in new else 0)
        if hits > 0:
            left.append(f"“{old}” still appears {hits} time(s) (should be “{new}”)")
    if not left:
        return Finding("stale", "pass", "No old values left behind for the facts that changed.")
    return Finding("stale", "warn", "Some old values still appear in the document.", left)


def _sig(el: etree._Element | None) -> bytes:
    return b"" if el is None else etree.tostring(el, method="c14n")


def _format_signatures(pkg: DocxPackage) -> tuple[set, set]:
    ppr_sigs, rpr_sigs = set(), set()
    for p in (p for r in pkg.roots().values() for p in r.iter(w("p"))):
        ppr = p.find(w("pPr"))
        ppr_sigs.add(_sig(ppr))
        for r in p.iter(w("r")):
            rpr_sigs.add(_sig(r.find(w("rPr"))))
    return ppr_sigs, rpr_sigs


def audit_style(base: DocxPackage, out: DocxPackage) -> Finding:
    bp, br = _format_signatures(base)
    op, orr = _format_signatures(out)
    new_p = op - bp
    new_r = orr - br
    if not new_p and not new_r:
        return Finding("style", "pass", "No new formatting: every paragraph and run format comes from the base document.")
    det = []
    if new_p:
        det.append(f"{len(new_p)} new paragraph format(s)")
    if new_r:
        det.append(f"{len(new_r)} new run format(s)")
    return Finding("style", "warn", "Some formatting does not exist in the base document.", det)


def audit_structure(out: DocxPackage) -> Finding:
    problems = []
    try:
        etree.fromstring(etree.tostring(out.root))
    except etree.XMLSyntaxError as e:  # pragma: no cover
        return Finding("structure", "fail", f"document.xml does not parse: {e}")
    outline = build_outline(out.body)
    for b in outline.blocks:
        if b["kind"] != "table":
            continue
        tbl = outline.registry[b["id"]]
        grid = tbl.find(w("tblGrid"))
        ncols = len(grid.findall(w("gridCol"))) if grid is not None else None
        for r in b["rows"]:
            span = sum(c["span"] for c in r["cells"])
            if ncols and span != ncols:
                tr = outline.registry[r["id"]]
                # rows may skip grid columns via gridBefore/gridAfter
                trpr = tr.find(w("trPr"))
                extra = 0
                if trpr is not None:
                    for tag in ("gridBefore", "gridAfter"):
                        g = trpr.find(w(tag))
                        if g is not None:
                            extra += int(g.get(w("val"), "0"))
                if span + extra != ncols:
                    problems.append(f"{r['id']}: {span + extra} columns, table grid has {ncols}")
    if out.body.find(w("sectPr")) is None:
        problems.append("Body has no section properties (w:sectPr)")
    if problems:
        return Finding("structure", "fail", "Table or section structure problems.", problems)
    return Finding("structure", "pass", "Tables and sections are well formed.")


_BIGNUM_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?![\d])|(?<![\w.,])\d{3,}(?![\d,])")


def find_leftovers(base_text: str, out_text: str, sources: str, reference_terms: list[str]) -> list[str]:
    """Template content still present in a new proposal.

    reference_terms come from the planner (client names, sites, counts...).
    Large numbers from the template that the user's sources never mention are
    added as a deterministic backstop.
    """
    left: list[str] = []
    seen = set()
    src_l = sources.lower()
    for t in reference_terms:
        t = t.strip()
        if len(t) < 3 or t.lower() in seen:
            continue
        seen.add(t.lower())
        if t in out_text and t.lower() not in src_l:
            left.append(t)
    src_nums = numbers_in(sources)
    standard_ctx = re.compile(r"(?:ISO|IEC|NIST|SP|Microsoft|Office|M|CIS|PCI|DSS|AES|RSA|SHA|TLS|IEEE|RFC|CVE|Windows|Server|Top|OWASP|SOC|Tier|Level|Port|IPv)\s*[-/:]?\s*$", re.I)
    standard_nums = set()
    for mm in _BIGNUM_RE.finditer(base_text):
        before = base_text[max(0, mm.start() - 14):mm.start()]
        after = base_text[mm.end():mm.end() + 2]
        if standard_ctx.search(before) or re.search(r"\d[-‑–]$", before) or re.match(r"[-‑–]\d", after):
            standard_nums.add(mm.group(0))
    for m in sorted(set(_BIGNUM_RE.findall(base_text)) - standard_nums):
        n = _norm_num(m)
        if n in src_nums or len(n) < 3 or m in seen:
            continue
        if n.startswith(("19", "20")) and len(n) == 4:
            continue  # years
        if m in out_text:
            left.append(m)
    return left


def audit_leftovers(left: list[str]) -> Finding:
    if not left:
        return Finding("leftovers", "pass", "No details from the template's old client remain.")
    return Finding("leftovers", "warn", f"{len(left)} detail(s) from the template still appear. Check they belong in this proposal.", left[:40])


_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{2,40}\]|\{\{[^}]{1,40}\}\}|\bTBD\b|\bTBC\b|\bXX+\b|lorem ipsum", re.I)


def audit_placeholders(new_texts: list[str]) -> Finding:
    hits = []
    for t in new_texts:
        for m in _PLACEHOLDER_RE.finditer(t):
            hits.append(f"“{m.group(0)}” in “{t[:100]}”")
    if not hits:
        return Finding("placeholders", "pass", "No placeholder text was written.")
    return Finding("placeholders", "warn", f"{len(hits)} placeholder(s) written. Replace them with real values.", hits[:20])


def run_audits(
    base: DocxPackage,
    out: DocxPackage,
    new_texts: list[str],
    corpus: str,
    fact_changes: list[dict],
    leftovers: list[str] | None = None,
) -> list[dict]:
    out_text = "\n".join(para_text(p) for r in out.roots().values() for p in r.iter(w("p")))
    findings = [
        audit_numbers(new_texts, corpus),
        audit_stale(out_text, fact_changes),
        audit_placeholders(new_texts),
        audit_style(base, out),
        audit_structure(out),
    ]
    if leftovers is not None:
        findings.insert(2, audit_leftovers(leftovers))
    return [asdict(f) for f in findings]
