"""Stable failures exposed by the Emby/Jellyfin exporter."""

from __future__ import annotations


class ExportError(RuntimeError):
    """An export failed with a stable, non-secret reason code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Emby/Jellyfin export failed: {code}")


class ExportConflictError(ExportError):
    """Publishing would overwrite user-owned or user-modified bytes."""


__all__ = ["ExportConflictError", "ExportError"]
