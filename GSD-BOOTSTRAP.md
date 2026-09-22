---
document: gsd-brownfield-bootstrap
project: chat
git_root: .
github_repository: sitex/chat
generated_utc: 2026-09-12T07:50:02Z
thoughts_status: available via /home/rocky/thoughts/repos/chat/shared
github_status: read-only open and cited closed issues collected
include_personal: false
---

## Review boundary

Historical onboarding snapshot2026-09-12, reviewed for documentary publication2026-09-22. Issues #36 and #34 independently remain OPEN; no Issue changed. Historical completion remains dated. PROJECT_GOAL direct-cliproxy criterion is supported by current source and eight isolated mocked checks on2026-09-22, not installed/live verification. No phase selected.

## Purpose

- Maintain `chatcore`, the internal Python package shared by Telegram persona bots for conversation memory, LLM routing, persona prompts, rate limiting, optional retrieval, and bot scaffolding (`README.md`, `pyproject.toml`, `chatcore/`).
- Provide reusable operational templates and single-instance checks for the bot fleet (`chatcore/templates/`, `scripts/check_single_instance.sh`).

## Implemented Capabilities

- Package modules implement configuration, hot-reload data, SQLite memory, persona assembly, retrieval, rate limiting, LLM routing, and Telegram handlers (`chatcore/__init__.py`, `chatcore/*.py`).
- Tests cover the major package modules and roundtable/TTS helpers (`tests/`).
- The legacy handoff's `auto -> ollama` warning work is reported complete and independently validated; closed issues I30 and I35 agree with T1 and commits `a42e9f5`/`c6a7be9`.
- The duplicate systemd-unit investigation is reported complete in T2 and closed issue I32; it led to the still-open ownership decision I34.

## Current Milestone

No GSD milestone or phase is selected. Registry lifecycle remains `paused`. Open work stays pending selection rather than becoming an invented phase.

## Open Requirements

- I36: ensure external CLI failures retain category/return code without copying untrusted stdout or stderr into exceptions or fallback logs. Commit `1ef43d0` reports related implementation, but the issue remains open, so acceptance/closure is unverified.
- I34: decide whether the live webhook deployment source remains in the archived-named repository or moves to a maintained owner. This is an ownership decision spanning another repository, not an automatic `chat` implementation phase.

## Accepted Decisions

- Explicit `LLM_BACKEND=ollama` is an operator choice; warning behavior applies to automatic fallback (T1, I30).
- Preserve the file-based single-instance invariant and keep the webhook deployment ownership question separate (T2, I32, I34).
- Completed legacy work remains historical evidence and is not reopened as a GSD phase (`.planning/.continue-here.md`, `.planning/HANDOFF.json`).

## Constraints

- Python 3.10+ and the dependency boundaries in `pyproject.toml` define the package runtime.
- `chatcore` is an internal shared dependency; interface or deployment changes can affect multiple consumer repositories (`README.md`, `PROJECT_GOAL.md`).
- Existing dirty files predate this reconciliation and were not modified; secrets and operational credentials are not carried into GSD documents.

## Unresolved Conflicts

- I36 is open although recent source history reports a related fix; the issue must be validated and reconciled before being called complete.
- I34 identifies an owner/status mismatch outside this repository's sole control.

## Source Thoughts

- T1: `/home/rocky/thoughts/repos/chat/shared/plans/2026-08-08-ISSUE-30-resolve-backend-warning.md`
- T2: `/home/rocky/thoughts/repos/chat/shared/handoffs/ISSUE-32/2026-08-07_23-57-37_ISSUE-32_webhook-server-duplicate-units.md`

## Source Issues

- I36: https://github.com/sitex/chat/issues/36 (open)
- I34: https://github.com/sitex/chat/issues/34 (open)
- I30: https://github.com/sitex/chat/issues/30 (closed)
- I35: https://github.com/sitex/chat/issues/35 (closed)
- I32: https://github.com/sitex/chat/issues/32 (closed)

## Source Limitations

- Shared Thoughts were read through the resolved projection and were not synchronized or modified.
- GitHub was queried read-only. No production service or consumer-bot deployment was checked.
- Historical completion is reported evidence, not fresh phase verification; `./scripts/verify` is absent.
