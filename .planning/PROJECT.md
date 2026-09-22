# chat

## What This Is

An internal Python package and operational toolkit shared by Telegram persona bots (`README.md`, `pyproject.toml`, `chatcore/`).

## Core Value

Keep one reusable, observable bot core so fleet-wide conversation, memory, and LLM behavior does not diverge across consumers.

## Requirements

Existing capabilities are represented by the current package and tests. Pending selection: reconcile open issue #36's acceptance state and decide ownership in issue #34. Neither is assigned to a GSD phase.

## Constraints

- Python 3.10+; Telegram and configured LLM providers are external boundaries.
- Changes to the shared package may require consumer version updates and deployment decisions.
- Registry lifecycle remains paused; existing user changes remain untouched.

## Status

Paused with no selected milestone or phase. Legacy WARNING and duplicate-unit work is reported complete; current open issues remain pending evidence/selection.

## Evidence

- `GSD-BOOTSTRAP.md`, `README.md`, `PROJECT_GOAL.md`, `pyproject.toml`
- `.planning/codebase/` and preserved handoff files
