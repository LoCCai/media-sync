"""media-sync application package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("media-sync")
except PackageNotFoundError:  # pragma: no cover - editable installs provide metadata
    __version__ = "0.1.0"

__all__ = ["__version__"]
