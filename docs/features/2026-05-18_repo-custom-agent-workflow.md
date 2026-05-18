# Feature: Repo Custom Agent Workflow

**Date:** 2026-05-18
**Files Introduced:** 3
**New Dependencies:** 0

---

## Summary

Added three repository-scoped custom Copilot agents that split delivery work into research, implementation, and validation roles. The Researching Agent is designed to reduce hallucination risk by preparing evidence-backed briefs, the Developer Agent is the primary implementation entry point, and the Testing Agent verifies completed work after changes are made. Each agent has a distinct model preference and a minimal tool set so the workflow stays disciplined rather than collapsing into a single general-purpose assistant.

## Files Introduced

- `.github/agents/developer.agent.md` — Primary implementation agent that coordinates research before coding and testing after changes.
- `.github/agents/researching.agent.md` — Read-only analysis agent that produces repo-grounded implementation briefs.
- `.github/agents/testing.agent.md` — Validation agent that runs focused checks and reports failures with evidence.

## Dependencies Added

None.

## Usage Example

```text
In Copilot Chat, select "Developer Agent" for a feature request such as:

"Add a new movie recommendation filter to the search flow."

Expected workflow:
1. Developer Agent invokes Researching Agent to inspect the relevant files and constraints.
2. Developer Agent implements the approved solution in the repository.
3. Developer Agent invokes Testing Agent to run the smallest reliable validation checks before finalizing.
```

## Notes

- This feature is repo-scoped because the custom agents live under `.github/agents/` and are intended to travel with the project.
- The Developer Agent is the best default entry point because it explicitly orchestrates the other two roles.
- Related process rule: `docs/features/2026-04-07_auto-feature-documentation-rule.md` documents why this feature doc is created automatically after a non-trivial implementation change.