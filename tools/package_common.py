"""Shared helpers for packaging and clean verification (standard library only)."""
from __future__ import annotations

import hashlib
import re
import socket
import stat
import unicodedata
import zipfile
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Tuple

MANIFEST_NAME = "PACKAGE_MANIFEST.txt"

# Files and directories that must never be in a review package.
FORBIDDEN_DIRS = {".git", ".venv", "venv", ".pw-browsers", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "artifacts", "dist"}
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".exe", ".bundle")

# Personal-data patterns that must not appear in any text file of the package.
PERSONAL_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9_. -]+"),
    re.compile(r"/home/[A-Za-z0-9_.-]+/"),
    re.compile(r"[A-Za-z0-9_.+-]{1,64}@(?:gmail|outlook|yahoo|hotmail)\.com", re.I),  # bounded: linear time on huge files
    re.compile("Alex" + " " + "Karmy"),
    re.compile("/var" + "/folders/"),
]
TEXT_SUFFIXES = {".md", ".txt", ".py", ".ini", ".toml", ".yml", ".yaml", ".json", ".xml", ".html", ".csv", ".sql", ".cfg", ".gitignore", ""}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_text_name(rel: str) -> bool:
    return PurePosixPath(rel).suffix.lower() in TEXT_SUFFIXES


def forbidden_reason(rel: str) -> str:
    parts = set(PurePosixPath(rel).parts)
    if parts & FORBIDDEN_DIRS or any(part.startswith(".venv") for part in parts):
        return "forbidden directory"
    if rel.lower().endswith(FORBIDDEN_SUFFIXES):
        return "forbidden file type"
    return ""


_JUNIT_HOST = re.compile(r'hostname="(?!redacted")[^"]*"')


def local_host_names() -> List[str]:
    """This machine's host names (full and short); never written to any output, only searched for."""
    names = {socket.gethostname(), socket.gethostname().split(".")[0]}
    return sorted((n for n in names if len(n) >= 4 and n.lower() not in ("localhost", "local")), key=len, reverse=True)


def personal_data_hits(rel: str, data: bytes) -> List[str]:
    if not is_text_name(rel):
        return []
    text = data.decode("utf-8", errors="replace")
    hits = []
    for pattern in PERSONAL_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append("%s: %r" % (rel, match.group(0)[:40]))
    if rel.endswith(".xml") and _JUNIT_HOST.search(text):
        hits.append("%s: machine host name attribute" % rel)  # the value itself is deliberately not echoed
    if any(name in text for name in local_host_names()):
        hits.append("%s: this machine's host name" % rel)
    return hits


def build_manifest(files: Dict[str, bytes]) -> str:
    """Lines ``sha256  size  path`` for every file, sorted; the manifest never lists itself."""
    lines = ["%s  %d  %s" % (sha256_bytes(data), len(data), rel) for rel, data in sorted(files.items()) if rel != MANIFEST_NAME]
    return "\n".join(lines) + "\n"


def parse_manifest(text: str) -> Dict[str, Tuple[str, int]]:
    """Return ``{path: (sha256, size)}``; a malformed or duplicated line raises ValueError."""
    entries: Dict[str, Tuple[str, int]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 2)
        if len(parts) != 3:
            raise ValueError("malformed manifest line: %r" % line[:80])
        digest, size, rel = parts
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not size.isdigit():
            raise ValueError("malformed manifest line: %r" % line[:80])
        if rel in entries:
            raise ValueError("duplicate manifest entry: %s" % rel)
        entries[rel] = (digest, int(size))
    return entries


def verify_inventory(actual: Dict[str, bytes], manifest_text: str) -> List[str]:
    """Compare the exact set of files and their hashes with the manifest; return a list of problems (empty = exact match)."""
    try:
        expected = parse_manifest(manifest_text)
    except ValueError as exc:
        return [str(exc)]
    problems: List[str] = []
    present = {rel: data for rel, data in actual.items() if rel != MANIFEST_NAME}
    for rel in sorted(set(expected) - set(present)):
        problems.append("missing from package: " + rel)
    for rel in sorted(set(present) - set(expected)):
        problems.append("not in manifest: " + rel)
    for rel in sorted(set(present) & set(expected)):
        digest, size = expected[rel]
        if len(present[rel]) != size:  # the recorded byte length is evidence too, not just the digest
            problems.append("size mismatch: %s (manifest %d, actual %d)" % (rel, size, len(present[rel])))
        if sha256_bytes(present[rel]) != digest:
            problems.append("hash mismatch: " + rel)
    if not expected:
        problems.append("manifest is empty")
    return problems


# -- archive entry validation (run BEFORE anything is extracted) --------------------------------------------------
MAX_ENTRIES = 5000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
_ALLOWED_COMPRESSION = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)


def _name_problem(name: str) -> str:
    if not name:
        return "empty entry name"
    if name.startswith("/") or "\\" in name or re.match(r"^[A-Za-z]:", name):
        return "absolute or drive-qualified path"
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        return "control character in the name"
    parts = name.rstrip("/").split("/") if name.endswith("/") else name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "empty, '.' or '..' path component"
    return ""


def check_zip_entries(infos: Iterable[zipfile.ZipInfo]) -> List[str]:
    """Return problems that make a ZIP unsafe or ambiguous to extract; an empty list means acceptable.

    Rejected: duplicate entries (also after case-folding / Unicode normalization, because two names could land on
    one file), absolute, drive-qualified, backslash, empty, '.' or '..' path parts, control characters, symlinks and
    other special files, encrypted entries, unsupported compression, and implausible entry counts or sizes.
    """
    problems: List[str] = []
    seen: Dict[str, str] = {}
    entries = list(infos)
    if len(entries) > MAX_ENTRIES:
        problems.append("too many entries (%d > %d)" % (len(entries), MAX_ENTRIES))
    if sum(info.file_size for info in entries) > MAX_TOTAL_BYTES:
        problems.append("declared uncompressed size is implausibly large")
    for info in entries:
        name = info.filename
        reason = _name_problem(name)
        if reason:
            problems.append("unsafe entry %r: %s" % (name, reason))
            continue
        key = unicodedata.normalize("NFC", name.rstrip("/")).casefold()
        if key in seen:
            problems.append("duplicate or ambiguous entry: %r (collides with %r)" % (name, seen[key]))
        else:
            seen[key] = name
        kind = stat.S_IFMT(info.external_attr >> 16)  # 0 = no file-type bits recorded (common): treated as regular
        if kind and not info.is_dir() and kind != stat.S_IFREG:
            problems.append("unsupported entry type (not a regular file): %r" % name)
        if kind and info.is_dir() and kind != stat.S_IFDIR:
            problems.append("directory entry with a non-directory mode: %r" % name)
        if info.flag_bits & 0x1:
            problems.append("encrypted entry: %r" % name)
        if info.compress_type not in _ALLOWED_COMPRESSION:
            problems.append("unsupported compression for %r" % name)
    return problems
