"""Regression tests for batch result wording and batch backups.

Run with: python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import gui_support as gs


class BatchHelperTests(unittest.TestCase):
    def test_backup_copies_are_not_converted_again(self):
        root = Path("/videos")
        files = [root / "E01.srt",
                 root / "subtitle_backups" / "E01_20260923_073856.srt",
                 root / "S1" / "E02.srt",
                 root / "S1" / "subtitle_backups" / "E02_20260923_073856.srt"]
        self.assertEqual(gs.without_backup_copies(files, root), [root / "E01.srt", root / "S1" / "E02.srt"])

    def test_choosing_the_backup_folder_itself_still_works(self):
        root = Path("/videos/subtitle_backups")
        files = [root / "E01_20260923_073856.srt"]
        self.assertEqual(gs.without_backup_copies(files, root), files)

    def test_failure_reason_names_missing_ffmpeg(self):
        with mock.patch.object(gs, "t", side_effect=lambda key, **kw: key):
            self.assertEqual(gs.batch_failure_reason("❌ No Chinese or English subtitles found!", True),
                             "ui.batch.r_no_ffmpeg")
            self.assertEqual(gs.batch_failure_reason(None, True), "ui.batch.r_no_ffmpeg")
            self.assertEqual(gs.batch_failure_reason("No Chinese or English subtitles found!", False),
                             "ui.batch.r_no_subs")
            self.assertEqual(gs.batch_failure_reason("", False), "ui.batch.r_failed")
            self.assertEqual(gs.batch_failure_reason("✗ disk full", True), "ui.batch.r_failed_why")

    def test_failure_reason_keeps_other_errors_readable(self):
        text = gs.batch_failure_reason("❌ disk full")
        self.assertIn("disk full", text)
        self.assertNotIn("❌", text)


if __name__ == "__main__":
    unittest.main()
