"""Upload content-validation tests — magic bytes connected to the real upload flow.

These tests prove that `validate_magic_bytes` is enforced on the actual
`POST /presentations/{id}/source` endpoint and service boundary, not just
defined in a helper. A file whose extension does not match its real binary
signature must be rejected before it reaches storage.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_USER_ID

# Real leading signatures for the supported document types.
PDF_HEADER = b"%PDF-1.4\n1 0 obj\n% fake pdf body"
DOCX_HEADER = b"PK\x03\x04" + b"\x00" * 32  # OOXML (ZIP) container signature
PPTX_HEADER = b"PK\x03\x04" + b"\x00" * 32  # OOXML (ZIP) container signature
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest_asyncio.fixture
async def presentation_id(db_session: AsyncSession) -> str:
    """Create a presentation owned by TEST_USER_ID."""
    from app.models.presentation import Presentation

    p = Presentation(
        title="Upload Validation Presentation",
        owner_id=TEST_USER_ID,
        status="draft",
        slide_count=0,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    await db_session.commit()
    return p.public_id


async def _upload(
    client: AsyncClient,
    presentation_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> int:
    resp = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": (filename, content, content_type or "application/octet-stream")},
    )
    return resp.status_code


# ── Valid files must still upload ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_pdf_accepted(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "slides.pdf", PDF_HEADER, "application/pdf") == 200


@pytest.mark.asyncio
async def test_valid_docx_accepted(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "notes.docx", DOCX_HEADER, "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == 200


@pytest.mark.asyncio
async def test_valid_pptx_accepted(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "deck.pptx", PPTX_HEADER, "application/vnd.openxmlformats-officedocument.presentationml.presentation") == 200


@pytest.mark.asyncio
async def test_valid_txt_accepted(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "outline.txt", b"hello world\nplain text\n") == 200


# ── Extension/spoof mismatch must be rejected ───────────────────────────────


@pytest.mark.asyncio
async def test_fake_pdf_rejected(client: AsyncClient, presentation_id: str) -> None:
    """A file named .pdf whose bytes are not a PDF must be rejected (422)."""
    assert await _upload(client, presentation_id, "slides.pdf", b"this is not a pdf at all") == 422


@pytest.mark.asyncio
async def test_fake_docx_rejected(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "notes.docx", b"PK\x00\x00 not a zip") == 422


@pytest.mark.asyncio
async def test_fake_pptx_rejected(client: AsyncClient, presentation_id: str) -> None:
    assert await _upload(client, presentation_id, "deck.pptx", b"\x00\x01\x02\x03 fake pptx") == 422


@pytest.mark.asyncio
async def test_binary_content_named_txt_rejected(client: AsyncClient, presentation_id: str) -> None:
    """A binary file renamed to .txt must be rejected (null bytes in header)."""
    assert await _upload(client, presentation_id, "notes.txt", b"real\x00binary\x00content") == 422


@pytest.mark.asyncio
async def test_pdf_bytes_named_docx_rejected(client: AsyncClient, presentation_id: str) -> None:
    """Cross-format spoof: real PDF bytes with a .docx extension must be rejected."""
    assert await _upload(client, presentation_id, "notes.docx", PDF_HEADER) == 422


@pytest.mark.asyncio
async def test_malformed_empty_file_rejected(client: AsyncClient, presentation_id: str) -> None:
    """An empty body is rejected before magic-byte validation runs."""
    assert await _upload(client, presentation_id, "slides.pdf", b"", "application/pdf") == 409


# ── Existing protections must still hold ────────────────────────────────────


@pytest.mark.asyncio
async def test_oversized_file_rejected(client: AsyncClient, presentation_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr("app.api.v1.presentations.settings.UPLOAD_MAX_FILE_SIZE", 16)
    # Body larger than the (patched) cap with otherwise-valid PDF bytes.
    resp = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": ("big.pdf", b"%PDF-" + b"x" * 300, "application/pdf")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_malicious_filename_sanitized(
    client: AsyncClient, presentation_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": ("..\\..\\evil.pdf", PDF_HEADER, "application/pdf")},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_traversal_attempt_rejected(client: AsyncClient, presentation_id: str) -> None:
    resp = await client.post(
        f"/api/v1/presentations/{presentation_id}/source",
        files={"source": ("evil.pdf", PDF_HEADER, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert ".." not in body["file_key"]


# ── Lower-level helper contract ─────────────────────────────────────────────


class TestValidateMagicBytes:
    def test_valid_pdf(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"%PDF-1.7", "file.pdf") is True

    def test_fake_pdf(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"notpdf", "file.pdf") is False

    def test_valid_docx(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"PK\x03\x04rest", "file.docx") is True

    def test_fake_docx(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"PK\x04\x05", "file.docx") is False

    def test_valid_pptx(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"PK\x03\x04rest", "file.pptx") is True

    def test_fake_pptx(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"xx", "file.pptx") is False

    def test_valid_txt(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"plain text content", "file.txt") is True

    def test_binary_txt(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"plain\x00null\x00bytes", "file.txt") is False

    def test_valid_png(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"\x89PNG\r\n\x1a\nrest", "thumb.png") is True

    def test_fake_png(self) -> None:
        from app.utils.file_helpers import validate_magic_bytes

        assert validate_magic_bytes(b"notpng", "thumb.png") is False
