"""Render a .docx to PDF and page images with LibreOffice and Poppler."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def render_lock(out_dir: Path) -> threading.Lock:
    """One render at a time per output folder. Two LibreOffice runs writing the same folder corrupt each other."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(Path(out_dir).resolve()), threading.Lock())


class RenderError(Exception):
    pass


@dataclass
class Rendered:
    pdf: Path
    pages: list[Path]
    page_texts: list[str]
    missing_fonts: list[str] = field(default_factory=list)


def _embedded_fonts(docx: Path, dest: Path) -> int:
    """Extract fonts embedded in the .docx so LibreOffice renders with the real typefaces.

    Without this, a missing font (e.g. a brand font) is replaced by a wider one and
    text overflows fixed frames such as cover titles. Obfuscated fonts (.odttf) are
    decoded with their fontKey as defined by ECMA-376.
    """
    import re
    import zipfile

    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        with zipfile.ZipFile(docx) as z:
            names = set(z.namelist())
            table = z.read("word/fontTable.xml").decode("utf8", "ignore") if "word/fontTable.xml" in names else ""
            rels = z.read("word/_rels/fontTable.xml.rels").decode("utf8", "ignore") if "word/_rels/fontTable.xml.rels" in names else ""
            targets = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
            targets.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
            for key, rid in re.findall(r'w:embed\w+\s+w:fontKey="\{?([0-9A-Fa-f-]+)\}?"\s+r:id="([^"]+)"', table):
                target = targets.get(rid)
                if not target:
                    continue
                part = "word/" + target.lstrip("/").removeprefix("word/")
                if part not in names:
                    continue
                data = bytearray(z.read(part))
                hexkey = key.replace("-", "")
                if len(hexkey) == 32 and int(hexkey, 16) != 0 and len(data) >= 32:
                    kb = bytes.fromhex(hexkey)[::-1]
                    for i in range(32):
                        data[i] ^= kb[i % 16]
                name = Path(part).stem + ".ttf"
                (dest / name).write_bytes(bytes(data))
                n += 1
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        return n
    return n


_GOOGLE_CSS = "https://fonts.googleapis.com/css2?family={}:ital,wght@0,400;0,700;1,400;1,700"
_ALIASES = {"calibri": "carlito", "cambria": "caladea", "arial": "liberation sans", "helvetica": "liberation sans",
            "times new roman": "liberation serif", "courier new": "liberation mono"}


