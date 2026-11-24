"""Root conftest: shared plugins and the ``tally`` fixture used as a teaching example for fixture lifecycles."""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Iterator, List

import pytest

pytest_plugins = ["tests.support.plugin", "tests.support.pw_plugin", "pytester"]


class Tally:
    """Tiny in-memory object used to teach fixture set-up and tear-down (independent synthetic example)."""

    def __init__(self) -> None:
        self.entries: List[str] = []
        self.closed = True

    def open(self) -> None:
        self.entries = ["opening balance"]
        self.closed = False

    def close(self) -> None:
        self.entries = []
        self.closed = True


@pytest.fixture
def tally() -> Iterator[Tally]:
    """A freshly opened Tally for every test; closed again afterwards, whatever the test did to it."""
    obj = Tally()
    obj.open()
    yield obj
    obj.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Iterator[None]:
    """On a failing browser test store a real screenshot under artifacts/failures/ and attach it to the HTML report.

    The hook never raises: a failure to take the screenshot must not hide the original test failure.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    target = getattr(item, "funcargs", {}).get("page") or getattr(item, "_kqa_driver", None)
    if target is None:
        return
    try:
        out_dir = Path(os.environ.get("KQA_ARTIFACTS", str(Path(str(item.config.rootpath)) / "artifacts"))) / "failures"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / (re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid) + ".png")
        if hasattr(target, "save_screenshot"):
            target.save_screenshot(str(path))
        else:
            target.screenshot(path=str(path))
        report.kqa_failure_screenshot = str(path)
        try:
            from pytest_html import extras

            report.extras = getattr(report, "extras", []) + [extras.image(base64.b64encode(path.read_bytes()).decode())]
        except ImportError:
            pass
    except Exception:  # noqa: BLE001 - best effort by design
        pass


def pytest_collection_modifyitems(items: "list[pytest.Item]") -> None:
    """Record golden-scenario ids, markers and layer as JUnit <properties> so reports are derived from the run itself."""
    for item in items:
        golden = [str(m.args[0]) for m in item.iter_markers("golden") if m.args]
        marks = sorted({m.name for m in item.iter_markers() if m.name not in ("golden", "parametrize", "usefixtures")})
        layer = item.nodeid.split("/")[1] if item.nodeid.startswith("tests/") else ""
        item.user_properties.append(("golden", ",".join(golden)))
        item.user_properties.append(("markers", ",".join(marks)))
        item.user_properties.append(("layer", layer))
        # Allure grouping (Behaviors tab): layer -> golden scenario. Added after the JUnit properties above, so the
        # derived QA/traceability reports do not change.
        if layer:
            item.add_marker(pytest.mark.allure_label(layer, label_type="epic"))
        for gid in golden:
            item.add_marker(pytest.mark.allure_label(gid, label_type="feature"))
