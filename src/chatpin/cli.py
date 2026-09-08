import argparse
import difflib
import json
from pathlib import Path
import re
import sys
from . import __version__
from .analysis import analyze
from .locking import load_lock, make_lock, write_file
from .sources import ChatpinError, extract, select


def emit(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=True, indent=2))
        return
    # Escape terminal control characters from untrusted sources and diffs.
    def safe(value):
        return "".join(c if c in "\n\t" or (c.isprintable() and c != "\x1b") else repr(c)[1:-1] for c in str(value))
    print(safe(value.get("status", "report").upper()))
    for key, val in value.items():
        if key == "status":
            continue
        if key == "diff":
            print(safe(val))
        elif isinstance(val, (list, dict)):
            print(f"{key}: {json.dumps(val, ensure_ascii=True, indent=2)}")
        else:
            print(f"{key}: {safe(val)}")


def parser():
    p = argparse.ArgumentParser(description="Review and pin LLM chat templates without executing them.")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("scan", "diff", "lock", "check", "extract", "export", "fetch"):
        s = commands.add_parser(name)
        s.add_argument("--json", action="store_true", help="Machine-readable output")
        if name in ("scan", "diff", "lock", "check", "extract"):
            s.add_argument("source", help="Local model directory or template/GGUF/tokenizer file")
            s.add_argument("--template", help="Exact named template to select")
        if name in ("diff", "lock"):
            s.add_argument("--upstream", required=name == "diff", help="Trusted local upstream template or checkout")
            s.add_argument("--upstream-template", help="Named upstream template; defaults to candidate name")
        if name in ("check", "export"):
            s.add_argument("--lock", default="chatpin.lock.json")
        if name in ("lock", "extract", "export", "fetch"):
            s.add_argument("--output", "-o", required=name != "lock", default="chatpin.lock.json")
            s.add_argument("--force", action="store_true", help="Explicitly replace an existing output")
        if name == "scan":
            s.add_argument("--fail-on", choices=("review", "high", "none"), default="review")
        if name == "lock":
            s.add_argument("--reviewed", action="store_true", help="Confirm this template was reviewed as the trust baseline")
        if name == "fetch":
            s.add_argument("repo", help="Hugging Face owner/repository")
            s.add_argument("--revision", required=True, help="Immutable full 40-character commit SHA")
            s.add_argument("--filename", default="chat_template.jinja", help="Template or tokenizer JSON only")
    return p


def run(args):
    command = args.command
    if command == "fetch":
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision):
            raise ChatpinError("Provide owner/repo and a full immutable commit SHA")
        filename = args.filename
        parts = filename.split("/")
        if any(p in ("", ".", "..") for p in parts) or "\\" in filename or not (filename.endswith(".jinja") or filename == "tokenizer_config.json"):
            raise ChatpinError("Only a relative Jinja path or tokenizer_config.json may be fetched")
        if Path(args.output).suffix != Path(filename).suffix:
            raise ChatpinError("Output must preserve the fetched file extension")
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise ChatpinError('Install the Hub extra: pip install ".[hub]"') from exc
        try:
            cached = hf_hub_download(repo_id=args.repo, filename=filename, revision=args.revision)
        except Exception as exc:
            raise ChatpinError(f"Hub download failed ({type(exc).__name__}); check repository, revision, and authentication") from exc
        # Validate before persisting; never load remote Python or model weights.
        templates = extract(cached)
        from .sources import read_bounded, MAX_CONFIG
        write_file(args.output, read_bounded(cached, MAX_CONFIG), args.force)
        return {"status": "fetched", "repo": args.repo, "revision": args.revision,
                "filename": filename, "output": args.output,
                "templates": [t.summary() for t in templates.values()]}, 0
    if command == "scan":
        values = extract(args.source)
        if args.template:
            values = {args.template: select(args.source, args.template)}
        reports = [{**t.summary(), "findings": analyze(t.text)} for t in values.values()]
        findings = [f for r in reports for f in r["findings"]]
        fail = any(args.fail_on == "review" or (args.fail_on == "high" and f["severity"] == "high") for f in findings)
        return {"status": "review_required" if findings else "no_findings",
                "templates": reports, "note": "Heuristic findings are review signals, not proof of compromise. No findings does not establish safety."}, int(fail)
    if command in ("check", "export"):
        lock = load_lock(args.lock)
        entry = lock["template"]
        if command == "export":
            write_file(args.output, entry["text"].encode("utf-8"), args.force)
            return {"status": "exported", "sha256": entry["sha256"], "output": args.output}, 0
        if args.template and args.template != entry["name"]:
            raise ChatpinError("Selected template name does not match the lockfile")
        template = select(args.source, entry["name"])
        matches = template.sha256 == entry["sha256"]
        return {"status": "match" if matches else "drift", "expected": entry["sha256"],
                "actual": template.sha256, "template": template.name}, 0 if matches else 1
    template = select(args.source, args.template)
    if command == "extract":
        write_file(args.output, template.text.encode("utf-8"), args.force)
        return {"status": "extracted", **template.summary(), "output": args.output}, 0
    upstream = None
    if args.upstream:
        upstream = select(args.upstream, args.upstream_template or template.name)
    if command == "diff":
        same = template.sha256 == upstream.sha256
        diff = "".join(difflib.unified_diff(upstream.text.splitlines(keepends=True), template.text.splitlines(keepends=True),
                                          fromfile="trusted-upstream", tofile="candidate"))
        return {"status": "match" if same else "drift", "candidate": template.summary(),
                "upstream": upstream.summary(), "diff": diff,
                "candidate_findings": analyze(template.text), "upstream_findings": analyze(upstream.text)}, 0 if same else 1
    if not args.reviewed:
        raise ChatpinError("Review the template first, then pass --reviewed to establish the trust baseline")
    findings = analyze(template.text)
    if any(f["code"] == "CP003" for f in findings):
        raise ChatpinError("Cannot pin external template dependencies; inline and review them first")
    if upstream and template.sha256 != upstream.sha256:
        return {"status": "drift", "message": "Refusing to lock a candidate that differs from the supplied trusted upstream"}, 1
    write_file(args.output, make_lock(template, upstream), args.force)
    return {"status": "locked", **template.summary(), "output": args.output, "findings": findings}, 0


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        report, code = run(args)
    except (ChatpinError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        report, code = {"status": "error", "message": str(exc)}, 2
    emit(report, args.json)
    return code
