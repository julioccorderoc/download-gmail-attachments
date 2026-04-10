# PRD: `download-gmail-attachments` Skill

## Problem

Autonomous AI agent owns Gmail inbox. On trigger, must extract file attachments from specific message, save locally for downstream processing (`doc-extractor`, `data-analysis`, `xlsx`).

Today: **7+ tool calls**, trial-and-error `gws` syntax, Gmail MIME knowledge, manual URL-safe base64. Three calls wasted on CLI discovery. Every conversation re-learns same quirks. Unacceptable for autonomous agent.

### Agent knows at invocation

Agent already triggered by specific email. Has **message ID**. Already decided attachments worth downloading. Skill doesn't decide — skill executes.

### Agent needs after invocation

1. Files on disk, correctly decoded, clean filenames
2. **Manifest** describing downloads — agent decides next step without reading files
3. Confidence nothing silently dropped or corrupted

## Solution

Single wrapper script (`download_attachments.py`) encapsulating all `gws` interaction, MIME traversal, base64 decode, file I/O.

```text
/download-attachments <message-id> --to <directory> [--filter <pattern>] [--include-inline] [--max-size <MB>] [--dry-run]
```

One tool call. Zero gws knowledge from agent.

## Scope

### In

- Download attachments from single Gmail message by ID
- Handle any file type (PDF, PNG, JPG, WEBP, XLSX, DOCX, CSV, ZIP, etc.)
- Filter by extension glob
- Distinguish real attachments vs inline images (signatures)
- Machine-readable manifest
- Handle all gws quirks internally

### Out

- Searching emails (agent has message ID)
- Deciding whether to download (agent decided)
- Processing downloads (downstream skills)
- Multi-message batch (one ID per invocation; agent can loop)

## Detailed Requirements

### 1. Core Pipeline

Steps in order:

1. **Fetch metadata** — `gws gmail users messages get`, stderr suppressed
2. **Parse MIME tree** — walk `payload.parts` recursively (arbitrary nesting, forwarded msgs)
3. **Classify parts** — real attachment vs inline via:
   - `Content-Disposition` (`attachment` vs `inline`)
   - `Content-ID` header presence (inline refs)
   - Filename patterns (`imageNNN.jpg` = signatures)
   - Size heuristic (inline sigs < 50KB)
4. **Apply filters** — `--filter` glob against filename
5. **Download** — `gws gmail users messages attachments get` with attachment ID
6. **Decode** — URL-safe base64: `-`→`+`, `_`→`/`, pad `=`
7. **Verify** — decoded size matches Gmail `size` field
8. **Sanitize filename** — bad chars, unicode, truncate
9. **Collision** — append `_1`, `_2` if exists
10. **Write** — atomic (temp + rename), no partial files
11. **Manifest** — write `manifest.json` alongside files

### 2. Manifest

Primary interface between skill and agent. Everything agent needs to decide next — without reading files.

**Location:** `<output-dir>/manifest.json`

```json
{
  "message_id": "19d77c4017cb684d",
  "subject": "Fw: Update on open orders | Protab | NCL",
  "from": "Julio Cordero <julio@naturalcurelabs.com>",
  "date": "2026-04-10T14:20:23Z",
  "downloaded_at": "2026-04-10T13:15:42Z",
  "output_dir": "/Users/juliocordero/Downloads/coa_downloads/",
  "files": [
    {
      "filename": "YK772_MONOLAURIN_600_MG_AND_L-LYSINE_HCL_600_MG_CAPSULE_PO_PT02.pdf",
      "original_filename": "YK772_MONOLAURIN 600 MG AND L-LYSINE HCL 600 MG CAPSULE _PO_PT02.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 184394,
      "sha256": "a1b2c3...",
      "disposition": "attachment",
      "path": "/Users/juliocordero/Downloads/coa_downloads/YK772_MONOLAURIN_600_MG_AND_L-LYSINE_HCL_600_MG_CAPSULE_PO_PT02.pdf"
    }
  ],
  "skipped": [
    {
      "filename": "image001.jpg",
      "reason": "inline_image",
      "size_bytes": 2298
    }
  ],
  "summary": {
    "total_parts": 4,
    "downloaded": 2,
    "skipped": 2,
    "total_bytes": 368786
  }
}
```

