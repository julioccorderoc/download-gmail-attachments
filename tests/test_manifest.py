"""Tests for _manifest module — manifest dataclass + JSON serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from _manifest import (
    FileEntry,
    Manifest,
    SkippedEntry,
    Summary,
    build_manifest,
    extract_header,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_headers() -> list[dict]:
    return [
        {"name": "Subject", "value": "Invoice Q1 2026"},
        {"name": "From", "value": "alice@example.com"},
        {"name": "Date", "value": "Mon, 6 Apr 2026 10:30:00 -0400"},
        {"name": "To", "value": "bob@example.com"},
    ]


@pytest.fixture
def sample_metadata(sample_headers: list[dict]) -> dict:
    """Minimal Gmail message dict with payload.headers."""
    return {"payload": {"headers": sample_headers}}


@pytest.fixture
def two_files() -> list[FileEntry]:
    return [
        FileEntry(
            filename="report.pdf",
            original_filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=12345,
            sha256="aabbcc",
            disposition="attachment",
            path="/out/report.pdf",
        ),
        FileEntry(
            filename="photo.jpg",
            original_filename="photo.jpg",
            mime_type="image/jpeg",
            size_bytes=67890,
            sha256="ddeeff",
            disposition="attachment",
            path="/out/photo.jpg",
        ),
    ]


@pytest.fixture
def one_skipped() -> list[SkippedEntry]:
    return [
        SkippedEntry(filename="logo.png", reason="inline image", size_bytes=999),
    ]


FROZEN_NOW = "2026-04-10T12:00:00+00:00"


# ---------------------------------------------------------------------------
# extract_header
# ---------------------------------------------------------------------------

class TestExtractHeader:
    def test_extracts_subject(self, sample_headers: list[dict]) -> None:
        assert extract_header(sample_headers, "Subject") == "Invoice Q1 2026"

    def test_extracts_from(self, sample_headers: list[dict]) -> None:
        assert extract_header(sample_headers, "From") == "alice@example.com"

    def test_returns_empty_when_missing(self, sample_headers: list[dict]) -> None:
        assert extract_header(sample_headers, "X-Custom") == ""

    def test_case_insensitive(self, sample_headers: list[dict]) -> None:
        assert extract_header(sample_headers, "subject") == "Invoice Q1 2026"
        assert extract_header(sample_headers, "SUBJECT") == "Invoice Q1 2026"

    def test_empty_headers_list(self) -> None:
        assert extract_header([], "Subject") == ""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

class TestFileEntry:
    def test_fields(self) -> None:
        f = FileEntry(
            filename="a.pdf",
            original_filename="a.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="abc",
            disposition="attachment",
            path="/tmp/a.pdf",
        )
        assert f.filename == "a.pdf"
        assert f.size_bytes == 100

    def test_path_none_for_dry_run(self) -> None:
        f = FileEntry(
            filename="a.pdf",
            original_filename="a.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256="abc",
            disposition="attachment",
            path=None,
        )
        assert f.path is None


class TestSkippedEntry:
    def test_fields(self) -> None:
        s = SkippedEntry(filename="img.png", reason="inline image", size_bytes=50)
        assert s.reason == "inline image"


class TestSummary:
    def test_fields(self) -> None:
        s = Summary(total_parts=5, downloaded=3, skipped=2, total_bytes=999)
        assert s.total_parts == 5
        assert s.downloaded == 3
        assert s.skipped == 2
        assert s.total_bytes == 999


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    @patch("_manifest.datetime")
    def test_produces_correct_structure(
        self,
        mock_dt: object,
        sample_metadata: dict,
        two_files: list[FileEntry],
        one_skipped: list[SkippedEntry],
    ) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)  # type: ignore[attr-defined]

        m = build_manifest(
            message_id="msg123",
            metadata=sample_metadata,
            files=two_files,
            skipped=one_skipped,
            output_dir="/out",
        )

        assert m.message_id == "msg123"
        assert m.subject == "Invoice Q1 2026"
        assert m.from_ == "alice@example.com"
        assert m.date == "Mon, 6 Apr 2026 10:30:00 -0400"
        assert m.downloaded_at == "2026-04-10T12:00:00+00:00"
        assert m.output_dir == "/out"
        assert len(m.files) == 2
        assert len(m.skipped) == 1

    @patch("_manifest.datetime")
    def test_summary_counts(
        self,
        mock_dt: object,
        sample_metadata: dict,
        two_files: list[FileEntry],
        one_skipped: list[SkippedEntry],
    ) -> None:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)  # type: ignore[attr-defined]

        m = build_manifest(
            message_id="msg123",
            metadata=sample_metadata,
            files=two_files,
            skipped=one_skipped,
            output_dir="/out",
        )

        assert m.summary.total_parts == 3
        assert m.summary.downloaded == 2
        assert m.summary.skipped == 1
        assert m.summary.total_bytes == 12345 + 67890


# ---------------------------------------------------------------------------
# Manifest.to_json / to_dict
# ---------------------------------------------------------------------------

class TestManifestSerialization:
    def _make_manifest(self) -> Manifest:
        return Manifest(
            message_id="msg456",
            subject="Test Subject",
            from_="sender@example.com",
            date="Thu, 10 Apr 2026 08:00:00 +0000",
            downloaded_at=FROZEN_NOW,
            output_dir="/output",
            files=[
                FileEntry(
                    filename="doc.pdf",
                    original_filename="doc.pdf",
                    mime_type="application/pdf",
                    size_bytes=500,
                    sha256="deadbeef",
                    disposition="attachment",
                    path="/output/doc.pdf",
                ),
            ],
            skipped=[
                SkippedEntry(filename="icon.png", reason="inline image", size_bytes=42),
            ],
            summary=Summary(total_parts=2, downloaded=1, skipped=1, total_bytes=500),
        )

    def test_to_dict_uses_from_not_from_(self) -> None:
        m = self._make_manifest()
        d = m.to_dict()
        assert "from" in d
        assert "from_" not in d
        assert d["from"] == "sender@example.com"

    def test_to_json_top_level_keys(self) -> None:
        m = self._make_manifest()
        data = json.loads(m.to_json())
        expected_keys = {
            "message_id", "subject", "from", "date",
            "downloaded_at", "output_dir", "files", "skipped", "summary",
        }
        assert set(data.keys()) == expected_keys

    def test_to_json_file_entry_keys(self) -> None:
        m = self._make_manifest()
        data = json.loads(m.to_json())
        file_keys = set(data["files"][0].keys())
        expected = {
            "filename", "original_filename", "mime_type",
            "size_bytes", "sha256", "disposition", "path",
        }
        assert file_keys == expected

    def test_to_json_skipped_entry_keys(self) -> None:
        m = self._make_manifest()
        data = json.loads(m.to_json())
        skipped_keys = set(data["skipped"][0].keys())
        assert skipped_keys == {"filename", "reason", "size_bytes"}

    def test_to_json_summary_keys(self) -> None:
        m = self._make_manifest()
        data = json.loads(m.to_json())
        summary_keys = set(data["summary"].keys())
        assert summary_keys == {"total_parts", "downloaded", "skipped", "total_bytes"}

    def test_to_json_is_valid_json(self) -> None:
        m = self._make_manifest()
        # Should not raise
        json.loads(m.to_json())

    def test_to_json_values(self) -> None:
        m = self._make_manifest()
        data = json.loads(m.to_json())
        assert data["message_id"] == "msg456"
        assert data["files"][0]["sha256"] == "deadbeef"
        assert data["summary"]["total_bytes"] == 500


# ---------------------------------------------------------------------------
# Manifest.write
# ---------------------------------------------------------------------------

class TestManifestWrite:
    def test_writes_file(self, tmp_path: Path) -> None:
        m = Manifest(
            message_id="abc123",
            subject="S",
            from_="f@x.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir=str(tmp_path),
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        result = m.write(tmp_path)
        assert result == tmp_path / "manifest_abc123.json"
        assert result.exists()

    def test_file_contains_valid_json(self, tmp_path: Path) -> None:
        m = Manifest(
            message_id="abc123",
            subject="S",
            from_="f@x.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir=str(tmp_path),
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        path = m.write(tmp_path)
        data = json.loads(path.read_text())
        assert data["message_id"] == "abc123"

    def test_write_matches_to_json(self, tmp_path: Path) -> None:
        m = Manifest(
            message_id="abc123",
            subject="S",
            from_="f@x.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir=str(tmp_path),
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        path = m.write(tmp_path)
        assert path.read_text() == m.to_json()

    def test_returns_path(self, tmp_path: Path) -> None:
        m = Manifest(
            message_id="xyz",
            subject="S",
            from_="f@x.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir=str(tmp_path),
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        result = m.write(tmp_path)
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_files_with_skipped(self) -> None:
        """Exit code 4 scenario: no downloadable attachments."""
        m = Manifest(
            message_id="msg_empty",
            subject="No attachments",
            from_="a@b.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir="/out",
            files=[],
            skipped=[
                SkippedEntry(filename="x.png", reason="inline", size_bytes=10),
            ],
            summary=Summary(total_parts=1, downloaded=0, skipped=1, total_bytes=0),
        )
        data = json.loads(m.to_json())
        assert data["files"] == []
        assert len(data["skipped"]) == 1
        assert data["summary"]["downloaded"] == 0

    def test_empty_both(self) -> None:
        m = Manifest(
            message_id="msg_none",
            subject="Nothing",
            from_="a@b.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir="/out",
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        data = json.loads(m.to_json())
        assert data["files"] == []
        assert data["skipped"] == []

    def test_special_chars_in_message_id(self, tmp_path: Path) -> None:
        """Message IDs can contain chars that are problematic in filenames."""
        msg_id = "abc/def+ghi=jkl"
        m = Manifest(
            message_id=msg_id,
            subject="S",
            from_="a@b.com",
            date="d",
            downloaded_at=FROZEN_NOW,
            output_dir=str(tmp_path),
            files=[],
            skipped=[],
            summary=Summary(total_parts=0, downloaded=0, skipped=0, total_bytes=0),
        )
        path = m.write(tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["message_id"] == msg_id
