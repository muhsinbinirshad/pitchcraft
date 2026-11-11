"""`pitchcraft doctor`: check that everything needed to run and preview proposals is installed."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

_DOCX_PARTS = {
    "[Content_Types].xml": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    ),
    "_rels/.rels": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    ),
    "word/document.xml": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>Pitchcraft render check</w:t></w:r></w:p>"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
        "</w:body></w:document>"
    ),
}


def _hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install --cask libreoffice && brew install poppler"
    if system == "Windows":
        return "install LibreOffice from libreoffice.org and Poppler (e.g. `choco install libreoffice-fresh poppler`), or use Docker"
    return "run ./scripts/install.sh, or install LibreOffice (Writer) and poppler-utils with your package manager"


def run(data: Path | None = None, web: Path | None = None) -> int:
    from .engine.render import render, renderer_status

    ok = True
    color = sys.stdout.isatty()

    def line(state: str, name: str, detail: str = "") -> None:
        mark = {"ok": "✓", "warn": "!", "fail": "✗"}[state]
        if color:
            mark = {"ok": "\033[32m✓\033[0m", "warn": "\033[33m!\033[0m", "fail": "\033[31m✗\033[0m"}[state]
        print(f"  {mark} {name:<22} {detail}")

    print("Pitchcraft doctor\n")

    py = sys.version_info
    if py >= (3, 11):
        line("ok", "Python", platform.python_version())
    else:
        ok = False
        line("fail", "Python", f"{platform.python_version()} (needs 3.11 or newer)")

    status = renderer_status()
    for tool, path in status["tools"].items():
        if path:
            version = ""
            if tool == "libreoffice":
                try:
                    out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60).stdout
                    version = " ".join(out.split()[:2])
                except Exception:  # noqa: BLE001
                    version = path
            line("ok", tool, version or path)
        else:
            ok = False
            line("fail", tool, "not found")

    if status["ok"]:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "check.docx"
            with zipfile.ZipFile(src, "w") as z:
                for name, xml in _DOCX_PARTS.items():
                    z.writestr(name, xml)
            t0 = time.time()
            try:
                r = render(src, Path(tmp) / "out", dpi=40)
                if r.pages and "render check" in " ".join(r.page_texts):
                    line("ok", "Preview render", f"{len(r.pages)} page in {time.time() - t0:.1f}s")
                else:
                    ok = False
                    line("fail", "Preview render", "LibreOffice ran but produced no readable page")
            except Exception as e:  # noqa: BLE001
                ok = False
                line("fail", "Preview render", str(e)[:200])
    else:
        line("fail", "Preview render", "skipped: missing " + ", ".join(status["missing"]))
        print(f"\n    Fix: {_hint()}")
        print("    Or point to LibreOffice directly: PITCHCRAFT_SOFFICE=/path/to/soffice\n")

    try:
        import xlrd  # noqa: F401
        line("ok", "Excel (.xls) reader", "xlrd")
    except ImportError:
        line("warn", "Excel (.xls) reader", "xlrd missing: pip install xlrd")

    web = web or Path(os.environ.get("PITCHCRAFT_WEB", Path(__file__).resolve().parents[1] / "frontend" / "out"))
    if (web / "index.html").is_file():
        line("ok", "Web UI", str(web))
    else:
        ok = False
        line("fail", "Web UI", f"not built at {web}: run `make build` (cd frontend && npm ci && npm run build)")

    data = data or Path(os.environ.get("PITCHCRAFT_DATA", "data"))
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        line("ok", "Data folder", f"{data.resolve()} (writable)")
    except OSError as e:
        ok = False
        line("fail", "Data folder", f"{data}: {e}")

    if os.environ.get("ANTHROPIC_API_KEY"):
        line("ok", "Claude API key", "set on the server")
    else:
        line("warn", "Claude API key", "not set: users add their own in Settings, or put ANTHROPIC_API_KEY in .env")

    print("\n" + ("All set. Start with: pitchcraft serve" if ok else "Some checks failed. Fix the items marked ✗ and run `pitchcraft doctor` again."))
    return 0 if ok else 1
