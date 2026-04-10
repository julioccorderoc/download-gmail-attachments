"""Tests for the download_attachments orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, call

import pytest

from _gws import GwsError


# The attachment data used in mocks: decodes to b'Hello, World!' (13 bytes)
MOCK_ATTACHMENT = {"size": 13, "data": "SGVsbG8sIFdvcmxkIQ"}


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create and return a temporary output directory."""
    d = tmp_path / "output"
    d.mkdir()
    return d


class TestFullPipelineSuccess:
    """Test 1: Full pipeline success — files written, manifest created, exit 0."""

    def test_downloads_all_attachments(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            exit_code = run([msg_id, "--to", str(output_dir)])

        assert exit_code == 0

        # Should have 2 PDF files (inline images are skipped by default)
        pdf_files = list(output_dir.glob("*.pdf"))
        assert len(pdf_files) == 2

        # Filenames should be sanitized (spaces -> underscores)
        names = sorted(f.name for f in pdf_files)
        assert all("_" in n for n in names)  # spaces replaced
        assert not any(" " in n for n in names)

        # Each file should contain b'Hello, World!'
        for f in pdf_files:
            assert f.read_bytes() == b"Hello, World!"

        # Manifest should exist
        manifest_files = list(output_dir.glob("manifest_*.json"))
        assert len(manifest_files) == 1

        manifest = json.loads(manifest_files[0].read_text())
        assert manifest["message_id"] == msg_id
        assert len(manifest["files"]) == 2
        assert manifest["summary"]["downloaded"] == 2

    def test_fetch_attachment_called_for_each_kept_part(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT) as mock_fetch,
        ):
            run([msg_id, "--to", str(output_dir)])

        # 2 PDFs kept, so fetch_attachment called twice
        assert mock_fetch.call_count == 2


class TestDryRun:
    """Test 2: Dry-run mode — no files downloaded, manifest written with nulls."""

    def test_dry_run_no_downloads(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment") as mock_fetch,
        ):
            exit_code = run([msg_id, "--to", str(output_dir), "--dry-run"])

        assert exit_code == 0
        mock_fetch.assert_not_called()

        # No PDF files should exist
        pdf_files = list(output_dir.glob("*.pdf"))
        assert len(pdf_files) == 0

    def test_dry_run_manifest_has_null_fields(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment"),
        ):
            run([msg_id, "--to", str(output_dir), "--dry-run"])

        manifest_files = list(output_dir.glob("manifest_*.json"))
        assert len(manifest_files) == 1

        manifest = json.loads(manifest_files[0].read_text())
        for file_entry in manifest["files"]:
            assert file_entry["path"] is None
            assert file_entry["sha256"] is None


