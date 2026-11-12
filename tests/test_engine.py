import json
from pathlib import Path

import pytest
from lxml import etree

from pitchcraft.engine import DocxPackage, Op, apply_plan, build_outline, plain_text, run_audits
from pitchcraft.engine.ns import W_NS, w
from pitchcraft.engine.ops import set_paragraph_text
from pitchcraft.pipeline.service import load_base, parse_ops

# A real proposal for the full-document tests. It is kept out of git (see private/README.md);
# tests that need it are skipped when it is missing.
FIX = Path(__file__).resolve().parents[1] / "private" / "fixtures"


@pytest.fixture(scope="module")
def base() -> DocxPackage:
    if not (FIX / "client_base.docx").exists():
        pytest.skip("needs private/fixtures/client_base.docx")
    return load_base(FIX / "client_base.docx")


def _p(xml: str) -> etree._Element:
    return etree.fromstring(f'<w:p xmlns:w="{W_NS}">{xml}</w:p>')


def test_roundtrip_keeps_text_and_parts(base, tmp_path):
    out = tmp_path / "rt.docx"
    base.save(out)
    again = load_base(out)
    assert plain_text(again.root) == plain_text(base.root)
    assert set(again.parts) == set(base.parts)


def test_outline_ids_are_stable(base):
    a = build_outline(base.body).text()
    b = build_outline(load_base(FIX / "client_base.docx").body).text()
    assert a == b
    assert "T11.R10 | Total Professional Fee" in a


def test_replace_across_runs_keeps_formatting():
    p = _p('<w:r><w:rPr><w:b/></w:rPr><w:t>AED 65,</w:t></w:r><w:r><w:t>000 total</w:t></w:r>')
    from pitchcraft.engine.ops import replace_in_paragraph
    assert replace_in_paragraph(p, "65,000", "71,000") == 1
    runs = p.findall(w("r"))
    assert runs[0].find(w("rPr")) is not None
    assert "".join(t.text for t in p.iter(w("t"))) == "AED 71,000 total"


def test_set_text_with_bold_label():
    p = _p('<w:r><w:rPr><w:b/></w:rPr><w:t>Old:</w:t></w:r><w:r><w:t> old body</w:t></w:r>')
    set_paragraph_text(p, "**New label:** new body")
    runs = p.findall(w("r"))
    assert [r.find(w("t")).text for r in runs] == ["New label:", " new body"]
    assert runs[0].find(f"{w('rPr')}/{w('b')}") is not None
    assert runs[1].find(f"{w('rPr')}/{w('b')}") is None


def test_failed_op_rolls_back_and_others_apply(base):
    ops = [
        Op(op="replace_text", find="does not exist anywhere", replace="x"),
        Op(op="replace_text", find="AED 65,000", replace="AED 71,000", expect=2),
        Op(op="replace_text", find="195 Person-Days", replace="225 Person-Days", expect=99),
    ]
    res = apply_plan(base, ops)
    assert [r.ok for r in res.results] == [False, True, False]
    text = plain_text(res.package.root)
    assert "AED 71,000" in text and "AED 65,000" not in text
    assert "195 Person-Days" in text  # rolled back: expect mismatch


def test_insert_rows_respects_vertical_merge(base):
    # T11 has no merges; build one by hand on a copy to check merge handling
    pkg = base.clone()
    tbl = build_outline(pkg.body).registry["T11"]
    first = tbl.findall(w("tr"))[1].findall(w("tc"))[2]
    tcpr = first.find(w("tcPr"))
    vm = etree.SubElement(tcpr, w("vMerge"))
    vm.set(w("val"), "restart")
    res = apply_plan(pkg, [Op(op="insert_rows", target="T11", anchor="T11.R1", like="T11.R1",
                              rows=[["A", "B", "should fail"]])])
    assert not res.results[0].ok and "merged" in res.results[0].error
    res = apply_plan(pkg, [Op(op="insert_rows", target="T11", anchor="T11.R1", like="T11.R1", rows=[["A", "B", ""]])])
    assert res.results[0].ok
    new_row = build_outline(res.package.body).registry["T11"].findall(w("tr"))[2]
    vmc = new_row.findall(w("tc"))[2].find(f"{w('tcPr')}/{w('vMerge')}")
    assert vmc is not None and vmc.get(w("val")) is None  # continues the merge


