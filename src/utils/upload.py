"""
Temporary upload helpers for session-scoped document processing.

Saves an uploaded-file-like object to a temp path, yields it for
processing, then deletes it. Nothing is kept permanently on disk.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from src.utils.helpers import safe_filename
from src.utils.logger import get_logger

logger = get_logger(__name__)


class UploadedFileLike(Protocol):
    """Minimal protocol for upload adapters (name + bytes)."""

    name: str

    def getbuffer(self) -> Any:
        ...

    def read(self, size: int = -1) -> bytes:
        ...


def _read_upload_bytes(uploaded_file: UploadedFileLike) -> bytes:
    """Extract raw bytes from an uploaded file object."""
    if hasattr(uploaded_file, "getbuffer"):
        try:
            return bytes(uploaded_file.getbuffer())
        except Exception:  # noqa: BLE001
            pass

    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    data = uploaded_file.read()
    return data if isinstance(data, (bytes, bytearray)) else bytes(data)


@contextmanager
def temporary_upload(uploaded_file: UploadedFileLike) -> Iterator[Path]:
    """
    Write ``uploaded_file`` to a temporary path, then delete it.

    Yields:
        Path to the temporary file while it exists.

    Raises:
        ValueError: If the upload has no usable filename or empty content.
    """
    original_name = getattr(uploaded_file, "name", "") or ""
    if not original_name.strip():
        raise ValueError("Uploaded file has no name")

    suffix = Path(original_name).suffix.lower()
    safe_name = safe_filename(Path(original_name).name)

    data = _read_upload_bytes(uploaded_file)
    if not data:
        raise ValueError("Uploaded file is empty")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="session_upload_",
            suffix=suffix or ".bin",
            delete=False,
        ) as handle:
            handle.write(data)
            tmp_path = Path(handle.name)

        logger.info(
            "Document uploaded to temp path | name=%s | bytes=%s | temp=%s",
            safe_name,
            len(data),
            tmp_path,
        )
        yield tmp_path
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.debug("Deleted temporary upload: %s", tmp_path)
            except OSError as exc:
                logger.warning("Failed to delete temporary upload %s: %s", tmp_path, exc)
