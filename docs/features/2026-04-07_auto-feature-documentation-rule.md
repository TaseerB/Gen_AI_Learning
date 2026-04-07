# Feature: Auto Feature Documentation Rule

**Date:** 2026-04-07  
**Files Introduced:** 0  
**New Dependencies:** 0

---

## Summary

Extends the Copilot instructions with a standing rule (Step 5) that makes feature documentation generation the default behavior after any non-trivial implementation work. Previously, documentation had to be explicitly requested each session. Now, a feature doc is produced automatically in the same session as code delivery unless the user explicitly opts out.

## Files Introduced

None.

## Files Modified

- `.github/copilot-instructions.md` — Added **Step 5: Feature Documentation (Default)** after the existing Step 4 Verification block. The step defines the trigger conditions, canonical template reference, file placement rules, file naming convention, and exclusion criteria.

## Dependencies Added

None.

## Usage Example

With this rule in place, no action is needed. When any feature or non-trivial enhancement is implemented, a doc is written automatically:

```
# During an implementation session the AI now:
# 1. Writes code
# 2. Verifies via tests / syntax checks
# 3. Creates docs/features/YYYY-MM-DD_<feature-name>.md automatically
#
# To skip doc generation, say:
#   "implement X, skip docs"
```

## Notes

- The canonical format and section ordering are defined in `.github/prompts/document-feature.prompt.md`. Step 5 references that prompt rather than duplicating it so the two stay in sync.
- Placement rule: root-level work → `docs/features/`; sub-project work (e.g. `movie-search/`) → `<subproject>/docs/features/`.
- Skip condition: trivial one-liner fixes or changes with no observable feature-level impact do not generate a doc.
- This rule was added in the same session that introduced `docs/features/2026-04-07_hybrid-search-engine.md` and `docs/features/2026-04-07_search-reranker.md` as the first two automatically generated examples.
