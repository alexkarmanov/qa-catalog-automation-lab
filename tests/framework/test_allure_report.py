"""The Allure helper scrubs machine identifiers before rendering and fails closed (rendering itself needs the Allure CLI + Java,
which are not project dependencies; the real render is part of the release evidence, not of this suite)."""
from __future__ import annotations

import json
import socket

import pytest

from tools import allure_report as ar
from tools import evidence_check as ec

pytestmark = [pytest.mark.framework, pytest.mark.negative]


def _result(host: str, trace: str) -> str:
    return json.dumps({"name": "t", "status": "failed", "labels": [{"name": "host", "value": host}, {"name": "thread", "value": "1-MainThread"},
                                                                   {"name": "tag", "value": "api"}],
                       "statusDetails": {"trace": trace}})


def test_host_and_thread_labels_and_private_paths_are_scrubbed(tmp_path):
    src, dst = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    trace = "File %s/tests/x.py line 3 in " % ar.ROOT
    (src / "a-result.json").write_text(_result(socket.gethostname(), trace), encoding="utf-8")
    (src / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert ar.scrub_results(src, dst) == 1
    data = json.loads((dst / "a-result.json").read_text(encoding="utf-8"))
    labels = {label["name"]: label["value"] for label in data["labels"]}
    assert labels["host"] == "redacted" and labels["thread"] == "redacted" and labels["tag"] == "api"
    assert str(ar.ROOT) not in json.dumps(data) and "<PROJECT>" in data["statusDetails"]["trace"]
    assert (dst / "shot.png").read_bytes() == b"\x89PNG\r\n\x1a\n"
    assert ec.find_private((dst / "a-result.json").read_text(encoding="utf-8"), ar.ROOT) == []


def test_missing_results_missing_cli_and_existing_output_are_non_zero(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    assert ar.main(["--results", str(results), "--out", str(tmp_path / "out")]) == 2  # nothing to render
    (results / "x-result.json").write_text(_result("h", "t"), encoding="utf-8")
    monkeypatch.delenv("ALLURE_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ar.main(["--results", str(results), "--out", str(tmp_path / "out")]) == 3  # no Allure CLI available
    existing = tmp_path / "keep"
    existing.mkdir()
    (existing / "f.txt").write_text("precious")
    assert ar.main(["--results", str(results), "--out", str(existing)]) == 2
    assert (existing / "f.txt").read_text() == "precious"
    assert not (tmp_path / "out").exists()


def test_environment_widget_files_are_written(tmp_path):
    ar.write_environment(tmp_path, {"python": "3.12.0", "packages": {"pytest": "8.4.2"}})
    text = (tmp_path / "environment.properties").read_text(encoding="utf-8")
    assert "python=3.12.0" in text and "package.pytest=8.4.2" in text
    assert json.loads((tmp_path / "categories.json").read_text(encoding="utf-8"))
