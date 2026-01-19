"""File system operations exposed over the data channel."""
from __future__ import annotations

import base64
import os
import string
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FileEntry:
    name: str
    path: str
    is_dir: bool
    size: int | None


class FileServiceError(RuntimeError):
    """Raised when file operations fail."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FileService:
    """Provides file listing and download helper methods."""

    def list_files_with_base(self, path: str) -> tuple[str, list[FileEntry]]:
        if not path:
            path = "."
        if os.name == "nt" and path in {".", "/", "\\"}:
            return ".", self._list_windows_drives()
        if os.name != "nt" and path == ".":
            path = "/"
        entries: list[FileEntry] = []
        try:
            for entry in os.scandir(path):
                entries.append(
                    FileEntry(
                        name=entry.name,
                        path=entry.path,
                        is_dir=entry.is_dir(),
                        size=entry.stat().st_size if entry.is_file() else None,
                    )
                )
        except OSError as exc:
            raise FileServiceError("list_failed", str(exc)) from exc
        return path, entries

    def list_files(self, path: str) -> list[FileEntry]:
        _, entries = self.list_files_with_base(path)
        return entries

    def _list_windows_drives(self) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                entries.append(FileEntry(name=drive, path=drive, is_dir=True, size=None))
        if not entries:
            raise FileServiceError("list_failed", "No drives found.")
        return entries

    def serialize_entries(self, entries: Iterable[FileEntry]) -> list[dict[str, object]]:
        return [
            {
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir,
                "size": entry.size,
            }
            for entry in entries
        ]

    def read_file_base64(self, path: str) -> str:
        try:
            with open(path, "rb") as handle:
                return base64.b64encode(handle.read()).decode()
        except OSError as exc:
            raise FileServiceError("read_failed", str(exc)) from exc