def test_recorded_plan_is_clean(base):
    plan = json.loads((FIX / "client_plan.json").read_text())
    ops, errors = parse_ops(plan["ops"])
    assert not errors
    res = apply_plan(base, ops)
    assert not res.errors, [r.error for r in res.errors]
    corpus = plain_text(base.root) + " 30 man days 71,000 10 weeks 3.75 GB 225 50 100 40 10 20"
    audits = {a["check"]: a for a in run_audits(base, res.package, res.new_texts, corpus, plan["fact_changes"])}
    assert audits["style"]["level"] == "pass"
    assert audits["stale"]["level"] == "pass", audits["stale"]
    assert audits["structure"]["level"] == "pass"
    text = plain_text(res.package.root)
    for s in ("225 Man Days", "AED 71,000", "6.9 Web Application & API Penetration Testing", "Weeks 9-10"):
        assert s in text


def test_numbers_audit_flags_invented_numbers(base):
    from pitchcraft.engine.audits import audit_numbers
    f = audit_numbers(["Fee is AED 83,250", "225 Man Days"], "195 man days plus 30")
    assert f.level == "warn"
    assert any("83250" in d for d in f.details)
    assert any(d.startswith("225 =") for d in f.details)


def test_headers_are_editable(base):
    from pitchcraft.engine import build_package_outline
    o = build_package_outline(base)
    assert "HDR1.P1" in o.registry
    header = "".join(t.text or "" for t in o.registry["HDR1.P1"].iter(w("t"))).strip()
    assert header
    res = apply_plan(base, [Op(op="replace_text", find=header, replace="Sample header text", expect=1)])
    assert res.results[0].ok
    assert "Sample header text" in plain_text(res.package)


def test_leftovers_found():
    from pitchcraft.engine.audits import find_leftovers
    base = "Harbor Point has 4,378 assets. Founded 2019. Northwind Security"
    out = "ABC Group has 1,200 assets across Harbor Point. Founded 2019. Northwind Security"
    left = find_leftovers(base, out, "ABC Group 1,200 assets", ["Harbor Point", "4,378"])
    assert left == ["Harbor Point"]


def test_inspect_rejects_junk(base):
    from pitchcraft.engine.inspect import inspect_docx
    good = inspect_docx((FIX / "client_base.docx").read_bytes())
    assert good.ok and good.stats["tables"] > 5 and good.headings
    assert not inspect_docx(b"junk").ok


def test_leftovers_ignore_standards_and_placeholders():
    from pitchcraft.engine.audits import audit_placeholders, find_leftovers
    base = "ISO/IEC 27001 and NIST SP 800-115 for Microsoft 365. Scope covers 4,378 assets."
    out = base.replace("4,378", "180")
    assert find_leftovers(base, out, "180 assets", []) == []
    assert find_leftovers(base, base, "180 assets", []) == ["4,378"]
    assert audit_placeholders(["Dated [Proposal Date]", "fine text"]).level == "warn"
    assert audit_placeholders(["Planned start: January 2027"]).level == "pass"


def test_changes_view_marks_edits(base):
    from pitchcraft.engine.diff import ADD_FILL, DEL_FILL, build_diff
    plan = json.loads((FIX / "client_plan.json").read_text())
    ops, _ = parse_ops(plan["ops"])
    new = apply_plan(base, ops).package
    marked, stats = build_diff(base, new)
    assert stats.changed > 10 and stats.added > 10
    xml = etree.tostring(marked.root).decode()
    assert ADD_FILL in xml and DEL_FILL in xml
    assert "195" in plain_text(marked) and "225" in plain_text(marked)  # old value shown struck, new value shaded
    assert plain_text(new) != plain_text(marked)
    assert "195 Man Days" in plain_text(base) and "195" not in plain_text(new).split("Man Days")[0][-6:]


def test_insert_table_any_shape(base):
    from pitchcraft.engine import build_package_outline
    # T11 is the 3-column commercial table; build a 5-column pricing table styled like it
    ops = [Op(op="insert_table", anchor="P226", like="T11", new_id="PRICE",
              rows=[["Item", "Qty", "Unit (AED)", "Days", "Total (AED)"],
                    ["Web app PT", "4", "1,500", "8", "12,000"],
                    ["SAST", "10", "600", "6", "6,000"]]),
           Op(op="set_text", target="PRICE.R2.C4", replace="6,500")]
    res = apply_plan(base, ops)
    assert all(r.ok for r in res.results), [r.error for r in res.results]
    tbl = res.package.body
    outline = build_package_outline(res.package)
    new_tbl = [b for b in outline.blocks if b["kind"] == "table" and b["rows"] and b["rows"][0]["cells"][0]["text"] == "Item"][0]
    assert len(new_tbl["rows"]) == 3 and len(new_tbl["rows"][0]["cells"]) == 5
    assert new_tbl["rows"][2]["cells"][4]["text"] == "6,500"
    from pitchcraft.engine.audits import audit_style, audit_structure
    assert audit_structure(res.package).level == "pass"
    assert audit_style(base, res.package).level == "pass"  # formatting comes from the like table


