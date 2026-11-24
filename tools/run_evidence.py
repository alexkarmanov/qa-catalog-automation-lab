"""Run the suite in the configurations that the QA report cites and record exactly what happened.

Steps (each recorded with command, exit code, duration and JUnit counts):
 collect-only | first_run (JUnit + HTML + Allure) | reverse_order | shuffled_order | separate_processes | parallel_xdist | coverage
plus tool/browser versions and a check that no chromedriver process was left behind.

Usage: python tools/run_evidence.py --out artifacts/evidence_run
Nothing is retried. Exit status is non-zero if any mandatory step fails.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_check import MANDATORY_STEPS, OPTIONAL_STEPS, scrub_text  # noqa: E402

PACKAGES = ["pytest", "pytest-html", "pytest-playwright", "playwright", "selenium", "requests", "Flask", "Werkzeug",
            "allure-pytest", "pytest-xdist", "pytest-cov", "pytest-timeout", "ruff", "mypy", "coverage"]
LAYERS = ["tests/framework", "tests/database", "tests/api", "tests/ui_selenium", "tests/ui_playwright", "tests/e2e"]


def junit_counts(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"missing": 1}
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return {"malformed": 1}
    counts = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for case in root.iter("testcase"):
        counts["tests"] += 1
        tags = {child.tag for child in case}
        if "failure" in tags:
            counts["failed"] += 1
        elif "error" in tags:
            counts["errors"] += 1
        elif "skipped" in tags:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    return counts


def run(cmd: List[str], env_extra: Optional[Dict[str, str]] = None, cwd: Path = ROOT, timeout: int = 1800) -> Dict:
    env = dict(os.environ)
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".pw-browsers"))
    env.update(env_extra or {})
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
    return {
        "command": " ".join(os.path.basename(c) if c == sys.executable else c for c in cmd),
        "exit_code": proc.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "stdout_tail": scrub_text(proc.stdout[-1500:], ROOT),  # no machine/user paths in curated evidence
        "stderr_tail": scrub_text(proc.stderr[-600:], ROOT),
    }


def versions() -> Dict:
    py = sys.executable
    out: Dict = {"python": sys.version.split()[0], "ssl": __import__("ssl").OPENSSL_VERSION, "platform": platform.platform(),
                 "machine": platform.machine(), "packages": {}}
    from importlib import metadata  # works in environments without pip (for example one created by uv)

    for name in PACKAGES:
        try:
            out["packages"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(chrome):
        out["chrome_for_selenium"] = subprocess.run([chrome, "--version"], capture_output=True, text=True).stdout.strip()
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".pw-browsers"))
    for engine in ("chromium", "firefox", "webkit"):  # real launches: the version is what the browser reports, not what was requested
        probe = (
            "from playwright.sync_api import sync_playwright\n"
            "with sync_playwright() as p:\n"
            "    b=p.%s.launch(); v=b.version; b.close()\n"
            "print(v)\n" % engine
        )
        res = subprocess.run([py, "-I", "-c", probe], capture_output=True, text=True, env=env, cwd=str(ROOT))
        out["playwright_" + engine] = res.stdout.strip() or ("unavailable: " + res.stderr.strip()[-200:])
    probe2 = (
        "from modules.ui.page_objects.base_page import make_chrome_driver\n"
        "d=make_chrome_driver(); c=d.capabilities; print(c.get('browserVersion'), '|', c.get('chrome',{}).get('chromedriverVersion','').split(' ')[0]); d.quit()\n"
    )
    res = subprocess.run([py, "-c", probe2], capture_output=True, text=True, cwd=str(ROOT), env=dict(os.environ, PYTHONPATH=str(ROOT)))
    out["selenium_chrome_and_driver"] = res.stdout.strip() or ("unavailable: " + res.stderr.strip()[-200:])
    return out


def driver_pids() -> List[str]:
    res = subprocess.run(["pgrep", "-f", "chromedriver"], capture_output=True, text=True)
    return sorted(res.stdout.split())


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "artifacts" / "evidence_run"))
    parser.add_argument("--skip", default="", help="comma list of steps to skip (e.g. coverage)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    skip = set(filter(None, args.skip.split(",")))
    py = sys.executable
    base = [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore"]
    summary: Dict = {"steps": {}, "date": time.strftime("%Y-%m-%d"), "mandatory_failures": [],
                     "mandatory_steps": list(MANDATORY_STEPS), "optional_steps": list(OPTIONAL_STEPS)}
    pids_before = driver_pids()
    summary["versions"] = versions()
    (out / "versions.json").write_text(json.dumps(summary["versions"], indent=2), encoding="utf-8")

    def step(name: str, cmd: List[str], junit: Optional[Path] = None, env: Optional[Dict[str, str]] = None, mandatory: bool = True,
             extra: Optional[Dict[str, str]] = None):
        if name in skip:
            return
        print("running", name, flush=True)
        res = run(cmd, env)
        if junit is not None:
            res["junit"] = junit_counts(junit)
            ok = res["exit_code"] == 0 and res["junit"].get("failed", 0) == 0 and res["junit"].get("errors", 0) == 0 \
                and res["junit"].get("tests", 0) > 0
        else:
            ok = res["exit_code"] == 0
        res["ok"] = ok
        res["mandatory"] = mandatory
        res.update(extra or {})
        summary["steps"][name] = res
        print("  ->", "OK" if ok else "FAILED", res.get("junit", ""), res["seconds"], "s", flush=True)
        if mandatory and not ok:
            summary["mandatory_failures"].append(name)

    artifacts = out / "artifacts"
    collect_cmd = [py, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-W", "ignore"]
    step("collect_only", collect_cmd, None)
    if "collect_only" in summary["steps"]:
        (out / "collect_only.txt").write_text(subprocess.run(collect_cmd, cwd=str(ROOT), capture_output=True, text=True,
                                                             env=dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".pw-browsers"))).stdout,
                                              encoding="utf-8")
    j = out / "junit_first_run.xml"
    step("first_run", base + [f"--junitxml={j}", f"--html={out / 'report.html'}", "--self-contained-html",
                              f"--alluredir={out / 'allure-results'}"], j, {"KQA_ARTIFACTS": str(artifacts)})
    j2 = out / "junit_reverse.xml"
    step("reverse_order", base + ["-p", "tools.order_plugin", f"--junitxml={j2}"], j2, {"KQA_ORDER": "reverse", "KQA_ARTIFACTS": str(artifacts / "reverse")})
    j3 = out / "junit_shuffled.xml"
    step("shuffled_order", base + ["-p", "tools.order_plugin", f"--junitxml={j3}"], j3, {"KQA_ORDER": "shuffle:20261118", "KQA_ARTIFACTS": str(artifacts / "shuffled")})
    # separate processes: one pytest process per layer
    total = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    sep_ok = True
    sep_detail = {}
    if "separate_processes" not in skip:
        print("running separate_processes", flush=True)
        for layer in LAYERS:
            jl = out / ("junit_layer_%s.xml" % layer.split("/")[-1])
            res = run(base + [layer, f"--junitxml={jl}"], {"KQA_ARTIFACTS": str(artifacts / "layers")})
            counts = junit_counts(jl)
            sep_detail[layer] = {"exit_code": res["exit_code"], "junit": counts, "seconds": res["seconds"]}
            sep_ok = sep_ok and res["exit_code"] == 0 and counts.get("failed", 0) == 0 and counts.get("errors", 0) == 0
            for key in total:
                total[key] += counts.get(key, 0)
        summary["steps"]["separate_processes"] = {"ok": sep_ok, "mandatory": True, "layers": sep_detail, "junit": total}
        print("  ->", "OK" if sep_ok else "FAILED", total, flush=True)
        if not sep_ok:
            summary["mandatory_failures"].append("separate_processes")
    # the same business scenarios (tests/ui_playwright + tests/e2e) on each real Playwright engine; no extra test code
    for engine in ("chromium", "webkit", "firefox"):
        jb = out / ("junit_browser_%s.xml" % engine)
        if engine == "firefox" and str(summary["versions"].get("playwright_firefox", "")).startswith("unavailable"):
            print("skipping browser_firefox: the engine did not launch on this machine (recorded in versions)", flush=True)
            continue
        step("browser_" + engine, base + ["tests/ui_playwright", "tests/e2e", "--browser", engine, f"--junitxml={jb}"], jb,
             {"KQA_ARTIFACTS": str(artifacts / ("browser_" + engine))}, mandatory=engine != "firefox", extra={"browser": engine})
    j4 = out / "junit_xdist.xml"
    step("parallel_xdist", base + ["-n", "4", f"--junitxml={j4}"], j4, {"KQA_ARTIFACTS": str(artifacts / "xdist")}, mandatory=False)
    cov = out / "coverage.json"
    j5 = out / "junit_coverage.xml"
    step("coverage", base + ["--cov", "--cov-branch", f"--cov-report=json:{cov}", "--cov-report=term", f"--junitxml={j5}"], j5,
         {"KQA_ARTIFACTS": str(artifacts / "coverage")}, mandatory=False)
    pids_after = driver_pids()
    summary["leftover_chromedriver_processes"] = sorted(set(pids_after) - set(pids_before))
    if summary["leftover_chromedriver_processes"]:
        summary["mandatory_failures"].append("leftover_chromedriver_processes")
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("MANDATORY FAILURES:", summary["mandatory_failures"] or "none", flush=True)
    return 1 if summary["mandatory_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
