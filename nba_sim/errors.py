"""Errors for configuration and on-disk storage."""

from __future__ import annotations

from pathlib import Path


class NbaSimError(Exception):
    """Base error for this project."""


class ConfigError(NbaSimError):
    """config.yaml or .env is missing a required value or has a bad one."""


class StorageError(NbaSimError):
    """A storage operation cannot be completed safely."""


class PathInsideRepoError(StorageError):
    """DATA_DIR or ARCHIVE_DIR points at the repository tree."""

    def __init__(self, path: Path, repo_root: Path) -> None:
        self.path = path
        self.repo_root = repo_root
        super().__init__(
            f"{path} is inside the repository at {repo_root}. "
            "DATA_DIR and ARCHIVE_DIR must live outside the repo."
        )


class StorageCapExceeded(StorageError):
    """DATA_DIR would grow past the configured cap."""

    def __init__(self, message: str, *, used: int, cap: int, data_dir: Path) -> None:
        super().__init__(message)
        self.used = used
        self.cap = cap
        self.data_dir = data_dir


class SeasonFrozenError(StorageError):
    """A completed season partition cannot be written again."""
