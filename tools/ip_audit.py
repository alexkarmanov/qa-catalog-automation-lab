"""Find lines of the historical (2023, course-based) repository that survive in a candidate publication tree.

Compares normalized source lines of every text file of the baseline tag against every text file of a directory. Lines
shorter than ``--min-chars`` and trivial boilerplate (imports, decorators, bare brackets) are ignored. It reports
``candidate-file:line`` and the baseline file only: the matched text itself is never printed, so the report is safe to
store. A match is a *lead for review*, not proof of copying (a short idiomatic statement can coincide), and the absence of
matches is evidence, not a legal clearance.

Usage: python tools/ip_audit.py --tree <dir> [--baseline legacy-2023-baseline] [--min-chars 24] [--fail-on-match]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".ini", ".toml", ".yml", ".yaml", ".cfg", ".sql", ".html", ".json"}
TRIVIAL = re.compile(r"^(import |from \S+ import |@pytest\.mark\.\w+$|[\]\[(){}:,.\"' ]*$|#!|\"\"\"|'''|return$|pass$"
                     r"|def __init__\(self\)( -> None)?:$|class \w+\(\w+\):$)")


def normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def baseline_lines(tag: str, min_chars: int) -> Dict[str, Set[str]]:
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", tag], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.splitlines()
    out: Dict[str, Set[str]] = {}
    for name in names:
        if Path(name).suffix.lower() not in TEXT_SUFFIXES:
            continue
        blob = subprocess.run(["git", "show", "%s:%s" % (tag, name)], cwd=str(ROOT), capture_output=True).stdout
        lines = {normalize(ln) for ln in blob.decode("utf-8", errors="replace").splitlines()}
        out[name] = {ln for ln in lines if len(ln) >= min_chars and not TRIVIAL.match(ln)}
    return out


def scan_tree(tree: Path, base: Dict[str, Set[str]], min_chars: int) -> List[Tuple[str, int, str]]:
    index: Dict[str, str] = {}
    for name, lines in base.items():
        for ln in lines:
            index.setdefault(ln, name)
    hits: List[Tuple[str, int, str]] = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or any(p in (".git", ".venv", ".venv312", ".pw-browsers") for p in path.parts):
            continue
        for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            ln = normalize(raw)
            if len(ln) >= min_chars and ln in index:
                hits.append((str(path.relative_to(tree)), number, index[ln]))
    return hits


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", required=True)
    parser.add_argument("--baseline", default="legacy-2023-baseline")
    parser.add_argument("--min-chars", type=int, default=24)
    parser.add_argument("--fail-on-match", action="store_true")
    args = parser.parse_args(argv)
    base = baseline_lines(args.baseline, args.min_chars)
    hits = scan_tree(Path(args.tree), base, args.min_chars)
    total = sum(len(v) for v in base.values())
    print("baseline: %d files, %d distinctive lines; candidate matches: %d" % (len(base), total, len(hits)))
    per_file: Dict[str, int] = {}
    for rel, _, _ in hits:
        per_file[rel] = per_file.get(rel, 0) + 1
    for rel, count in sorted(per_file.items()):
        print("  %-60s %d line(s)" % (rel, count))
    for rel, number, origin in hits[:200]:
        print("  %s:%d  == %s" % (rel, number, origin))
    return 1 if (hits and args.fail_on_match) else 0


if __name__ == "__main__":
    sys.exit(main())
