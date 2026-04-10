# download-gmail-attachments

![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue?logo=python&logoColor=white)
![stdlib only](https://img.shields.io/badge/dependencies-zero-brightgreen)
![gws CLI](https://img.shields.io/badge/gws-v0.22.5%2B-orange)
![Tests](https://img.shields.io/badge/tests-121_passing-yellow?logo=pytest)

Agent skill that downloads Gmail attachments by message ID. One command — files + manifest out. Zero gws knowledge needed.

## Install

```bash
npx skills add julioccorderoc/download-gmail-attachments -g -y
```

Or install to a specific agent:

```bash
npx skills add julioccorderoc/download-gmail-attachments -a claude-code
npx skills add julioccorderoc/download-gmail-attachments -a cursor
```

### Prerequisites

- **Python 3.13+** (stdlib only, zero pip dependencies)
- **[uv](https://docs.astral.sh/uv/)** for project management
- **[gws CLI](https://github.com/nicholasgasior/gws) v0.22.5+** installed and authenticated

```bash
uv sync --group dev
```

## Usage

```bash
uv run python scripts/download_attachments.py <message-id> --to <output-dir>
```

Read the result:

```bash
cat <output-dir>/manifest_<message-id>.json
```

### Flags

| Flag | Description |
| --- | --- |
| `--to <dir>` | **(required)** Output directory (created if needed) |
| `--filter <glob>` | Filename pattern: `"*.pdf"`, `"*.{pdf,xlsx}"`, `"COA*"` |
| `--include-inline` | Include inline images (signatures/logos skipped by default) |
| `--max-size <MB>` | Skip attachments larger than this (default: 100) |
| `--dry-run` | Show what would download without downloading |
| `--json-summary` | Print summary JSON to stdout |

### Exit Codes

| Code | Meaning | Action |
| --- | --- | --- |
| 0 | Success | Read manifest |
| 1 | Auth failure | Re-authenticate gws |
| 2 | Not found | Check message ID |
| 3 | API error | Retry once |
| 4 | No attachments | Check `skipped[]` in manifest |
| 5 | Disk error | Check permissions/space |

Exit 4 is not an error. Email had no matching attachments. Manifest still written.

## Manifest

The script writes `manifest_<message-id>.json` in the output directory with everything an agent needs to decide next steps:

```json
{
  "message_id": "your-message-id",
  "subject": "Your-subject",
  "from": "your-email@gmail.com",
  "date": "2026-04-10T14:20:23Z",
  "files": [
    {
      "filename": "your-file.pdf",
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

Every attachment ends up in `files[]` or `skipped[]` with a reason. Nothing is silently dropped.

## How It Works

```text
Message ID
    |
    v
+-----------+     +------------+     +-----------+
| Fetch msg |---->| Parse MIME |---->| Classify  |
| (_gws.py) |     | (_mime.py) |     | parts     |
+-----------+     +------------+     +-----+-----+
                                           |
                       +-------------------+--------+
                       v                            v
                +-----------+              +--------------+
                | Download  |              | Skip inline  |
                | + decode  |              | (to skipped) |
                | (_fileops)|              +--------------+
                +-----+-----+
                      v
                +--------------+
                | Write files  |
                | + manifest   |
                | (_manifest)  |
                +--------------+
```

## Project Structure

```text
scripts/
  download_attachments.py   # orchestrator + CLI
  _gws.py                   # gws wrapper (only subprocess caller)
  _mime.py                   # MIME walk + classify
  _fileops.py                # decode, sanitize, write
  _manifest.py               # manifest dataclass + JSON

tests/                       # pytest, TDD (121 tests)
test_data/                   # scrubbed real gws output
```

## Testing

```bash
uv run pytest                         # all tests
uv run pytest -m "not integration"    # unit only (no gws needed)
uv run pytest -m integration          # needs gws auth
```

## Why This Exists

Without this skill: 7+ tool calls, learn gws syntax, wrestle MIME trees, decode URL-safe base64. Every conversation re-learns the same quirks.

With this skill: one call, zero discovery, manifest tells the agent everything.

## License

MIT
