"""Scripted user-acceptance walk-through for someone who starts from a clean installation.

Run it with the virtualenv's Python from the project root. It performs 11 numbered steps, records the exact
expected and observed exit status/values of each, and exits 1 if any step failed. Standard library only (the
browser step shells out to the project's own Playwright).

Usage: python tools/uat.py --expected-tests N --out <dir> [--result-md <file>]
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS: List[Tuple[str, str, str]] = []


def record(step: str, ok: bool, detail: str) -> bool:
    RESULTS.append((step, "PASS" if ok else "FAIL", detail))
    print("%s %s - %s" % (step, "PASS" if ok else "FAIL", detail), flush=True)
    return ok


def sh(cmd: List[str], timeout: int = 1800, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".pw-browsers"))
    full_env.update(env or {})
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=full_env)


def http_call(host: str, port: int, method: str, path: str, body: Optional[dict] = None, cookie: str = "") -> Tuple[int, dict, str]:
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if cookie:
        headers["Cookie"] = cookie
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    set_cookie = resp.getheader("Set-Cookie") or ""
    conn.close()
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    return resp.status, payload, set_cookie


def port_closed(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) != 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-tests", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--result-md", default="")
    args = parser.parse_args(argv)
    py = sys.executable
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="kqa_uat_"))
    proc: Optional[subprocess.Popen] = None
    try:
        # U01 interpreter and dependency consistency
        res = sh([py, "-m", "pip", "check"])
        record("U01 interpreter + dependency consistency", res.returncode == 0 and sys.version_info >= (3, 9),
               "python %s, `pip check` exit %d (expected 0)" % (sys.version.split()[0], res.returncode))

        # U02 collection count
        res = sh([py, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-W", "ignore"])
        match = re.search(r"(\d+) tests? collected", res.stdout)
        collected = int(match.group(1)) if match else -1
        record("U02 test collection", res.returncode == 0 and collected == args.expected_tests,
               "collected %d (expected %d), exit %d (expected 0)" % (collected, args.expected_tests, res.returncode))

        # U03 start the sandbox like a user would
        db = work / "uat.db"
        proc = subprocess.Popen([py, "-m", "sandbox", "--db", str(db)], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        url_line = ""
        started = time.monotonic()
        assert proc.stdout is not None
        while time.monotonic() - started < 30:
            url_line = proc.stdout.readline()
            if "listening on" in url_line or proc.poll() is not None:
                break
        m = re.search(r"http://(127\.0\.0\.1):(\d+)", url_line)
        record("U03 sandbox starts on loopback, random port", bool(m), "startup line: %s" % (url_line.strip() or "<none>"))
        if not m:
            raise RuntimeError("sandbox did not start")
        host, port = m.group(1), int(m.group(2))

        # U04 API behaviour a user can check by hand
        status, body, _ = http_call(host, port, "GET", "/api/v1/health")
        ok = status == 200 and body == {"status": "ok"}
        status2, _, cookie_bad = http_call(host, port, "POST", "/api/v1/session", {"username": "viewer1", "password": "wrong"})
        ok = ok and status2 == 401 and cookie_bad == ""
        status3, _, cookie = http_call(host, port, "POST", "/api/v1/session", {"username": "viewer1", "password": "TESTONLY-viewer1"})
        sid = cookie.split(";")[0]
        status4, items, _ = http_call(host, port, "GET", "/api/v1/items", cookie=sid)
        status5, _, _ = http_call(host, port, "GET", "/api/v1/items/SYN-2001", cookie=sid)
        status6, _, _ = http_call(host, port, "DELETE", "/api/v1/session", cookie=sid)
        status7, _, _ = http_call(host, port, "GET", "/api/v1/items", cookie=sid)
        skus = [i["sku"] for i in items.get("items", [])]
        ok = ok and (status3, status4, status5, status6, status7) == (200, 200, 404, 204, 401) and skus == ["SYN-1001", "SYN-1002"]
        record("U04 login/read/draft-hidden/logout over HTTP", ok,
               "statuses health=%d bad-login=%d login=%d list=%d draft=%d logout=%d replay=%d (expected 200,401,200,200,404,204,401); skus=%s"
               % (status, status2, status3, status4, status5, status6, status7, skus))

        # U05 real browser screenshot of the catalog
        shot = out / "uat_catalog_viewer.png"
        script = (
            "import sys\n"
            "from playwright.sync_api import sync_playwright\n"
            "base, shot = sys.argv[1], sys.argv[2]\n"
            "with sync_playwright() as p:\n"
            "    b = p.chromium.launch(); pg = b.new_page()\n"
            "    pg.goto(base + '/login'); pg.fill('#username', 'viewer1'); pg.fill('#password', 'TESTONLY-viewer1'); pg.click('#login-submit')\n"
            "    pg.wait_for_url(base + '/catalog'); pg.wait_for_selector('[data-testid=catalog-table]')\n"
            "    rows = pg.locator('[data-testid=catalog-table] tbody tr').count(); pg.screenshot(path=shot); b.close()\n"
            "print('ROWS', rows)\n"
        )
        res = sh([py, "-I", "-c", script, "http://%s:%d" % (host, port), str(shot)])
        record("U05 real Chromium shows 2 published rows (screenshot kept)", res.returncode == 0 and "ROWS 2" in res.stdout
               and shot.exists() and shot.stat().st_size > 5000,
               "exit %d (expected 0), output %r, screenshot %s bytes" % (res.returncode, res.stdout.strip(), shot.stat().st_size if shot.exists() else 0))

        # U06 stop the server and prove the port is free
        proc.send_signal(signal.SIGINT)
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = -9
        record("U06 sandbox stops cleanly and the port is released", code == 0 and port_closed(host, port),
               "exit %d (expected 0), port closed: %s" % (code, port_closed(host, port)))
        proc = None

        # U07 the whole suite
        junit = out / "uat_full_run.xml"
        res = sh([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore", "--junitxml", str(junit)],
                 env={"KQA_ARTIFACTS": str(out / "artifacts")})
        counts = {"tests": 0, "bad": 0}
        if junit.exists():
            for case in ET.parse(str(junit)).getroot().iter("testcase"):
                counts["tests"] += 1
                counts["bad"] += any(c.tag in ("failure", "error", "skipped") for c in case)
        record("U07 full suite passes", res.returncode == 0 and counts["tests"] == args.expected_tests and counts["bad"] == 0,
               "exit %d (expected 0), %d tests in JUnit (expected %d), failed/error/skipped: %d (expected 0)"
               % (res.returncode, counts["tests"], args.expected_tests, counts["bad"]))

        # U08 lint and static types
        r1 = sh([py, "-m", "ruff", "check", "."])
        r2 = sh([py, "-m", "mypy"])
        record("U08 ruff and mypy are clean", r1.returncode == 0 and r2.returncode == 0,
               "ruff exit %d, mypy exit %d (expected 0, 0)" % (r1.returncode, r2.returncode))

        # U09 one seeded defect is caught
        mdir = out / "mutation_uat"
        res = sh([py, "tools/mutation_runner.py", "--only", "M03", "--out", str(mdir)], timeout=900)
        verdict = ""
        try:
            verdict = json.loads((mdir / "mutation_results.json").read_text())["mutants"][0]["verdict"]
        except (OSError, ValueError, KeyError, IndexError):
            pass
        record("U09 seeded defect M03 is caught by an assertion", res.returncode == 0 and verdict == "CAUGHT_BY_ASSERTION",
               "runner exit %d (expected 0), verdict %s (expected CAUGHT_BY_ASSERTION)" % (res.returncode, verdict or "<none>"))

        # U10 CI aggregator fails when a child fails (failure path)
        res = sh([py, "-c", "import sys; sys.path.insert(0, '.'); from tools.ci_check import run_checks; "
                  "sys.exit(run_checks([('ok', [sys.executable, '-c', '0']), ('bad', [sys.executable, '-c', 'raise SystemExit(5)'])]))"])
        record("U10 CI aggregator reports a failing child as failure", res.returncode == 1 and "FAILED STEPS: bad (exit 5)" in res.stdout,
               "exit %d (expected 1), names failing step: %s" % (res.returncode, "FAILED STEPS: bad (exit 5)" in res.stdout))

        # U11 documentation entry points exist
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        refs = sorted(set(re.findall(r"\]\(((?:docs/|[A-Z]+\.md)[^)#]*)", readme)))
        missing = [r for r in refs if not (ROOT / r).exists()]
        record("U11 README links resolve", bool(refs) and not missing, "%d links checked, missing: %s (expected none)" % (len(refs), missing or "none"))
    except Exception as exc:  # noqa: BLE001 - recorded as a failed UAT, never swallowed
        record("UAT ABORTED", False, "%s: %s" % (type(exc).__name__, exc))
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        for item in work.glob("*"):
            item.unlink()
        work.rmdir()

    failed = [r for r in RESULTS if r[1] != "PASS"]
    if args.result_md:
        lines = ["# UAT result", "", "Scripted walk-through `tools/uat.py` from a clean installation. Expected and observed values are in the Detail column.", "",
                 "| Step | Result | Detail |", "|---|---|---|"]
        lines += ["| %s | %s | %s |" % (s, r, d.replace("|", "/")) for s, r, d in RESULTS]
        lines += ["", "Overall: **%s**" % ("PASS" if not failed else "FAIL (%d step(s))" % len(failed))]
        Path(args.result_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("UAT OVERALL:", "PASS" if not failed else "FAIL", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
