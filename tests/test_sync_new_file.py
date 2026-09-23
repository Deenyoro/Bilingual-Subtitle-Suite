"""Shift Timing > Match a video, 'Save as a new file' must never write the
output until the offset is known (regression for the r2 critic finding)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processors.subtitle_sync import SyncResult

SRC = "1\n00:00:05,000 --> 00:00:07,000\nHello.\n\n2\n00:00:10,000 --> 00:00:12,000\nBye.\n\n"
GOOD = "1\n00:00:03,000 --> 00:00:05,000\nHello.\n\n"


class FakeSync:
    def __init__(self, success, offset_ms=0):
        self.success, self.offset_ms = success, offset_ms

    def detect_offset(self, video, srt, track_index=None, track_lang=None):
        return SyncResult(video=video, subtitle=srt, offset_ms=self.offset_ms,
                          shift_applied_ms=-self.offset_ms, match_count=2, total_compared=2,
                          track_used="s:0", success=self.success,
                          message="" if self.success else "No embedded subtitle track")


class SyncToNewFileTests(unittest.TestCase):
    def setUp(self):
        from ui.gui import _sync_to_new_file
        self.run_sync = _sync_to_new_file
        self.tmp = Path(tempfile.mkdtemp(prefix="biss-sync-test-"))
        self.src = self.tmp / "clip.en.srt"
        self.src.write_text(SRC, encoding="utf-8")
        self.target = self.tmp / "clip.en.shifted.srt"
        self.video = self.tmp / "clip.mkv"

    def test_failed_detection_keeps_existing_target(self):
        self.target.write_text(GOOD, encoding="utf-8")
        result = self.run_sync(FakeSync(False), self.video, self.src, self.target, None)
        self.assertFalse(result.success)
        self.assertEqual(self.target.read_text(encoding="utf-8"), GOOD)
        self.assertEqual(self.src.read_text(encoding="utf-8"), SRC)

    def test_failed_detection_creates_no_target(self):
        self.run_sync(FakeSync(False), self.video, self.src, self.target, None)
        self.assertFalse(self.target.exists())

    def test_success_writes_shifted_copy_and_keeps_original(self):
        result = self.run_sync(FakeSync(True, offset_ms=2000), self.video, self.src, self.target, None)
        self.assertTrue(result.success, result.message)
        self.assertIn("00:00:03,000 --> 00:00:05,000", self.target.read_text(encoding="utf-8"))
        self.assertEqual(self.src.read_text(encoding="utf-8"), SRC)

    def test_zero_offset_writes_plain_copy(self):
        result = self.run_sync(FakeSync(True, offset_ms=0), self.video, self.src, self.target, None)
        self.assertTrue(result.success)
        self.assertIn("00:00:05,000", self.target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
