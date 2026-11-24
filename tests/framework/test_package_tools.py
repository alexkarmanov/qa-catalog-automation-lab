"""Failure paths of the packaging/verification helpers: bad evidence must never become a pass."""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools import package_common as pc

pytestmark = [pytest.mark.framework, pytest.mark.negative]
ROOT = Path(__file__).resolve().parents[2]


def _files():
    return {"README.md": b"hello", "docs/a.md": b"alpha", "src/b.py": b"print(1)\n"}


def test_exact_inventory_matches():
    files = _files()
    manifest = pc.build_manifest(files)
    assert pc.verify_inventory(files, manifest) == []


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda f: f.pop("docs/a.md"), "missing from package: docs/a.md"),
        (lambda f: f.update({"extra.txt": b"x"}), "not in manifest: extra.txt"),
        (lambda f: f.update({"README.md": b"HELLO"}), "hash mismatch: README.md"),
    ],
    ids=["missing-file", "extra-file", "changed-file"],
)
def test_inventory_detects_missing_extra_and_changed_files(mutate, expected):
    files = _files()
    manifest = pc.build_manifest(files)
    mutate(files)
    assert expected in pc.verify_inventory(files, manifest)


def test_malformed_or_empty_manifest_is_a_problem_not_a_pass():
    assert pc.verify_inventory(_files(), "garbage line\n")
    assert "manifest is empty" in pc.verify_inventory({}, "")


def test_manifest_never_lists_itself():
    files = dict(_files(), **{pc.MANIFEST_NAME: b"whatever"})
    assert pc.MANIFEST_NAME not in pc.parse_manifest(pc.build_manifest(files))


@pytest.mark.parametrize("name", [".git/config", ".venv/bin/python", "x/__pycache__/m.cpython-39.pyc", "data/old.db", "bin/chromedriver.exe", "private.bundle"])
def test_forbidden_content_is_recognized(name):
    assert pc.forbidden_reason(name)


@pytest.mark.parametrize(
    "text",
    ["see /Us" + "ers/someone/project", "mail me at person@" + "gmail.com", "path /ho" + "me/dev/x/", "Alex" + " Karmy folder"],
    ids=["mac-home-path", "webmail-address", "linux-home-path", "owner-path-name"],
)
def test_personal_data_is_recognized(text):
    assert pc.personal_data_hits("docs/x.md", text.encode())


def test_clean_text_has_no_personal_data():
    assert pc.personal_data_hits("docs/x.md", b"nothing personal here, only <PERSONAL_PATH>") == []


def _tiny_package(tmp_path, tamper):
    files = {"README.md": b"hello", "docs/a.md": b"alpha"}
    manifest = pc.build_manifest(files)
    stored = dict(files)
    stored[pc.MANIFEST_NAME] = manifest.encode()
    if tamper:
        stored["docs/a.md"] = b"tampered"
    path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(str(path), "w") as archive:
        for rel, data in stored.items():
            archive.writestr("pkgroot/" + rel, data)
    return path


def _run_clean_verify(tmp_path, zip_path, sha, name):
    log = tmp_path / name
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "clean_verify.py"), "--zip", str(zip_path), "--sha256", sha, "--log", str(log),
                           "--expected-tests", "1", "--skip-install"], capture_output=True, text=True)
    return proc, log


def test_clean_verify_passes_a_consistent_package_and_fails_a_tampered_one(tmp_path):
    good = _tiny_package(tmp_path, tamper=False)
    sha = pc.sha256_bytes(good.read_bytes())
    proc, log = _run_clean_verify(tmp_path, good, sha, "good.log")
    assert proc.returncode == 0, proc.stdout
    assert "RESULT: PASS" in log.read_text()

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad = _tiny_package(bad_dir, tamper=True)
    proc, log = _run_clean_verify(tmp_path, bad, pc.sha256_bytes(bad.read_bytes()), "bad.log")
    assert proc.returncode == 1  # the manifest no longer matches the content
    assert "hash mismatch: docs/a.md" in log.read_text()
    assert "RESULT: FAIL" in log.read_text()


def test_clean_verify_fails_on_a_wrong_checksum_and_never_extracts(tmp_path):
    good = _tiny_package(tmp_path, tamper=False)
    proc, log = _run_clean_verify(tmp_path, good, "0" * 64, "wrong.log")
    assert proc.returncode == 1
    text = log.read_text()
    assert "checksum mismatch" in text
    assert "extracted" not in text.replace("nothing was extracted", "")