def test_delete_range_removes_a_section(base):
    # 6.8 heading (P176) through its last bullet (P180)
    res = apply_plan(base, [Op(op="delete_range", anchor="P176", target="P180")])
    assert res.results[0].ok, res.results[0].error
    text = plain_text(res.package)
    assert "Validate realistic attack paths" not in text
    assert "6.7 Endpoint" in text and "7. METHODOLOGY" in text
    bad = apply_plan(base, [Op(op="delete_range", anchor="P180", target="P176")])
    assert not bad.results[0].ok


def test_spreadsheet_and_slide_attachments(tmp_path):
    import zipfile
    from pitchcraft.ai.inputs import prepare_inputs
    ods = tmp_path / "a.ods"
    with zipfile.ZipFile(ods, "w") as z:
        z.writestr("content.xml", '<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="Assets"><table:table-row><table:table-cell><text:p>Site</text:p></table:table-cell><table:table-cell><text:p>Hosts</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell><text:p>Sharjah</text:p></table:table-cell><table:table-cell><text:p>120</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>')
    ppt = tmp_path / "b.pptx"
    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    with zipfile.ZipFile(ppt, "w") as z:
        z.writestr("ppt/slides/slide1.xml", f'<p:sld {ns}><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Budget AED 39,500</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    r = prepare_inputs([ods, ppt])
    assert "Sharjah\t120" in r.text and "## Sheet: Assets" in r.text
    assert "Budget AED 39,500" in r.text and "## Slide 1" in r.text


def test_env_file_loading(tmp_path, monkeypatch):
    import os
    from pitchcraft.__main__ import load_env_file

    f = tmp_path / ".env"
    f.write_text('# comment\nPITCHCRAFT_T1="quoted value"\nexport PITCHCRAFT_T2=plain\nPITCHCRAFT_T3=from-file\n')
    f.chmod(0o600)
    monkeypatch.delenv("PITCHCRAFT_T1", raising=False)
    monkeypatch.delenv("PITCHCRAFT_T2", raising=False)
    monkeypatch.setenv("PITCHCRAFT_T3", "from-env")
    load_env_file(f)
    assert os.environ["PITCHCRAFT_T1"] == "quoted value"
    assert os.environ["PITCHCRAFT_T2"] == "plain"
    assert os.environ["PITCHCRAFT_T3"] == "from-env"  # real environment wins
    monkeypatch.delenv("PITCHCRAFT_T1"); monkeypatch.delenv("PITCHCRAFT_T2")


def test_doctor_reports_missing_tools(tmp_path, monkeypatch, capsys):
    from pitchcraft import doctor
    from pitchcraft.engine import render as r

    monkeypatch.setattr(r, "find_soffice", lambda: None)
    assert r.renderer_status()["missing"][0] == "libreoffice"
    assert doctor.run(data=tmp_path / "data") == 1
    out = capsys.readouterr().out
    assert "libreoffice" in out and "not found" in out and "Fix:" in out


def test_concurrent_renders_of_one_folder_do_not_collide(tmp_path):
    """A background preview render and a browser request for the same folder must not run LibreOffice at once."""
    import threading
    from pitchcraft.engine import render as r

    active, peak = [0], [0]
    gate = threading.Lock()

    def fake(docx, out_dir, dpi, timeout):
        with gate:
            active[0] += 1; peak[0] = max(peak[0], active[0])
        import time; time.sleep(0.05)
        with gate:
            active[0] -= 1
        return None

    orig = r._render
    r._render = fake
    try:
        ts = [threading.Thread(target=r.render, args=(tmp_path / "a.docx", tmp_path / "out")) for _ in range(4)]
        [t.start() for t in ts]; [t.join() for t in ts]
    finally:
        r._render = orig
    assert peak[0] == 1
