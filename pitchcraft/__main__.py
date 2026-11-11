"""Command line: `python -m pitchcraft serve|outline|apply`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ.

    Values already set in the real environment win, so a deploy's own secrets are never overridden.
    """
    import os

    if not path.is_file():
        return
    if os.name == "posix" and path.stat().st_mode & 0o077:
        print(f"warning: {path} is readable by other users; run: chmod 600 {path}", file=sys.stderr)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pitchcraft")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8600)
    s.add_argument("--data", default="data")
    s.add_argument("--env-file", help="Read settings such as ANTHROPIC_API_KEY from this file (default: ./.env)")

    d = sub.add_parser("doctor", help="Check that LibreOffice, Poppler and the web UI are installed and previews render")
    d.add_argument("--data", default=None)
    d.add_argument("--env-file", help="Settings file to load first (default: ./.env)")

    u = sub.add_parser("adduser", help="Create a login (the first user is usually created in the browser)")
    u.add_argument("username")
    u.add_argument("--admin", action="store_true")
    u.add_argument("--data", default="data")

    it = sub.add_parser("import-templates", help="Add existing proposals (.docx) to the template library")
    it.add_argument("files", nargs="+")
    it.add_argument("--data", default="data")
    it.add_argument("--default", help="file name to mark as the default template")

    o = sub.add_parser("outline", help="Print a document's id outline")
    o.add_argument("docx")

    a = sub.add_parser("apply", help="Apply a plan JSON (list of ops or a full plan) to a document")
    a.add_argument("docx")
    a.add_argument("plan")
    a.add_argument("-o", "--out", required=True)

    args = ap.parse_args(argv)
    load_env_file(Path(args.env_file) if getattr(args, "env_file", None) else Path.cwd() / ".env")

    if args.cmd == "doctor":
        from .doctor import run as doctor

        return doctor(Path(args.data) if args.data else None)

    if args.cmd == "serve":
        import os

        import uvicorn

        os.environ["PITCHCRAFT_DATA"] = args.data
        from .api.app import create_app
        from .engine.render import renderer_status

        if missing := renderer_status()["missing"]:
            print(f"warning: previews are off, missing: {', '.join(missing)}. Run `pitchcraft doctor` for the fix.", file=sys.stderr)

        uvicorn.run(create_app(Path(args.data)), host=args.host, port=args.port)
        return 0

    if args.cmd == "adduser":
        import getpass

        from .api.auth import Auth, AuthError

        data = Path(args.data)
        data.mkdir(parents=True, exist_ok=True)
        pw = getpass.getpass("Password (min 8 chars): ")
        try:
            Auth(data).add_user(args.username, pw, admin=args.admin)
        except AuthError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"created {args.username}{' (admin)' if args.admin else ''}")
        return 0

    if args.cmd == "import-templates":
        import os

        from .engine.inspect import inspect_docx
        from .engine.render import render
        from .pipeline.service import Service
        from .pipeline.store import Store

        svc = Service(Store(Path(args.data)))
        key = {"api_key": os.environ.get("ANTHROPIC_API_KEY")} if os.environ.get("ANTHROPIC_API_KEY") else None
        for f in map(Path, args.files):
            data = f.read_bytes()
            rep = svc.inspect_template(data, f.name, key) if key else {"structure": inspect_docx(data).to_dict(), "ai": None,
                                                                          "ai_error": None, "verdict": "unchecked"}
            if not rep["structure"]["ok"]:
                rep["verdict"] = "reject"
            if rep["verdict"] == "reject":
                print(f"skip {f.name}: {'; '.join(rep['structure']['errors'])}")
                continue
            meta = svc.store.add_template(f.stem, f.name, data)
            meta["inspection"] = rep
            svc.store._write(svc.store.template_dir(meta["id"]) / "meta.json", meta)
            render(svc.store.template_dir(meta["id"]) / "doc.docx", svc.store.template_dir(meta["id"]) / "preview", dpi=40)
            if args.default and f.name == Path(args.default).name:
                svc.store.set_default_template(meta["id"])
            ai = rep.get("ai") or {}
            print(f"added {f.name}: {rep['verdict']} {ai.get('document_type', '')}")
        return 0

    from .engine import apply_plan, build_package_outline, plain_text, run_audits
    from .pipeline.service import load_base, parse_ops

    base = load_base(Path(args.docx))
    if args.cmd == "outline":
        print(build_package_outline(base).text())
        return 0

    raw = json.loads(Path(args.plan).read_text())
    plan = raw if isinstance(raw, dict) else {"ops": raw, "fact_changes": []}
    ops, errors = parse_ops(plan["ops"])
    for e in errors:
        print("invalid:", e, file=sys.stderr)
    res = apply_plan(base, ops)
    for r in res.results:
        if not r.ok:
            print(f"op {r.index + 1} failed: {r.error}", file=sys.stderr)
    res.package.save(args.out)
    for f in run_audits(base, res.package, res.new_texts, plain_text(base) + json.dumps(plan),
                        plan.get("fact_changes", [])):
        print(f"[{f['level']}] {f['check']}: {f['message']}")
        for d in f["details"]:
            print("   -", d)
    print(f"saved {args.out}: {len(res.results) - len(res.errors)}/{len(res.results)} ops applied")
    return 1 if res.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
