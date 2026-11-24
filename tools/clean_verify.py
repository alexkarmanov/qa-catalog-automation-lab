"""Clean verification of the final review ZIP (standard library only; run with any Python 3.9+).

What it does, in order (each command's exact expected exit status is recorded; any mismatch fails the run):
 1. checks the ZIP's SHA-256 against the expected value,
 2. extracts it into a *unique temporary directory that this run creates* (never overwrites or deletes anything else),
 2b. before extracting, rejects duplicate/ambiguous entries, unsafe paths and unsupported entry types (symlinks, devices, encryption),
 3. compares the extracted file inventory, byte sizes and SHA-256 hashes with PACKAGE_MANIFEST.txt exactly,
 4. rejects forbidden content (.git, .venv, caches, *.db, *.exe, *.pyc, bundles) and personal paths/e-mail addresses,
 5. creates a fresh virtualenv, installs from requirements.lock.txt, installs Chromium for Playwright,
 6. runs tools/uat.py (11 steps including the full suite, lint, types, a seeded defect and the failure path),
 7. removes only the temporary directory it created.
The log goes to a path OUTSIDE the ZIP given with --log; checksums are produced separately by the caller.

Usage: python tools/clean_verify.py --zip <zip> --sha256 <hex> --log <file> --expected-tests N
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_common as pc  # noqa: E402

FAILURES: List[str] = []
LOG: List[str] = []


def log(message: str) -> None:
    LOG.append(message)
    print(message, flush=True)


def expect_exit(name: str, cmd: List[str], expected: int, cwd: Path, env: Optional[Dict[str, str]] = None, timeout: int = 3600) -> int:
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
    log("$ %s" % " ".join(os.path.basename(c) if c == sys.executable else c for c in cmd))
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-25:]
    for line in tail:
        log("    " + line)
    ok = proc.returncode == expected
    log("[%s] %s: exit %d (expected %d) in %.1f s" % ("OK" if ok else "FAIL", name, proc.returncode, expected, time.monotonic() - started))
    if not ok:
        FAILURES.append("%s: exit %d, expected %d" % (name, proc.returncode, expected))
    return proc.returncode


def read_zip(zip_path: Path) -> Tuple[Dict[str, bytes], str]:
    """Return ({relative path: bytes}, top-level folder); rejects absolute paths, '..' and several top-level folders."""
    files: Dict[str, bytes] = {}
    roots = set()
    with zipfile.ZipFile(str(zip_path)) as archive:
        bad = pc.check_zip_entries(archive.infolist())  # nothing is read or extracted unless every entry is acceptable
        if bad:
            raise ValueError("unacceptable ZIP entries: " + "; ".join(bad[:5]))
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or "\\" in name:
                raise ValueError("unsafe path in ZIP: %r" % name)
            roots.add(parts[0])
            files["/".join(parts[1:])] = archive.read(info)
    if len(roots) != 1:
        raise ValueError("ZIP must contain exactly one top-level folder, found %s" % sorted(roots))
    return files, roots.pop()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--expected-tests", type=int, required=True)
    parser.add_argument("--external-manifest", default=None,
                        help="manifest file kept OUTSIDE the ZIP (used for the public snapshot, which carries no manifest of its own)")
    parser.add_argument("--skip-install", action="store_true", help="verify package integrity only (used by the tests of this tool)")
    args = parser.parse_args(argv)
    zip_path = Path(args.zip)
    log_path = Path(args.log)
    if log_path.exists():
        print("REFUSING to overwrite an existing log: %s" % log_path, file=sys.stderr)
        return 2
    if zipfile.is_zipfile(str(zip_path)) and str(log_path.resolve()).startswith(str(zip_path.resolve().parent / "extracted")):
        print("log must not live inside an extracted package", file=sys.stderr)
        return 2
    log("clean verification started %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log("python %s on %s" % (sys.version.split()[0], sys.platform))
    tmp = Path(tempfile.mkdtemp(prefix="kqa_clean_"))
    log("owned temporary directory: %s" % tmp.name)
    try:
        # 1 checksum
        actual_hash = pc.sha256_bytes(zip_path.read_bytes()) if zip_path.exists() else "<missing zip>"
        ok = actual_hash == args.sha256.lower()
        log("[%s] ZIP sha256 %s (expected %s)" % ("OK" if ok else "FAIL", actual_hash, args.sha256.lower()))
        if not ok:
            FAILURES.append("zip checksum mismatch")
            raise RuntimeError("checksum mismatch - nothing was extracted")
        # 2 extract (in memory first: validates paths), then write
        files, root_name = read_zip(zip_path)
        project = tmp / root_name
        for rel, data in files.items():
            target = project / rel
            if project.resolve() not in target.resolve().parents:
                raise ValueError("entry would be written outside the owned directory: %r" % rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        log("[OK] extracted %d files into the owned temporary directory" % len(files))
        # 3 inventory
        manifest = files.get(pc.MANIFEST_NAME)
        if args.external_manifest:
            if manifest is not None:
                raise RuntimeError("the ZIP carries its own manifest although an external one was given")
            manifest = Path(args.external_manifest).read_bytes()
        if manifest is None:
            FAILURES.append("manifest missing")
            raise RuntimeError("PACKAGE_MANIFEST.txt is missing")
        problems = pc.verify_inventory(files, manifest.decode("utf-8"))
        for problem in problems[:20]:
            log("    inventory problem: " + problem)
        log("[%s] exact inventory/hash check against PACKAGE_MANIFEST.txt (%d problems)" % ("OK" if not problems else "FAIL", len(problems)))
        if problems:
            FAILURES.append("inventory mismatch")
        # 4 forbidden content and personal data
        bad = [rel for rel in files if pc.forbidden_reason(rel)]
        hits = [h for rel, data in files.items() for h in pc.personal_data_hits(rel, data)]
        log("[%s] forbidden files: %s" % ("OK" if not bad else "FAIL", bad or "none"))
        log("[%s] personal paths / e-mail addresses: %s" % ("OK" if not hits else "FAIL", hits[:5] or "none"))
        if bad or hits:
            FAILURES.append("forbidden or personal content present")
        if args.skip_install:
            log("(--skip-install: environment steps not run)")
        elif not FAILURES:
            env = dict(os.environ)
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(project / ".pw-browsers")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            venv = tmp / "venv"
            expect_exit("create virtualenv", [sys.executable, "-m", "venv", str(venv)], 0, project)
            vpy = str(venv / ("Scripts" if os.name == "nt" else "bin") / "python")
            expect_exit("pip install -r requirements.lock.txt", [vpy, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.lock.txt"], 0, project, env)
            expect_exit("playwright install chromium", [vpy, "-m", "playwright", "install", "chromium"], 0, project, env)
            out_dir = tmp / "uat_out"
            expect_exit("scripted UAT (tools/uat.py)", [vpy, "tools/uat.py", "--expected-tests", str(args.expected_tests), "--out", str(out_dir),
                                                          "--result-md", str(tmp / "UAT_RESULT.md")], 0, project, env)
            if (tmp / "UAT_RESULT.md").exists():
                for line in (tmp / "UAT_RESULT.md").read_text(encoding="utf-8").splitlines():
                    log("    " + line)
    except Exception as exc:  # noqa: BLE001 - always recorded
        log("[FAIL] %s: %s" % (type(exc).__name__, exc))
        if not FAILURES:
            FAILURES.append("%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)  # only the directory created above
        log("removed owned temporary directory (exists now: %s)" % tmp.exists())
    log("RESULT: %s" % ("PASS" if not FAILURES else "FAIL - " + "; ".join(FAILURES)))
    log_path.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
