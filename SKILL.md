---
name: download-gmail-attachments
description: "Download file attachments from a Gmail message by ID and save them locally with a machine-readable manifest. Use this skill whenever the agent has a Gmail message ID and needs to extract attachments — whether for COA processing, document extraction, data analysis, spreadsheet import, or any downstream file handling. Also use when the user says 'download attachments', 'save email files', 'get attachments from Gmail', 'extract files from email', or refers to processing files attached to an email."
---

# download-gmail-attachments

Download attachments from a Gmail message to a local directory. Run the script, then read the manifest for results.

## Invocation

```bash
uv run python scripts/download_attachments.py <message-id> --to <output-dir> [options]
```

## Prerequisites

| Check | Verify | If missing |
|---|---|---|
| `uv` | `which uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python 3.13+ | `uv python list` | `uv python install 3.13` |
| `gws` CLI | `gws --version` (need ≥ 0.22.5) | `brew install googleworkspace-cli` |
| gws auth | `gws auth status` | `gws auth login` (opens browser for OAuth) |

## Flags

| Flag | Description |
|---|---|
| `--to <dir>` | **(required)** Output directory (created if needed) |
| `--filter <glob>` | Filename pattern, e.g. `"*.pdf"`, `"*.{pdf,xlsx}"`, `"COA*"` |
| `--include-inline` | Include inline images (signatures/logos, skipped by default) |
| `--max-size <MB>` | Skip attachments larger than this (default: 100) |
| `--dry-run` | Show what would download without downloading |
| `--json-summary` | Print summary JSON to stdout |

## Exit Codes

| Code | Meaning | Action |
|---|---|---|
| 0 | Success | Read manifest |
| 1 | Auth failure | Re-authenticate gws |
| 2 | Message not found | Check message ID |
| 3 | API error (transient) | Retry once |
| 4 | No matching attachments | Check manifest skipped[] |
| 5 | Disk write failure | Check permissions/space |

## Results

Read `<output-dir>/manifest_<message-id>.json` for download results. The manifest lists every file in `files[]` and every skipped part in `skipped[]` with reasons — nothing is silently dropped. Use the manifest to decide next steps without inspecting the files directly.
