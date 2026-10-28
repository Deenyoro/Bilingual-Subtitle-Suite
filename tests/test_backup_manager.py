"""BackupManager only prunes the backups that belong to the file it backs up."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.backup_manager import BackupManager


class BackupLimitTests(unittest.TestCase):
    def test_other_files_backups_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            others = []
            for i, name in enumerate(["Movie.en.srt.bak", "Movie.zh.srt.bak",
                                      "Movie 2.srt.bak", "Movie.ass.bak"]):
                p = d / name
                p.write_text("x")
                old = time.time() - 1000 + i
                os.utime(p, (old, old))
                others.append(p)
            original = d / "Movie.srt"
            original.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n")

            backup = BackupManager(max_backups=1).create_backup(original)

            self.assertEqual(backup, d / "Movie.srt.bak")
            self.assertTrue(backup.exists())
            for p in others:
                self.assertTrue(p.exists(), p.name)

    def test_name_with_brackets(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "Movie [1080p].srt"
            original.write_text("x")
            backup = BackupManager(max_backups=1).create_backup(original)
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
