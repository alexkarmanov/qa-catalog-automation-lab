# UAT result

Scripted walk-through `tools/uat.py` from a clean installation. Expected and observed values are in the Detail column.

| Step | Result | Detail |
|---|---|---|
| U01 interpreter + dependency consistency | PASS | python 3.12.16, `pip check` exit 0 (expected 0) |
| U02 test collection | PASS | collected 520 (expected 520), exit 0 (expected 0) |
| U03 sandbox starts on loopback, random port | PASS | startup line: CAPS sandbox listening on http://127.0.0.1:49826 (Ctrl+C to stop) |
| U04 login/read/draft-hidden/logout over HTTP | PASS | statuses health=200 bad-login=401 login=200 list=200 draft=404 logout=204 replay=401 (expected 200,401,200,200,404,204,401); skus=['SYN-1001', 'SYN-1002'] |
| U05 real Chromium shows 2 published rows (screenshot kept) | PASS | exit 0 (expected 0), output 'ROWS 2', screenshot 31803 bytes |
| U06 sandbox stops cleanly and the port is released | PASS | exit 0 (expected 0), port closed: True |
| U07 full suite passes | PASS | exit 0 (expected 0), 520 tests in JUnit (expected 520), failed/error/skipped: 0 (expected 0) |
| U08 ruff and mypy are clean | PASS | ruff exit 0, mypy exit 0 (expected 0, 0) |
| U09 seeded defect M03 is caught by an assertion | PASS | runner exit 0 (expected 0), verdict CAUGHT_BY_ASSERTION (expected CAUGHT_BY_ASSERTION) |
| U10 CI aggregator reports a failing child as failure | PASS | exit 1 (expected 1), names failing step: True |
| U11 README links resolve | PASS | 28 links checked, missing: none (expected none) |

Overall: **PASS**
