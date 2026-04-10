"""Shared test fixtures for download-gmail-attachments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


@pytest.fixture
def sample_message_metadata() -> dict:
    """Load scrubbed Gmail message metadata with nested MIME structure.

    Contains:
    - 2 inline images (image001.jpg, image002.jpg) nested in multipart/related
    - 2 PDF attachments at top-level multipart/mixed
    - Text/plain and text/html body parts nested 3 levels deep
    """
    return json.loads((TEST_DATA_DIR / "sample_message_metadata.json").read_text())


@pytest.fixture
def sample_attachment_response() -> dict:
    """Load scrubbed Gmail attachment response.

    Contains 'size' (decoded byte count) and 'data' (URL-safe base64).
    The sample decodes to b'Hello, World!' (13 bytes).
    """
    return json.loads((TEST_DATA_DIR / "sample_attachment.json").read_text())


@pytest.fixture
def message_payload(sample_message_metadata: dict) -> dict:
    """Return just the payload portion of the message metadata."""
    return sample_message_metadata["payload"]
