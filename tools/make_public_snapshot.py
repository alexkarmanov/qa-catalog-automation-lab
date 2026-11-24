"""Build the sanitized PUBLICATION CANDIDATE: an independent, clean-history snapshot of this project (standard library only).

It never touches Git history and publishes nothing. The snapshot is a plain file tree in a ZIP (no ``.git``): whoever publishes it
starts a NEW repository from it, so no historical Git object (and no 2023 course-derived file, binary, database or personal commit
metadata) can reach the public repository. How it relates to the privately preserved history is documented in
docs/PUBLICATION_CHECKLIST.md.

Rules enforced (the build aborts instead of producing a questionable candidate):
* requires a clean Git tree and uses Git-tracked files only; refuses to overwrite an existing ZIP;
* owner-private and process documents are excluded (provenance, rights, job-market research, CV/interview/assessment material,
  release decision, status, legacy baseline evidence); a few documents are replaced by their public versions;
* every text file is searched for personal data, machine identifiers, absolute paths, secrets and tokens; every binary type and
  size is checked; every relative Markdown link must resolve inside the snapshot;
* lines of the 2023 baseline must not survive (tools/ip_audit.py, 0 matches required);
* an external manifest (sizes + SHA-256) is written next to the ZIP and an audit record is printed.

Usage: python tools/make_public_snapshot.py --version 1.0.2 --name qa-catalog-automation-lab --out <dir>
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ip_audit  # noqa: E402
import package_common as pc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

RENAME: Dict[str, str] = {
    "docs/PUBLIC_README.md": "README.md",
    "docs/PUBLIC_CHANGELOG.md": "CHANGELOG.md",
}
# Never shipped: replaced by a public version above, or private/process material.
EXCLUDE_FILES = {
    "README.md", "CHANGELOG.md", "STATUS.md",
    "docs/GATE0_PROVENANCE.md", "docs/SOURCES_AND_RIGHTS.md", "docs/UNIQUENESS_GATE.md", "docs/LEGACY_AUDIT.md", "docs/LEGACY_MIGRATION_MAP.md",
    "docs/CV_LINKEDIN_UPWORK.md", "docs/CV_READY.md", "docs/INTERVIEW_QA.md", "docs/QA_SERVICE_SAMPLE.md", "docs/RELEASE_DECISION.md",
    "docs/OWNER_READINESS_ASSESSMENT.md", "docs/PUBLICATION_CHECKLIST.md", "docs/LICENCE_OPTIONS.md", "docs/REPORT_GENERATION_FAILED.md",
}
EXCLUDE_PREFIXES = ("docs/evidence/baseline_2023/", "docs/evidence/git_ancestry", "docs/evidence/REDACTION_LOG", "docs/evidence/private/")
LINE_DROP = ("private backup", "SOURCES_AND_RIGHTS", "private bundle")  # lines mentioning private artifacts are removed from kept docs
TEXT_REPLACEMENTS = [("the owner's ", "the author's "), ("The owner's ", "The author's "), ("the owner ", "the author "), ("The owner ", "The author ")]

MAX_FILE_BYTES = 8 * 1024 * 1024
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[=:]\s*[\"'][A-Za-z0-9/+_-]{16,}[\"']"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{16,}"),
]
ABSOLUTE_PATH_PATTERNS = [re.compile(r"[A-Za-z]:\\(?:Users|Documents)\\"), re.compile(r"/Users/[A-Za-z0-9_.-]+"), re.compile(r"/home/[A-Za-z0-9_.-]+/"),
                          re.compile("/private" + r"/(?:var|tmp)/"), re.compile(r"file:///(?!\.)[A-Za-z]")]
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


def select(tracked: List[str]) -> Dict[str, str]:
    """Map snapshot path -> source path for the files that may be published."""
    chosen: Dict[str, str] = {}
    for rel in tracked:
        if rel in RENAME:
            chosen[RENAME[rel]] = rel
        elif rel in EXCLUDE_FILES or rel.startswith(EXCLUDE_PREFIXES):
            continue
        else:
            chosen[rel] = rel
    return chosen


def transform(rel: str, data: bytes) -> bytes:
    """Public wording for kept Markdown: drop lines about private artifacts, address the author neutrally."""
    if not rel.endswith(".md"):
        return data
    lines = [ln for ln in data.decode("utf-8").splitlines() if not any(token in ln for token in LINE_DROP)]
    text = "\n".join(lines) + "\n"
    for old, new in TEXT_REPLACEMENTS:
        text = text.replace(old, new)
    return text.encode("utf-8")


def audit(files: Dict[str, bytes]) -> List[str]:
    """Return problems found in the proposed publication tree (empty list = clean)."""
    problems: List[str] = []
    for rel, data in sorted(files.items()):
        reason = pc.forbidden_reason(rel)
        if reason:
            problems.append("%s: %s" % (rel, reason))
        if len(data) > MAX_FILE_BYTES:
            problems.append("%s: larger than %d bytes" % (rel, MAX_FILE_BYTES))
        problems += pc.personal_data_hits(rel, data)
        if not pc.is_text_name(rel):
            continue
        text = data.decode("utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append("%s: looks like a secret or token" % rel)
        for pattern in ABSOLUTE_PATH_PATTERNS:
            if pattern.search(text):
                problems.append("%s: absolute path" % rel)
                break
    return problems


def broken_links(files: Dict[str, bytes]) -> List[str]:
    """Relative Markdown links that point at nothing inside the snapshot."""
    known = set(files)
    broken: List[str] = []
    for rel, data in sorted(files.items()):
        if not rel.endswith(".md"):
            continue
        base = Path(rel).parent
        for target in LINK.findall(data.decode("utf-8", errors="replace")):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "mailto:")):
                continue
            resolved = (base / target).as_posix()
            parts: List[str] = []
            for piece in resolved.split("/"):
                if piece == "..":
                    if parts:
                        parts.pop()
                elif piece not in ("", "."):
                    parts.append(piece)
            path = "/".join(parts)
            if path not in known and not any(k.startswith(path + "/") for k in known):
                broken.append("%s -> %s" % (rel, target))
    return broken


def build(tracked: List[str], read) -> Tuple[Dict[str, bytes], Dict[str, str]]:
    chosen = select(tracked)
    files = {dst: transform(dst, read(src)) for dst, src in chosen.items()}
    return files, chosen


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--name", default="qa-catalog-automation-lab", help="proposed public repository name (also the ZIP's top folder)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    zip_path = out / ("%s_publication_candidate_v%s.zip" % (args.name, args.version))
    manifest_path = out / ("%s_publication_candidate_v%s_MANIFEST.txt" % (args.name, args.version))
    if zip_path.exists() or manifest_path.exists():
        print("REFUSING to overwrite an existing candidate in %s" % out, file=sys.stderr)
        return 2
    if git("status", "--porcelain").strip():
        print("REFUSING: the working tree is not clean; commit first so the candidate equals a commit.", file=sys.stderr)
        return 2
    tracked = git("ls-files").splitlines()
    files, _ = build(tracked, lambda rel: (ROOT / rel).read_bytes())
    for required in ("README.md", "CHANGELOG.md", "docs/LIMITATIONS.md"):
        if required not in files:
            print("REFUSING: the public version %s is missing (expected one of %s)" % (required, sorted(RENAME)), file=sys.stderr)
            return 2
    problems = audit(files)
    problems += ["broken link: " + b for b in broken_links(files)]
    staging = Path(ROOT / ".public_snapshot_check")
    if staging.exists():
        print("REFUSING: leftover staging folder", file=sys.stderr)
        return 2
    try:
        staging.mkdir()
        for rel, data in files.items():
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        base = ip_audit.baseline_lines("legacy-2023-baseline", 24)
        hits = ip_audit.scan_tree(staging, base, 24)
        problems += ["2023 baseline line survives in %s:%d (matches %s)" % h for h in hits]
    finally:
        shutil.rmtree(str(staging), ignore_errors=True)
    if problems:
        print("REFUSING: the publication candidate is not clean:", *problems[:40], sep="\n  ", file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "x", zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(files):
            info = zipfile.ZipInfo("%s/%s" % (args.name, rel), date_time=(2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[rel])
    with zipfile.ZipFile(str(zip_path)) as archive:
        if archive.testzip() is not None or pc.check_zip_entries(archive.infolist()):
            print("ZIP check failed", file=sys.stderr)
            return 3
    manifest_path.write_text(pc.build_manifest(files), encoding="utf-8")
    excluded = sorted(set(tracked) - set(select(tracked).values()))
    print("publication candidate written: %s (%d files, %d tracked files excluded)" % (zip_path.name, len(files), len(excluded)))
    print("audit: personal data / paths / secrets / binaries / sizes: clean; broken links: 0; 2023 baseline lines surviving: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
