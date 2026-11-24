"""Build the versioned review ZIP from the committed tree (standard library only).

Safety rules enforced here (the build aborts instead of producing a bad package):
* refuses to overwrite an existing ZIP;
* requires a clean Git working tree (the package equals a commit);
* includes only Git-tracked files (so .venv, caches, artifacts, old DB/exe, bundles can never slip in) and re-checks every name;
* scans every text file for personal paths/e-mail addresses; generated evidence files (docs/evidence/run) are redacted in the
  exported copy and every substitution is recorded in docs/evidence/REDACTION_LOG.md; any remaining hit aborts the build;
* writes a manifest that covers every file except itself, plus sanitized Git evidence (no author e-mail addresses).

Usage: python tools/make_package.py --version 1.0 --out dist
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_common as pc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REDACT_UNDER = "docs/evidence/run/"
REDACTIONS = [
    (re.compile(r'hostname="[^"]*"'), 'hostname="redacted"'),
    (re.compile(r"/Users/[^\s\"'<>)\]]*"), "<PATH>"),
    (re.compile(r"/private/(?:var|tmp)/[^\s\"'<>)\]]*"), "<PATH>"),
    (re.compile("/var" + r"/folders/[^\s\"'<>)\]]*"), "<PATH>"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


def git_evidence() -> str:
    head = git("rev-parse", "HEAD").strip()
    baseline = git("rev-parse", "legacy-2023-baseline").strip()
    tree = git("rev-parse", "legacy-2023-baseline^{tree}").strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", "legacy-2023-baseline", "HEAD"], cwd=str(ROOT)).returncode == 0
    log = git("log", "--reverse", "--format=%h %ad %s", "--date=short")
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    lines = [
        "Sanitized Git evidence (author names and e-mail addresses omitted).",
        "branch: %s" % branch,
        "modern HEAD: %s" % head,
        "historical baseline tag legacy-2023-baseline: %s (tree %s)" % (baseline, tree),
        "baseline is an ancestor of modern HEAD: %s" % ("YES" if ancestor else "NO"),
        "commit count on this branch: %s" % git("rev-list", "--count", "HEAD").strip(),
        "",
        "history (oldest first):",
    ]
    lines += ["  " + line for line in log.splitlines()]
    return "\n".join(lines) + "\n"


def redact(rel: str, data: bytes, log: List[str]) -> bytes:
    if not rel.startswith(REDACT_UNDER) or not pc.is_text_name(rel):
        return data
    text = data.decode("utf-8", errors="replace")
    total = 0
    for pattern, replacement in REDACTIONS:
        text, count = pattern.subn(replacement, text)
        total += count
    if total:
        log.append("| %s | %d |" % (rel, total))
    return text.encode("utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    zip_path = out_dir / ("Karmanov_QA_Automation_Review_Package_v%s.zip" % args.version)
    if zip_path.exists():
        print("REFUSING to overwrite existing package: %s" % zip_path, file=sys.stderr)
        return 2
    if git("status", "--porcelain").strip():
        print("REFUSING: the working tree is not clean; commit first so the package equals a commit.", file=sys.stderr)
        return 2

    files: Dict[str, bytes] = {}
    redaction_rows: List[str] = []
    for rel in git("ls-files").splitlines():
        reason = pc.forbidden_reason(rel)
        if reason:
            print("REFUSING: tracked file %s is a %s" % (rel, reason), file=sys.stderr)
            return 2
        files[rel] = redact(rel, (ROOT / rel).read_bytes(), redaction_rows)
    files["docs/evidence/git_ancestry.txt"] = git_evidence().encode("utf-8")
    log_lines = ["# Redaction log for the exported review package", "",
                 "Generated evidence files under `docs/evidence/run/` are redacted in the exported copy only (the working tree is untouched). "
                 "Personal filesystem paths were replaced by `<PATH>`.", "",
                 "| File | Substitutions |", "|---|---|"] + (redaction_rows or ["| (none needed) | 0 |"])
    files["docs/evidence/REDACTION_LOG.md"] = ("\n".join(log_lines) + "\n").encode("utf-8")

    hits: List[str] = []
    for rel, data in files.items():
        hits += pc.personal_data_hits(rel, data)
    if hits:
        print("REFUSING: personal data found in the package content:", *hits, sep="\n  ", file=sys.stderr)
        return 2

    files[pc.MANIFEST_NAME] = pc.build_manifest(files).encode("utf-8")
    root_name = "karmanovqaauto_review_package_v%s" % args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "x", zipfile.ZIP_DEFLATED) as archive:  # mode "x": never overwrite
        for rel in sorted(files):
            info = zipfile.ZipInfo("%s/%s" % (root_name, rel), date_time=(2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[rel])
    with zipfile.ZipFile(str(zip_path)) as archive:
        if archive.testzip() is not None:
            print("ZIP integrity check failed", file=sys.stderr)
            return 3
        entry_problems = pc.check_zip_entries(archive.infolist())
        if entry_problems:
            print("ZIP entry check failed:", *entry_problems[:5], sep="\n  ", file=sys.stderr)
            return 3
    print("package written: %s (%d files)" % (zip_path, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
