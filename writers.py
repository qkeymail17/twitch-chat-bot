# NOTE:
# PartWriterTXT и PartWriterCSV похожи по структуре.
# Не объединяем пока специально — логика записи различается,
# чтобы не усложнять код перед Этапом 2.
import csv
from pathlib import Path

from config import MAX_PART_BYTES


class PartWriterTXT:
    def __init__(self, base_stem: str, out_dir: Path, max_bytes: int = MAX_PART_BYTES):
        self.base_stem = base_stem
        self.out_dir = out_dir
        self.max_bytes = max_bytes
        self.part_index = 0
        self.f = None
        self.current_path = None
        self.bytes_written = 0
        self.paths: list[Path] = []

    def _open_next(self):
        if self.f:
            self.f.close()
        self.part_index += 1
        self.current_path = self.out_dir / f"{self.base_stem}_part{self.part_index}.txt"
        self.f = self.current_path.open("w", encoding="utf-8", newline="\n")
        self.bytes_written = 0
        self.paths.append(self.current_path)

    def write_line(self, line: str):
        if self.f is None:
            self._open_next()

        encoded = (line + "\n").encode("utf-8")
        if self.bytes_written + len(encoded) > self.max_bytes and self.bytes_written > 0:
            self._open_next()

        self.f.write(line + "\n")
        self.bytes_written += len(encoded)

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


class PartWriterCSV:
    def __init__(self, base_stem: str, out_dir: Path, max_bytes: int = MAX_PART_BYTES):
        self.base_stem = base_stem
        self.out_dir = out_dir
        self.max_bytes = max_bytes
        self.part_index = 0
        self.f = None
        self.current_path = None
        self.bytes_written = 0
        self.paths: list[Path] = []

    def _open_next(self):
        if self.f:
            self.f.close()
        self.part_index += 1
        self.current_path = self.out_dir / f"{self.base_stem}_part{self.part_index}.csv"
        self.f = self.current_path.open("w", encoding="utf-8", newline="")
        self.bytes_written = 0
        self.paths.append(self.current_path)
        self._write_row(["offset_hhmmss", "created_at", "user", "message"])

    def _write_row(self, row):
        from io import StringIO
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(row)
        text = buf.getvalue()
        b = text.encode("utf-8")

        if self.f is None:
            self._open_next()

        if self.bytes_written + len(b) > self.max_bytes and self.bytes_written > 0:
            self._open_next()

        self.f.write(text)
        self.bytes_written += len(b)

    def write_row(self, row):
        if self.f is None:
            self._open_next()
        self._write_row(row)

    def close(self):
        if self.f:
            self.f.close()
            self.f = None