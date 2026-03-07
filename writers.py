import csv
from pathlib import Path


class PartWriterTXT:
    def __init__(self, base_stem: str, out_dir: Path):
        self.base_stem = base_stem
        self.out_dir = out_dir
        self.path: Path | None = None
        self.f = None
        self.paths: list[Path] = []

    def _open(self):
        if self.f:
            return
        self.path = self.out_dir / f"{self.base_stem}.txt"
        self.f = self.path.open("w", encoding="utf-8", newline="\n")
        self.paths = [self.path]

    def write_line(self, line: str):
        if self.f is None:
            self._open()
        self.f.write(line + "\n")

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


class PartWriterCSV:
    def __init__(self, base_stem: str, out_dir: Path):
        self.base_stem = base_stem
        self.out_dir = out_dir
        self.path: Path | None = None
        self.f = None
        self.writer = None
        self.paths: list[Path] = []

    def _open(self):
        if self.f:
            return
        self.path = self.out_dir / f"{self.base_stem}.csv"
        self.f = self.path.open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.f)
        self.paths = [self.path]
        self.writer.writerow(["offset_hhmmss", "created_at", "user", "message"])

    def write_row(self, row):
        if self.f is None:
            self._open()
        self.writer.writerow(row)

    def close(self):
        if self.f:
            self.f.close()
            self.f = None