---
description: "Generate a feature doc for a development iteration. Use when: adding a new feature, completing an implementation task, or wrapping up a dev session and needing a record of what was built."
name: "Document Feature"
argument-hint: "Feature name or brief description (e.g. 'movie search UI' or 'database connection layer')"
agent: "agent"
---

Generate a feature documentation file for the development iteration described by the user. This doc will serve as a future reference for understanding what was built, why, and how to use it.

## Default Behavior

When a user asks to create, add, or implement a feature, generating this feature doc is the default follow-up action unless the user explicitly opts out.

## Steps

1. **Gather context** — Search the workspace for recently changed or newly introduced files relevant to the feature. Look at imports, entry points, tests, and any existing docs under `docs/features/` or `movie-search/docs/features/` to understand prior doc conventions.

2. **Determine file location** — Check whether the feature belongs to a sub-project (e.g. `movie-search/`) or the root project. Place the doc in the matching `docs/features/` folder:
   - Root-level feature → `docs/features/`
   - Sub-project feature → `<subproject>/docs/features/`

3. **Generate the doc** — Create a new Markdown file named `YYYY-MM-DD_<kebab-case-feature-name>.md` using today's date. Use the template below exactly.

4. **Populate each section** with factual, specific content drawn from the actual files — do not guess or fabricate file names, dependency versions, or behavior.

---

## Output Template

```markdown
# Feature: <Feature Name>

**Date:** YYYY-MM-DD
**Files Introduced:** <count of new files>
**New Dependencies:** <count of new packages>

---

## Summary
<2–4 sentence description of what this feature adds and its business value. Mention the primary mechanism (e.g. API, CLI, DB layer) and any notable design decisions.>

## Files Introduced
<Bullet list of every new file with a one-line description of its role.>
- `path/to/file.py` — <what it does>

## Files Modified
<Bullet list of existing files that were changed and why. Omit this section if no files were modified.>
- `path/to/file.py` — <what changed and why>

## Dependencies Added
<List new packages with pinned version range from requirements.txt. Write "None." if no new dependencies.>
- `package>=x.y.z` — <one-line purpose>

## Usage Example
<Runnable code block or CLI command that demonstrates the feature end-to-end. Prefer a minimal but complete example.>

\`\`\`bash
# or python, depending on context
<example here>
\`\`\`

## Notes
<Any caveats, known limitations, follow-up tasks, or design rationale worth preserving. Write "None." if there is nothing to add.>
```

---

## Rules

- Treat feature documentation generation as required by default for feature creation tasks, unless the user explicitly says not to generate docs.
- Follow the template and rules in this file exactly; do not improvise section names, ordering, or metadata fields.
- Use **today's date** for the `Date` field.
- Keep section headers exactly as shown — do not rename or reorder them.
- File counts in the metadata must match the actual bullet lists.
- Do not include the ` ``` ` fence around the template itself in the output file.
- If the user provides a feature name as an argument, use it as the `# Feature:` title (title-cased).
- Cross-reference any related existing doc files in the Notes section if relevant.
