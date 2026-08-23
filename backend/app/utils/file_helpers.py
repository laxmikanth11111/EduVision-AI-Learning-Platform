from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from app.core.config import settings

SUPPORTED_DOCUMENT_EXTENSIONS: set[str] = {".pdf", ".docx", ".pptx", ".txt"}


def get_file_extension(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    return ext.lower()


def is_extension_allowed(filename: str) -> bool:
    ext = get_file_extension(filename)
    return ext in settings.allowed_extensions_list


def is_document_extension_allowed(filename: str) -> bool:
    ext = get_file_extension(filename)
    return ext in SUPPORTED_DOCUMENT_EXTENSIONS


def get_content_type(filename: str) -> str:
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


def validate_magic_bytes(header: bytes, filename: str) -> bool:
    """Validate file binary header against expected magic byte signatures."""
    if not header:
        return False
    ext = get_file_extension(filename)
    if ext == ".pdf":
        return header.startswith(b"%PDF")
    if ext in (".pptx", ".docx"):
        return header.startswith(b"PK\x03\x04")
    if ext in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".mp4":
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if ext == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if ext == ".txt":
        return b"\x00" not in header[:512]
    return True


def human_readable_size(size_bytes: int) -> str:
    size: float = size_bytes
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def is_within_size_limit(size_bytes: int) -> bool:
    return size_bytes <= settings.UPLOAD_MAX_FILE_SIZE


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str) -> str:
    import re

    name, ext = os.path.splitext(filename)
    name = re.sub(r"[^\w\-_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return f"{name}{ext}"
