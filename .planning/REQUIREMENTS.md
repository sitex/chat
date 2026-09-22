# Requirements

## Historically documented scope (not fresh product verification)

- **CORE-01**: The package exposes shared configuration, persona, memory, LLM, retrieval, rate-limit, and scaffold modules (`chatcore/`, `tests/`).
- **CORE-02**: Repository templates and single-instance tooling support consumer-bot operations (`chatcore/templates/`, `scripts/`).

## Pending Selection

- [ ] **SAFE-01**: Reconcile open issue #36 against commit `1ef43d0`; verify that untrusted CLI output cannot reach exceptions or fallback logs before closing or planning more work.
- [ ] **OWN-01**: Resolve issue #34's deployment-source ownership decision without assigning work owned by another repository to a `chat` phase.

## Out of Scope

- Reopening closed issues #30/#32/#35 as new implementation phases.
- Deploying or repinning consumer bots during documentation onboarding.

## Traceability

No active roadmap phases. `SAFE-01` and `OWN-01` remain pending milestone selection.

## Bounded source verification,2026-09-22

The checked direct-cliproxy criterion in PROJECT_GOAL.md is supported by current chatcore/llm.py and eight isolated existing tests in tests/test_llm.py. This covers configured HTTP fallback and rolling summary, not installed/live runtime or all consumer bots. Issues #36 and #34 remain OPEN; no milestone selected.
