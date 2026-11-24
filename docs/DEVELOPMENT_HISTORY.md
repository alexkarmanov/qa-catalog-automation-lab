# Development history

This page records how the project came to be: who wrote what, when, and how AI tooling was involved. It is deliberately short and factual. It describes
*how the work was done*; what the project can be trusted to show is established by the recorded test runs, mutation results and reports, not by this page.

## Timeline

| When | What happened |
|---|---|
| January - February 2023 | The author wrote the original project while taking a QA automation course: an API client, a SQLite helper, a Selenium page object and 22 pytest tests, committed lesson by lesson (16 commits). |
| November 2026 | The author modernized it into the current suite (releases 1.0, 1.0.1 and 1.0.2), working with an AI assistant (Claude, used through Claude Code). |

## The 2023 original

The original project was independently coded by the author during the course. The course instructor gave general architectural guidance (a layered structure
with an API client, a database layer, page objects and fixtures) but not line-by-line implementation instructions. That guidance is gratefully acknowledged;
the layered structure of this repository still follows it.

The original repository stays unchanged on the author's account. It is not part of this repository's history and none of its files or lines is carried over
(a line-by-line comparison against the 2023 files found no surviving distinctive line).

## The 2026 modernization

The modernization kept the original ideas (API client, database layer, page objects, fixtures, markers, SQL checks) and rebuilt them around a local synthetic
target so that results no longer depend on the internet. In order:

1. The 2023 project was reviewed and its weaknesses were written down (live-internet dependence, shared mutable database, hard-coded paths, string-built SQL,
   assertions that cannot fail).
2. A test plan, an API/UI contract and literal expected values were written before any test code.
3. A small Flask sandbox, a database adapter, an HTTP client, Selenium and Playwright page objects and six test layers were built.
4. Evidence tooling was added: first-run reports, reversed and shuffled order runs, seeded-defect (mutation) checks, HTML/Allure reports, screenshots and traces,
   fail-closed consistency checks, a CI workflow.
5. An independent review of release 1.0 produced eight findings (KQA-001 .. KQA-008); each was reproduced, fixed and given a regression test
   ([DEVELOPMENT_DEFECTS.md](DEVELOPMENT_DEFECTS.md)).

## AI involvement

* **Tool.** Claude (Anthropic), used through Claude Code, under the author's direction. The author set the goals, scope and constraints and reviewed the results.
* **What the assistant did.** Most of the 2026 implementation: the sandbox, adapters, page objects, tests, tooling and documents were drafted and written by the
  assistant, then run, checked and revised in the same sessions.
* **What this does not mean.** It would be wrong to say the author typed every modernization change by hand, and this project does not claim that. It is also
  not a generated artefact nobody checked: every number in the reports comes from commands that were actually executed, and the code is covered by the
  mutation check described in [MUTATION_REPORT.md](MUTATION_REPORT.md).
* **Independent review.** The release-1.0 review that led to KQA-001 .. KQA-008 was carried out by a different AI assistant working from the delivered archive;
  its results are summarized in [LIMITATIONS.md](LIMITATIONS.md). Release 1.0.2 has not been independently re-audited.
* **Skills.** Which individual skills the author can demonstrate without the assistant is assessed separately, with an unaided exercise set kept in the author's
  own notes. Nothing in this repository asserts such a skill before that assessment.

## Preservation

The original 2023 history and every earlier release are preserved. This public snapshot is built from the current files only (see
[LIMITATIONS.md](LIMITATIONS.md) for what is and is not verified).
