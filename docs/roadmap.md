# ROADMAP

- **Version:** 0.1.0
- **Updated:** 2026-04-10
- **Owner:** Julio Cordero

## Planner Rules

1. One Epic `Active` at a time (except EPICs 002-005 = parallel)
2. Verify all Success Criteria met in main before marking `Complete`
3. Don't start Epics with incomplete prereqs

## Epic Ledger

### EPIC-001: Foundation & CLAUDE.md

- **Status:** Complete
- **Deps:** None
- **Goal:** Project conventions for independent agent work
- **Boundary:** CLAUDE.md, pyproject.toml, dir structure, fixtures, conftest.py
- **Done when:** `uv run pytest` runs, CLAUDE.md has conventions + gws ref, `test_data/` has valid scrubbed output

### EPIC-002: gws CLI Wrapper

- **Status:** Complete
- **Deps:** EPIC-001
- **Goal:** Encapsulate all gws interaction, no other module touches subprocess
- **Boundary:** `scripts/_gws.py`, `tests/test_gws.py` (TDD)
- **Done when:** tests pass, retry logic tested (mock 429→success), errors map to exit codes 1/2/3

### EPIC-003: MIME Parser & Classifier

- **Status:** Complete
- **Deps:** EPIC-001
- **Goal:** Identify real attachments vs inline images in any MIME structure
- **Boundary:** `scripts/_mime.py`, `tests/test_mime.py` (TDD)
- **Done when:** tests pass, inline classification matches PRD heuristic, glob filter works (`*.pdf`, `*.{pdf,xlsx}`, `COA*`)

### EPIC-004: File Operations

- **Status:** Complete
- **Deps:** EPIC-001
- **Goal:** Safely decode, name, write attachment files
- **Boundary:** `scripts/_fileops.py`, `tests/test_fileops.py` (TDD)
- **Done when:** tests pass, atomic write no partials on failure, collision tested 10+ conflicts

### EPIC-005: Manifest Builder

- **Status:** Complete
- **Deps:** EPIC-001
- **Goal:** Machine-readable manifest matching PRD schema
- **Boundary:** `scripts/_manifest.py`, `tests/test_manifest.py` (TDD)
- **Done when:** tests pass, JSON matches PRD schema, subject/from/date extraction works

### EPIC-006: Orchestrator & CLI

- **Status:** Complete
- **Deps:** EPIC-002, 003, 004, 005
- **Goal:** Wire everything into single-command interface
- **Boundary:** `scripts/download_attachments.py`, `tests/test_orchestrator.py`, `tests/test_integration.py` (TDD)
- **Done when:** unit tests pass, integration test passes with real gws, `--dry-run` works, exit codes match PRD

### EPIC-007: Skill Prompt

- **Status:** Complete
- **Deps:** EPIC-006
- **Goal:** Minimal skill prompt < 400 tokens for agent context
- **Boundary:** `skill.md`
- **Done when:** < 400 tokens, YAML frontmatter with name + description, flags + exit codes documented, agent can invoke from prompt alone

## Parallelism

```text
EPIC-001 (Foundation)
    │
    ├── EPIC-002 (gws)      ─┐
    ├── EPIC-003 (MIME)       ├── parallel (disjoint files)
    ├── EPIC-004 (fileops)    │
    └── EPIC-005 (manifest)  ─┘
              │
        EPIC-006 (Orchestrator)
              │
        EPIC-007 (Skill prompt)
```