class TestFilterPattern:
    """Test 3: --filter '*.pdf' — only PDFs downloaded, images in skipped."""

    def test_filter_pdf_only(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            exit_code = run([msg_id, "--to", str(output_dir), "--filter", "*.pdf"])

        assert exit_code == 0
        pdf_files = list(output_dir.glob("*.pdf"))
        assert len(pdf_files) == 2

    def test_filter_with_include_inline(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        """With --include-inline and --filter *.jpg, only inline images kept."""
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            exit_code = run([
                msg_id, "--to", str(output_dir),
                "--filter", "*.jpg", "--include-inline",
            ])

        assert exit_code == 0
        jpg_files = list(output_dir.glob("*.jpg"))
        assert len(jpg_files) == 2


class TestExitCode4NoAttachments:
    """Test 4: Exit code 4 when no attachments match filter."""

    def test_no_match_returns_4(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment") as mock_fetch,
        ):
            exit_code = run([msg_id, "--to", str(output_dir), "--filter", "*.xlsx"])

        assert exit_code == 4
        mock_fetch.assert_not_called()

    def test_no_match_manifest_written(
        self, sample_message_metadata: dict, output_dir: Path
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment"),
        ):
            run([msg_id, "--to", str(output_dir), "--filter", "*.xlsx"])

        manifest_files = list(output_dir.glob("manifest_*.json"))
        assert len(manifest_files) == 1

        manifest = json.loads(manifest_files[0].read_text())
        assert manifest["files"] == []
        assert len(manifest["skipped"]) > 0


class TestExitCode1Auth:
    """Test 5: Exit code 1 on auth failure."""

    def test_auth_error(self, output_dir: Path) -> None:
        from download_attachments import run

        with patch(
            "download_attachments.fetch_message",
            side_effect=GwsError("auth failed", exit_code=1),
        ):
            exit_code = run(["some_id", "--to", str(output_dir)])

        assert exit_code == 1


class TestExitCode2NotFound:
    """Test 6: Exit code 2 on not found."""

    def test_not_found_error(self, output_dir: Path) -> None:
        from download_attachments import run

        with patch(
            "download_attachments.fetch_message",
            side_effect=GwsError("not found", exit_code=2),
        ):
            exit_code = run(["some_id", "--to", str(output_dir)])

        assert exit_code == 2


class TestStderrSummary:
    """Test 7: Verify stderr summary line format."""

    def test_summary_line(
        self, sample_message_metadata: dict, output_dir: Path, capsys
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            run([msg_id, "--to", str(output_dir)])

        captured = capsys.readouterr()
        # Format: "Downloaded N/M attachments (X.X KB) → <dir>/"
        assert "Downloaded 2/" in captured.err
        assert "attachments" in captured.err
        assert str(output_dir) in captured.err


class TestJsonSummary:
    """Test 8: --json-summary prints summary JSON to stdout."""

    def test_json_summary_stdout(
        self, sample_message_metadata: dict, output_dir: Path, capsys
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            run([msg_id, "--to", str(output_dir), "--json-summary"])

        captured = capsys.readouterr()
        summary = json.loads(captured.out)
        assert "total_parts" in summary
        assert "downloaded" in summary
        assert "skipped" in summary
        assert "total_bytes" in summary
        assert summary["downloaded"] == 2


class TestSizeVerification:
    """Test 9: Size mismatch logs warning but still saves."""

    def test_size_mismatch_warns(
        self, sample_message_metadata: dict, output_dir: Path, caplog
    ) -> None:
        from download_attachments import run
        import logging

        # data decodes to 13 bytes, but reported size is 999
        mismatched = {"size": 999, "data": "SGVsbG8sIFdvcmxkIQ"}

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=mismatched),
            caplog.at_level(logging.WARNING),
        ):
            exit_code = run([msg_id, "--to", str(output_dir)])

        assert exit_code == 0

        # Files still written
        pdf_files = list(output_dir.glob("*.pdf"))
        assert len(pdf_files) == 2

        # Warning logged
        assert any("size mismatch" in r.message.lower() for r in caplog.records)


class TestOutputDirCreated:
    """Output directory is created if it doesn't exist."""

    def test_creates_output_dir(
        self, sample_message_metadata: dict, tmp_path: Path
    ) -> None:
        from download_attachments import run

        output_dir = tmp_path / "nested" / "dir"
        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
        ):
            exit_code = run([msg_id, "--to", str(output_dir)])

        assert exit_code == 0
        assert output_dir.exists()


class TestDiskWriteFailure:
    """Disk write failure returns exit code 5."""

    def test_oserror_returns_5(
        self, sample_message_metadata: dict, output_dir: Path, capsys
    ) -> None:
        from download_attachments import run

        msg_id = sample_message_metadata["id"]

        with (
            patch("download_attachments.fetch_message", return_value=sample_message_metadata),
            patch("download_attachments.fetch_attachment", return_value=MOCK_ATTACHMENT),
            patch("download_attachments.atomic_write", side_effect=OSError("disk full")),
        ):
            exit_code = run([msg_id, "--to", str(output_dir)])

        assert exit_code == 5
        captured = capsys.readouterr()
        assert "disk full" in captured.err.lower() or "oserror" in captured.err.lower() or "disk" in captured.err.lower()
