# Feature: Backend GenAI Development Skill

**Date:** 2026-03-24
**Files Introduced:** 1
**New Dependencies:** 0

---

## Summary
Added a new project skill that prepares AI agents for Python backend service development with GenAI capabilities. The skill includes trigger heuristics, structured planning steps, architecture and quality standards, and starter code skeletons. It is designed to auto-apply for implementation requests that combine build-style verbs with backend/API/service context.

## Files Introduced
- `.cursor/skills/backend-genai-development/SKILL.md` — Main skill definition with metadata, activation rules, implementation guidance, and reusable Python templates.

## Dependencies Added
None.

## Usage Example
```text
User prompt:
"Build me a Python backend API service for document summarization with Anthropic, deployed on AWS."

Expected behavior:
The development-skill activates, asks clarifying questions, proposes a structured implementation plan, injects coding/security/GenAI standards, and provides starter scaffolding templates.
```

## Notes
None.
