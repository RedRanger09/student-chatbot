"""
Shared helper utilities used across the project.

Keep this module free of domain-specific business logic.
"""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """
    Create a directory (and parents) if it does not exist.

    Args:
        path: Directory path to ensure.

    Returns:
        The same path, for convenient chaining.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """
    Sanitize a filename by replacing characters unsafe for common filesystems.

    Args:
        name: Original filename or user-provided string.

    Returns:
        A filesystem-safe filename string.
    """
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in forbidden else ch for ch in name.strip())
    return cleaned or "unnamed"