def test_clean_verify_refuses_to_overwrite_an_existing_log(tmp_path):
    good = _tiny_package(tmp_path, tamper=False)
    existing = tmp_path / "keep.log"
    existing.write_text("precious")
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "clean_verify.py"), "--zip", str(good), "--sha256", "0" * 64, "--log", str(existing),
                           "--expected-tests", "1", "--skip-install"], capture_output=True, text=True)
    assert proc.returncode == 2
    assert existing.read_text() == "precious"


def test_make_package_refuses_to_overwrite_an_existing_zip(tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    target = out / "Karmanov_QA_Automation_Review_Package_v9.9.zip"
    target.write_bytes(b"original")
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_package.py"), "--version", "9.9", "--out", str(out)], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "REFUSING to overwrite" in proc.stderr
    assert target.read_bytes() == b"original"


# ---- KQA-005: size verification and unsafe/ambiguous archive entries ---------------------------------------------
import stat as _stat  # noqa: E402
import zipfile as _zipfile  # noqa: E402

from tools import clean_verify as _cv  # noqa: E402


def test_manifest_size_must_match_the_actual_byte_length():
    files = _files()
    manifest = pc.build_manifest(files)
    forged = manifest.replace("  5  README.md", "  999  README.md")
    assert forged != manifest
    problems = pc.verify_inventory(files, forged)
    assert "size mismatch: README.md (manifest 999, actual 5)" in problems


def test_manifest_with_correct_hash_but_wrong_size_is_not_accepted():
    files = {"a.txt": b"abcdef"}
    digest = pc.sha256_bytes(b"abcdef")
    problems = pc.verify_inventory(files, "%s  7  a.txt\n" % digest)
    assert problems and "size mismatch" in problems[0]


def _zip_with(tmp_path, entries, name="p.zip"):
    path = tmp_path / name
    with _zipfile.ZipFile(str(path), "w") as archive:
        for entry in entries:
            info = _zipfile.ZipInfo(entry[0]) if isinstance(entry, tuple) else entry
            data = entry[1] if isinstance(entry, tuple) else b""
            info.external_attr = (entry[2] if isinstance(entry, tuple) and len(entry) > 2 else 0o100644) << 16
            archive.writestr(info, data)
    return path


def _verify(zip_path, tmp_path, sha=None, name="log.txt"):
    digest = sha or pc.sha256_bytes(zip_path.read_bytes())
    code = _cv.main(["--zip", str(zip_path), "--sha256", digest, "--log", str(tmp_path / name), "--expected-tests", "1", "--skip-install"])
    _cv.FAILURES.clear()
    _cv.LOG.clear()
    return code


def _valid_package(tmp_path, extra=()):
    files = {"README.md": b"hello", "docs/a.md": b"alpha"}
    manifest = pc.build_manifest(files).encode()
    entries = [("root/%s" % rel, data) for rel, data in files.items()] + [("root/" + pc.MANIFEST_NAME, manifest)]
    return _zip_with(tmp_path, entries + list(extra))


def test_a_valid_package_is_accepted_by_the_verifier(tmp_path):
    assert _verify(_valid_package(tmp_path), tmp_path) == 0


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_duplicate_archive_entries_are_rejected_even_if_the_last_matches_the_manifest(tmp_path):
    files = {"README.md": b"hello"}
    manifest = pc.build_manifest(files).encode()
    zip_path = _zip_with(tmp_path, [("root/README.md", b"tampered"), ("root/README.md", b"hello"),
                                     ("root/" + pc.MANIFEST_NAME, manifest)])
    assert _verify(zip_path, tmp_path) != 0
    log = (tmp_path / "log.txt").read_text()
    assert "duplicate or ambiguous entry" in log and "RESULT: FAIL" in log


@pytest.mark.parametrize("name", ["root/Readme.MD", "root/./README.md", "root//README.md", "root/docs/../README.md"],
                         ids=["case-collision", "dot-part", "empty-part", "dotdot"])
def test_ambiguous_or_unsafe_paths_are_rejected(tmp_path, name):
    zip_path = _valid_package(tmp_path, [(name, b"hello")])
    assert _verify(zip_path, tmp_path) != 0


@pytest.mark.parametrize("name", ["/abs/README.md", "root\\evil.txt", "C:/win/x", "root/bad\x01name"],
                         ids=["absolute", "backslash", "drive", "control-char"])
def test_absolute_drive_backslash_and_control_names_are_rejected(tmp_path, name):
    info = _zipfile.ZipInfo("x")
    info.filename = name  # ZipInfo would otherwise normalise some separators
    zip_path = _valid_package(tmp_path, [info])
    assert _verify(zip_path, tmp_path) != 0


@pytest.mark.parametrize("mode", [_stat.S_IFLNK | 0o777, _stat.S_IFIFO | 0o644, _stat.S_IFCHR | 0o644],
                         ids=["symlink", "fifo", "device"])
def test_unsupported_entry_types_are_rejected_before_extraction(tmp_path, mode):
    zip_path = _valid_package(tmp_path, [("root/link", b"README.md", mode)])
    assert _verify(zip_path, tmp_path) != 0
    assert "not a regular file" in (tmp_path / "log.txt").read_text()


def test_encrypted_flag_is_rejected(tmp_path):
    info = _zipfile.ZipInfo("root/secret.bin")
    info.flag_bits |= 0x1
    problems = pc.check_zip_entries([info])
    assert any("encrypted" in p for p in problems)


def test_nothing_is_extracted_when_entries_are_rejected(tmp_path):
    zip_path = _valid_package(tmp_path, [("root/../../escape.txt", b"x")])
    assert _verify(zip_path, tmp_path) != 0
    assert not (tmp_path.parent / "escape.txt").exists()


def test_verifier_still_refuses_to_overwrite_an_existing_log(tmp_path):
    zip_path = _valid_package(tmp_path)
    (tmp_path / "log.txt").write_text("keep me")
    assert _verify(zip_path, tmp_path) == 2
    assert (tmp_path / "log.txt").read_text() == "keep me"


def test_check_zip_entries_accepts_a_normal_listing():
    infos = []
    for name in ("root/a.md", "root/docs/b.md", "root/docs/"):
        info = _zipfile.ZipInfo(name)
        info.external_attr = (0o40755 if name.endswith("/") else 0o100644) << 16
        infos.append(info)
    assert pc.check_zip_entries(infos) == []


def test_local_host_name_in_package_content_is_a_personal_data_hit():
    names = pc.local_host_names()
    if not names:
        pytest.skip("no usable local host name on this machine")
    hits = pc.personal_data_hits("docs/x.md", ("built on " + names[0]).encode())
    assert hits and names[0] not in "".join(hits)  # reported, but the name itself is never echoed


def test_junit_host_attribute_must_be_redacted():
    xml = b'<testsuite name="pytest" ' + b'host' + b'name="some-machine.example"></testsuite>'
    assert pc.personal_data_hits("docs/evidence/run/j.xml", xml)
    assert not pc.personal_data_hits("docs/evidence/run/j.xml", xml.replace(b"some-machine.example", b"redacted"))


def test_external_manifest_mode_verifies_a_zip_without_its_own_manifest(tmp_path):
    files = {"README.md": b"hello", "docs/a.md": b"alpha"}
    zip_path = _zip_with(tmp_path, [("root/%s" % rel, data) for rel, data in files.items()])
    manifest = tmp_path / "external_manifest.txt"
    manifest.write_text(pc.build_manifest(files))
    sha = pc.sha256_bytes(zip_path.read_bytes())
    args = ["--zip", str(zip_path), "--sha256", sha, "--expected-tests", "1", "--skip-install", "--external-manifest", str(manifest)]
    assert _cv.main(args + ["--log", str(tmp_path / "ok.log")]) == 0
    _cv.FAILURES.clear()
    _cv.LOG.clear()
    manifest.write_text(pc.build_manifest(dict(files, **{"docs/a.md": b"ALPHA"})))
    assert _cv.main(args + ["--log", str(tmp_path / "bad.log")]) != 0
    assert "hash mismatch: docs/a.md" in (tmp_path / "bad.log").read_text()
    _cv.FAILURES.clear()
    _cv.LOG.clear()


def test_personal_data_scan_is_linear_time_on_large_files():
    import time

    big = b"A" * (3 * 1024 * 1024)  # e.g. a base64 blob inside a single-file HTML report
    started = time.monotonic()
    assert pc.personal_data_hits("docs/big.html", big) == []
    assert time.monotonic() - started < 5
