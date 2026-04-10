# download-gmail-attachments

CLI: download Gmail attachments by message ID via `gws` CLI. MIME parse, base64 decode, inline filter, manifest JSON.

## Setup

- **Python 3.13+**, stdlib only, zero pip deps
- **`uv`** for project mgmt
- **`gws` CLI** (v0.22.5+) — installed + authenticated

```bash
uv sync --group dev              # dev deps
uv run pytest                    # all tests
uv run pytest -m "not integration"  # unit only
uv run pytest -m integration     # needs gws auth
uv run python scripts/download_attachments.py <message-id> --to <output-dir>
```

## Structure

```
scripts/
├── download_attachments.py  # orchestrator + CLI entry
├── _gws.py                  # gws wrapper (subprocess, retries, stderr filter)
├── _mime.py                 # MIME walk, classify, inline detect
├── _fileops.py              # base64 decode, sanitize, collision, atomic write
└── _manifest.py             # manifest dataclass + JSON

tests/
├── conftest.py              # shared fixtures
├── test_gws.py              # mocked subprocess
├── test_mime.py             # pure functions
├── test_fileops.py          # tmp_path
├── test_manifest.py         # manifest gen
├── test_orchestrator.py     # mocked _gws
└── test_integration.py      # real gws (@pytest.mark.integration)

test_data/
├── sample_message_metadata.json
└── sample_attachment.json
```

## Conventions

- **TDD**: red-green-refactor. Failing test first.
- Type hints on all signatures
- Dataclasses for structured data (not dicts)
- `_gws.py` = **only** subprocess caller. All others pure.
- stdout sacred: only `--json-summary` to stdout, rest stderr
- Exit: 0=ok, 1=auth fail, 2=not found, 3=API err, 4=no attachments, 5=disk err

## gws CLI Reference

```bash
gws gmail users messages get --params '{"userId": "me", "id": "<MESSAGE_ID>", "format": "full"}'
gws gmail users messages attachments get --params '{"userId": "me", "messageId": "<MESSAGE_ID>", "id": "<ATTACHMENT_ID>"}'
```

**gws quirks (encapsulated in `_gws.py`):**

- stderr has `"Using keyring backend: keyring"` — filter
- `data` = URL-safe base64: `-`→`+`, `_`→`/`, pad `=`
- `size` = decoded byte count (verify against)
- MIME parts nest deep — must recurse

## Docs

- `docs/PRD.md` — manifest schema + behavior source of truth
- `docs/roadmap.md` — epic status
- `ERRORS.md` — non-obvious errors + solutions
- `current-plan.md` — active epic tracker
- `MEMORY.md` — cross-session memory index

### Agent Rules

1. Read this file + `docs/roadmap.md` before work
2. Log non-obvious errors to `ERRORS.md`: `## Error: <desc>` + cause + fix
3. Update `current-plan.md` on epic start/finish: `Epic: EPIC-NNN | Status: Active/Complete | Agent: <id>`
4. Only modify files in your epic's Technical Boundary

## Agent Coordination

Disjoint file sets per epic:

- EPIC-002: `_gws.py`, `test_gws.py`
- EPIC-003: `_mime.py`, `test_mime.py`
- EPIC-004: `_fileops.py`, `test_fileops.py`
- EPIC-005: `_manifest.py`, `test_manifest.py`

Shared files (`conftest.py`, `test_data/`) from EPIC-001 — don't modify in parallel epics.
