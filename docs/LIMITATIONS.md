# Limitations (read before relying on any claim)

## Verified environments - and what is not

| Item | Status |
|---|---|
| macOS (Apple Silicon), Python **3.12** (isolated, hash-locked dependencies) | **verified**: complete suite, lint, type checks, all 26 seeded defects, scripted UAT, clean installation of the final archive |
| Playwright **Chromium** and **WebKit**, Selenium **Chrome** | **verified** (versions and counts in `QA_REPORT.md`) |
| Python 3.9 (macOS) | the suite was run once more as a regression check (tests only; the project's declared floor is now 3.11) |
| Playwright **Firefox** | **not run**: the Firefox build bundled with Playwright 1.60 does not finish starting on the development machine (macOS 27.2.1; its own graphics initialisation fails, with or without Playwright and with sandbox or graphics preferences changed). It is in the CI workflow and untested until a Linux runner executes it |
| Linux, Windows, Python 3.11 and 3.13, headed mode, other screen sizes | **not verified** |
| Hosted CI (GitHub Actions) | **never run**; the workflow was only validated against the workflow schema and its commands were run by hand |
| Safari | not tested; the Playwright "WebKit" engine is not Safari |

"Verified" means the commands were executed and the results are recorded in `QA_REPORT.md`, `MUTATION_REPORT.md` and `UAT_RESULT.md`. "Not verified" is not a claim that it fails.

## Scope of the target
* The sandbox is a deliberately simplified synthetic policy, not a real security design, not penetration-tested and not certified. It has no CSRF tokens, rate limiting, HTTPS, session expiry, password policy or audit log (explicit non-goals, `API_CONTRACT.md` section 3). Its low-cost password hashing is intentional for public test-only credentials.
* The request body is parsed as JSON whatever `Content-Type` is declared; that is documented and tested, not a protection.
* No inventory allocation, checkout, payment, shipping or order state machine; `customers`/`orders` are a read-only join fixture.
* The suite proves the behaviour described in `TEST_PLAN.md`; it does not prove the absence of other defects.

## Evidence limits
* Seeded mutants are controlled defects chosen by the author; passing the mutation check shows that those 26 defect classes (13 from v1.0, 10 targeted at the v1.0.1 fixes, 3 at the v1.0.2 evidence checks) are detected, not that all defects are.
* The evidence files are plain and unsigned. The consistency checks (`tools/evidence_check.py`) detect missing, incomplete or inconsistent evidence and accidental errors; they do not authenticate it and are not tamper-proof.
* Coverage excludes subprocess execution (inner pytest sessions of the isolation tests) and is a diagnostic, not an acceptance criterion.
* The historical 2023 live-service tests were never executed (policy), so their 2023 behaviour is unknown.
* Allure is rendered with the Allure 2 command line on a Java runtime that is not a project dependency (`REPORTING.md`); the first-run result of every test is the result (no retries).

## Review history
* An independent review of v1.0 by an AI assistant (Linux, Python 3.13.5, limited packages) re-checked checksums, the manifest, the archive inventory, test identities and ran 54 packaging, CI and database tests against an independently prepared synthetic fixture. It could not install Flask, Selenium or the pytest plugins, so it did not repeat the full suite, browsers, HTTP scenarios, UAT or mutations. Its findings (KQA-001 .. KQA-006 and two follow-ups) are fixed in v1.0.1 and v1.0.2 (`DEVELOPMENT_DEFECTS.md`). v1.0.2 has **not** been independently re-audited.
* The host name of the development machine appears in earlier, private releases of the evidence; the public candidate is built from scrubbed evidence only and is re-checked for it.

## Provenance limits
* Two periods are kept apart: the **original 2023 project**, written by the author during a QA automation course (the instructor gave general architectural guidance), and the **2026 modernization**, which is everything in this repository today and was carried out with AI assistance (Claude). Not every modernization change was implemented by hand; [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) states what was done and how. The original 2023 history is preserved privately and unchanged.
* No licence has been chosen; the repository name is not trademark-cleared (GitHub and PyPI were checked on 2026-11-18, no trademark search).

## Not claimed
Commercial employment experience, production deployment, mastery of any tool by the author before it has been used on real tasks, compliance of any kind, client experience, cross-browser or cross-platform support beyond the table above, or a hosted CI pass.
