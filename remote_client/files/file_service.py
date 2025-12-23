"""File system operations exposed over the data channel."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FileEntry:
    name: str
    is_dir: bool
    size: int | None


class FileService:
    """Provides file listing and download helper methods."""

    def list_files(self, path: str) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for entry in os.scandir(path):
            entries.append(
                FileEntry(
                    name=entry.name,
                    is_dir=entry.is_dir(),
                    size=entry.stat().st_size if entry.is_file() else None,
                )
            )
        return entries

    def serialize_entries(self, entries: Iterable[FileEntry]) -> list[dict[str, object]]:
        return [
            {"name": entry.name, "is_dir": entry.is_dir, "size": entry.size}
            for entry in entries
        ]

    def read_file_base64(self, path: str) -> str:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode()