def _font_cache() -> Path:
    d = Path(os.environ.get("PITCHCRAFT_FONT_CACHE", Path.home() / ".cache" / "pitchcraft" / "fonts"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _installed(family: str) -> bool:
    want = _ALIASES.get(family.lower(), family.lower())
    try:
        got = subprocess.run(["fc-match", "-f", "%{family}", family], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return any(want == g.strip().lower() for g in got.split(","))


def _fetch_google_font(family: str, cache: Path) -> bool:
    """Download a font family from Google Fonts into the cache (once). False if unavailable."""
    import re
    import urllib.error
    import urllib.request

    slug = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    if list(cache.glob(f"{slug}-*.ttf")):
        return True
    if (cache / f"{slug}.missing").exists() or os.environ.get("PITCHCRAFT_FETCH_FONTS", "on").lower() in ("off", "0", "false"):
        return False
    try:
        req = urllib.request.Request(_GOOGLE_CSS.format(family.replace(" ", "+")), headers={"User-Agent": "Mozilla/4.0"})
        css = urllib.request.urlopen(req, timeout=15).read().decode()
        urls = re.findall(r"font-style:\s*(\w+);\s*font-weight:\s*(\d+);[^}]*?url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css, re.S)
        for style, weight, url in urls:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/4.0"}), timeout=30).read()
            (cache / f"{slug}-{weight}-{style}.ttf").write_bytes(data)
        if urls:
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False  # offline: try again next time
    (cache / f"{slug}.missing").write_text("not on Google Fonts")
    return False


def _used_fonts(docx: Path) -> tuple[set[str], set[str]]:
    """(fonts the document names, fonts it embeds)."""
    import re
    import zipfile

    used, embedded = set(), set()
    try:
        with zipfile.ZipFile(docx) as z:
            table = z.read("word/fontTable.xml").decode("utf8", "ignore") if "word/fontTable.xml" in z.namelist() else ""
    except (zipfile.BadZipFile, OSError):
        return used, embedded
    try:
        with zipfile.ZipFile(docx) as z:
            for name in z.namelist():
                if name.startswith("word/") and name.endswith(".xml") and any(k in name for k in ("document", "styles", "header", "footer", "numbering")):
                    xml = z.read(name).decode("utf8", "ignore")
                    used.update(re.findall(r'<w:rFonts\b[^>]*?w:(?:ascii|hAnsi)="([^"]+)"', xml))
    except (zipfile.BadZipFile, OSError):
        pass
    for block in re.findall(r"<w:font\b.*?</w:font>|<w:font\b[^>]*/>", table, re.S):
        m = re.search(r'w:name="([^"]+)"', block)
        if not m:
            continue
        used.add(m.group(1))
        if "w:embed" in block:
            embedded.add(m.group(1))
    return used, embedded


def _resolve_fonts(docx: Path, dest: Path) -> list[str]:
    """Make every font the document uses available; return those still missing."""
    used, embedded = _used_fonts(docx)
    cache = _font_cache()
    missing = []
    for fam in sorted(used - embedded):
        if fam.lower().startswith(("symbol", "wingdings", "webdings", "ms ", "segoe")) or _installed(fam):
            continue
        if not _fetch_google_font(fam, cache):
            missing.append(fam)
    for f in cache.glob("*.ttf"):
        shutil.copy(f, dest / f.name)
    return missing


_SPACING_RE = None


def _render_copy(docx: Path, dest: Path) -> Path:
    """Copy of the .docx with spec defaults made explicit where LibreOffice reads them differently than Word.

    <w:spacing w:line="240"/> without w:lineRule means "auto" (single spacing) in
    ECMA-376 and in Word, but LibreOffice treats it as an exact line height, so
    large text in fixed frames (cover titles) overlaps. Only the render copy is
    changed; the user's document is untouched.
    """
    import re
    import zipfile

    global _SPACING_RE
    if _SPACING_RE is None:
        _SPACING_RE = re.compile(rb"<w:spacing\b[^>]*/>")

    def fix(m: re.Match) -> bytes:
        t = m.group(0)
        return t if (b"w:lineRule" in t or b"w:line=" not in t) else t.replace(b"w:line=", b'w:lineRule="auto" w:line=', 1)

    out = dest / docx.name
    with zipfile.ZipFile(docx) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                data = _SPACING_RE.sub(fix, data)
            dst.writestr(info, data)
    return out


_SOFFICE_PATHS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",          # macOS
    r"C:\Program Files\LibreOffice\program\soffice.exe",          # Windows
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/opt/libreoffice/program/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/snap/bin/libreoffice",
)


def find_soffice() -> str | None:
    """LibreOffice binary: $PITCHCRAFT_SOFFICE, then PATH, then the usual install folders."""
    if (env := os.environ.get("PITCHCRAFT_SOFFICE")) and Path(env).is_file():
        return env
    for name in ("soffice", "libreoffice"):
        if p := shutil.which(name):
            return p
    return next((p for p in _SOFFICE_PATHS if Path(p).is_file()), None)


def renderer_status() -> dict:
    """What previews need: LibreOffice to make the PDF, Poppler to turn it into pages and text."""
    tools = {"libreoffice": find_soffice(), "pdftoppm": shutil.which("pdftoppm"), "pdftotext": shutil.which("pdftotext")}
    return {"ok": all(tools.values()), "tools": tools, "missing": [k for k, v in tools.items() if not v]}


def _soffice() -> str:
    if p := find_soffice():
        return p
    raise RenderError("LibreOffice is not installed. Install it (see README) or set PITCHCRAFT_SOFFICE, then run: pitchcraft doctor")


def render(docx: Path, out_dir: Path, dpi: int = 70, timeout: int = 240) -> Rendered:
    out_dir.mkdir(parents=True, exist_ok=True)
    # separate profile dir so parallel renders don't fight over a lock; it is also
    # HOME, so fontconfig picks up the document's embedded fonts from ~/.fonts
    with tempfile.TemporaryDirectory() as profile:
        fonts = Path(profile) / ".fonts"
        _embedded_fonts(docx, fonts)
        missing_fonts = _resolve_fonts(docx, fonts)
        work = Path(profile) / "in"
        work.mkdir()
        try:
            source = _render_copy(docx, work)
        except Exception:  # noqa: BLE001 - fall back to the original file
            source = docx
        extra = os.environ.get("PITCHCRAFT_FONTS")
        if extra and Path(extra).is_dir():
            for f in Path(extra).glob("*.[ot]tf"):
                shutil.copy(f, fonts / f.name)
        cmd = [
            _soffice(),
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "HOME": profile, "XDG_DATA_HOME": str(Path(profile) / ".local/share")})
    pdf = out_dir / (docx.stem + ".pdf")
    if proc.returncode != 0 or not pdf.exists():
        raise RenderError(f"PDF conversion failed: {proc.stderr.strip()[:400]}")
    for old in out_dir.glob("page-*.png"):
        old.unlink()
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(out_dir / "page")],
        check=True, capture_output=True, timeout=timeout,
    )
    pages = page_files(out_dir)
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                         text=True, timeout=timeout).stdout
    texts = txt.split("\f")
    return Rendered(pdf=pdf, pages=pages, page_texts=texts[: len(pages)], missing_fonts=missing_fonts)


def page_files(folder: Path) -> list[Path]:
    return sorted(folder.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))


def pages_containing(page_texts: list[str], snippets: list[str]) -> list[int]:
    """1-based page numbers whose text contains any snippet (first 40 chars, spaces squashed)."""
    norm = [" ".join(t.split()) for t in page_texts]
    hits = set()
    for s in snippets:
        key = " ".join(s.replace("**", "").split())[:40]
        if len(key) < 6:
            continue
        for i, t in enumerate(norm):
            if key in t:
                hits.add(i + 1)
    return sorted(hits)