**Design decisions:**

- `skipped[]` tells agent what ignored + why — no silent drops
- `original_filename` vs `filename` tracks sanitization
- `sha256` for downstream integrity verification
- `disposition` = real attachment or inline
- `summary` = quick overview without iterating `files[]`

### 3. Inline Image Handling

Default: skip inline images (sigs, logos). Agent rarely wants these.

**Classification (order matters):**

1. `Content-Disposition: inline` + `Content-ID` → inline → skip
2. Filename matches `image\d+\.(jpg|png|gif)` → likely sig → skip
3. Image < 50KB + `Content-Disposition: inline` → likely sig → skip

**Override:** `--include-inline` downloads all, marks disposition in manifest.

### 4. Filtering

`--filter` = glob on filenames:

- `--filter "*.pdf"` — PDFs only
- `--filter "*.{pdf,xlsx}"` — PDFs + spreadsheets
- `--filter "COA*"` — COA-prefixed

Filter applies **after** inline classification. `--filter "*.jpg" --include-inline` gets all JPGs including inline.

No filter = all non-inline attachments.

### 5. Dry Run

`--dry-run` does steps 1-4 (fetch, parse, classify, filter), outputs manifest of what **would** download. `files[]` has metadata but `path` = `null`, `sha256` = `null`.

Agent inspects email contents before committing.

### 6. Error Handling & Exit Codes

| Exit | Meaning | Agent action |
|---|---|---|
| `0` | Success | Read manifest, proceed |
| `1` | Auth failure | Tell user re-auth gws |
| `2` | Message not found | Log warning, skip |
| `3` | API error (transient) | Retry once, then report |
| `4` | No attachments (after filter) | Log info, check manifest |
| `5` | Disk write failure | Report, check perms/space |

**Exit 4 not error.** Email had no matching attachments. Manifest still written with empty `files[]` + populated `skipped[]`.

### 7. Output

- **stderr** — one-line summary: `Downloaded 2/4 attachments (368.8 KB) → ~/Downloads/coa_downloads/`
- **stdout** — nothing default. `--json-summary` prints manifest summary JSON.
- **Manifest** — always at `<output-dir>/manifest.json`

## Skill Prompt Design

Must be **minimal** (< 400 tokens): invocation syntax, flags table, exit codes table, "read manifest.json for results."

All logic in script. Prompt teaches **how to invoke**, not internals.

## Technical Notes

### gws Quirks (in `_gws.py`, never exposed)

- Params via `--params '<json>'`, not CLI flags
- stderr has `"Using keyring backend: keyring"` — suppress
- URL-safe base64: `-`→`+`, `_`→`/`, pad `=`
- `size` = decoded byte count
- MIME nests deep — recurse

### Dependencies

- Python 3.9+ (stdlib only: `json`, `base64`, `hashlib`, `pathlib`, `subprocess`, `fnmatch`)
- `gws` CLI (installed + authenticated)

### File Structure

```text
download-gmail-attachments/
├── pyproject.toml
├── scripts/
│   └── download_attachments.py
└── skill.md                  # < 400 tokens
```

## Success Criteria

1. **One tool call** — invoke once, get files + manifest
2. **Zero gws knowledge** — agent never sees `--params`, base64, MIME, stderr
3. **Manifest-driven** — agent reads ~500 byte manifest for next steps
4. **No silent failures** — every attachment in `files[]` or `skipped[]` with reason
5. **Composable** — output dir + manifest plugs into `doc-extractor`, `xlsx`, `pdf`
6. **Skill prompt < 400 tokens**

## Resolved Decisions

1. **Manifest strategy** — per-message (`manifest_<message-id>.json`). Multiple emails same dir won't overwrite metadata.
2. **Max size** — warn > 25MB, skip > 100MB. `--max-size` flag (MB). Skipped oversized in `skipped[]` reason `"exceeds_size_limit"`.
3. **Rate limiting** — v1 included. 429 handled with exponential backoff (1s initial, 32s max, 5 retries). Transient 429s never surface to agent.
