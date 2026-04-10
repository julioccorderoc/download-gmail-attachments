"""End-to-end integration tests requiring gws CLI authentication.

Run with: uv run pytest tests/test_integration.py -m integration
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from download_attachments import run

# Known message with 2 PDF attachments + 2 inline images
KNOWN_MESSAGE_ID = "19d77c4017cb684d"


@pytest.mark.integration
class TestEndToEnd:
    """Full pipeline with real gws CLI calls."""

    def test_downloads_attachments(self, tmp_path: Path) -> None:
        output_dir = str(tmp_path / "output")
        exit_code = run([KNOWN_MESSAGE_ID, "--to", output_dir])

        assert exit_code == 0

        manifest_path = tmp_path / "output" / f"manifest_{KNOWN_MESSAGE_ID}.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["message_id"] == KNOWN_MESSAGE_ID
        assert manifest["summary"]["downloaded"] == 2
        assert manifest["summary"]["skipped"] == 2

        # Verify files exist on disk
        for f in manifest["files"]:
            assert Path(f["path"]).exists()
            assert Path(f["path"]).stat().st_size == f["size_bytes"]
            assert f["sha256"] is not None

        # Verify skipped are inline images
        for s in manifest["skipped"]:
            assert s["reason"] == "inline_image"

    def test_dry_run(self, tmp_path: Path) -> None:
        output_dir = str(tmp_path / "output")
        exit_code = run([KNOWN_MESSAGE_ID, "--to", output_dir, "--dry-run"])

        assert exit_code == 0

        manifest_path = tmp_path / "output" / f"manifest_{KNOWN_MESSAGE_ID}.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["summary"]["downloaded"] == 2

        # Dry-run: no actual files on disk
        for f in manifest["files"]:
            assert f["path"] is None
            assert f["sha256"] is None

    def test_filter_pdf(self, tmp_path: Path) -> None:
        output_dir = str(tmp_path / "output")
        exit_code = run([KNOWN_MESSAGE_ID, "--to", output_dir, "--filter", "*.pdf"])

        assert exit_code == 0

        manifest_path = tmp_path / "output" / f"manifest_{KNOWN_MESSAGE_ID}.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["summary"]["downloaded"] == 2
        assert all(f["filename"].endswith(".pdf") for f in manifest["files"])

    def test_filter_no_match(self, tmp_path: Path) -> None:
        output_dir = str(tmp_path / "output")
        exit_code = run([KNOWN_MESSAGE_ID, "--to", output_dir, "--filter", "*.xlsx"])

        assert exit_code == 4

        manifest_path = tmp_path / "output" / f"manifest_{KNOWN_MESSAGE_ID}.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["summary"]["downloaded"] == 0

    def test_invalid_message_id(self, tmp_path: Path) -> None:
        output_dir = str(tmp_path / "output")
        exit_code = run(["nonexistent_message_id_12345", "--to", output_dir])

        assert exit_code in (1, 2, 3)  # gws returns 1 for invalid IDs
