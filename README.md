# download-gmail-attachments

![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue?logo=python&logoColor=white)
![stdlib only](https://img.shields.io/badge/dependencies-zero-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![gws CLI](https://img.shields.io/badge/gws-v0.22.5%2B-orange)
![Tests](https://img.shields.io/badge/tests-pytest-yellow?logo=pytest)

One command. Gmail message ID in, decoded files + manifest out. No gws knowledge needed.

Agent give message ID. Script fetch, parse MIME, decode base64, write files, produce manifest. Agent read manifest, decide next step. Done.

## Why

Without this: 7+ tool calls, learn gws syntax, wrestle MIME trees, decode URL-safe base64. Every conversation re-learn same quirks. Bad.

With this: one call. Zero discovery. Manifest tell agent everything.

## Quick Start

```bash
# install
uv sync --group dev

# run
uv run python scripts/download_attachments.py <message-id> --to ./downloads

# read result
cat ./downloads/manifest_<message-id>.json
```

## Flags

| Flag | What do |
| --- | --- |
| `--to <dir>` | **(required)** Output dir (created if needed) |
| `--filter <glob>` | Match filenames: `"*.pdf"`, `"*.{pdf,xlsx}"`, `"COA*"` |
| `--include-inline` | Include inline images (sigs/logos skipped by default) |
| `--max-size <MB>` | Skip attachments bigger than this (default: 100) |
| `--dry-run` | Show what would download, no actual download |
| `--json-summary` | Print summary JSON to stdout |

## Exit Codes

| Code | Mean | Do what |
| --- | --- | --- |
| 0 | Success | Read manifest |
| 1 | Auth fail | Re-auth gws |
| 2 | Not found | Check message ID |
| 3 | API error | Retry once |
| 4 | No attachments | Check `skipped[]` in manifest |
| 5 | Disk error | Check perms/space |

Exit 4 not error. Email had no matching attachments. Manifest still written.

## Manifest

Script write `manifest_<message-id>.json` in output dir. Has everything agent need:

```json
{
  "message_id": "19d77c4017cb684d",
  "subject": "Fw: Update on open orders | Protab | NCL",
  "from": "Julio Cordero <julio@naturalcurelabs.com>",
  "date": "2026-04-10T14:20:23Z",
  "files": [
    {
      "filename": "YK772_MONOLAURIN_600_MG.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 184394,
      "sha256": "a1b2c3..."
    }
  ],
  "skipped": [
    { "filename": "image001.jpg", "reason": "inline_image" }
  ],
  "summary": { "downloaded": 2, "skipped": 2, "total_bytes": 368786 }
}
```

Every attachment in `files[]` or `skipped[]` with reason. Nothing silently dropped.

## How It Work

```text
Message ID
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Fetch msg  │────▶│  Parse MIME  │────▶│  Classify   │
│  (_gws.py)  │     │  (_mime.py)  │     │  parts      │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                         ┌──────────────────────┴───────┐
                         ▼                              ▼
                  ┌─────────────┐              ┌──────────────┐
                  │  Download   │              │  Skip inline │
                  │  + decode   │              │  (to skipped)│
                  │  (_fileops) │              └──────────────┘
                  └──────┬──────┘
                         ▼
                  ┌──────────────┐
                  │  Write files │
                  │  + manifest  │
                  │  (_manifest) │
                  └──────────────┘
```

## Project Structure

```text
scripts/
├── download_attachments.py   # orchestrator + CLI
├── _gws.py                   # gws wrapper (only subprocess user)
├── _mime.py                   # MIME walk + classify
├── _fileops.py                # decode, sanitize, write
└── _manifest.py               # manifest dataclass + JSON

tests/                         # pytest, TDD
test_data/                     # scrubbed real gws output
```

## Testing

```bash
uv run pytest                         # all tests
uv run pytest -m "not integration"    # unit only (no gws needed)
uv run pytest -m integration          # needs gws auth
```

## Tech

- **Python 3.13+**, stdlib only. Zero pip deps.
- **`uv`** for project mgmt
- **`gws` CLI** for Gmail API. Already installed + authed.
- All gws quirks (stderr noise, URL-safe base64, MIME nesting) handled internally. Never leak to caller.
