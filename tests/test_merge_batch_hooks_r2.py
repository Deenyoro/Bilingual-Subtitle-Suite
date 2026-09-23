"""Regression tests for the processor hooks the GUI uses: asking before an
existing merged file is replaced, and per-file batch results.

Run with: python -m unittest discover -s tests
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from processors.batch_processor import BatchProcessor
from processors.merger import BilingualMerger, MergeCancelled, OverwriteDeclined

ZH = "1\n00:00:01,000 --> 00:00:03,000\n你好，世界。\n\n2\n00:00:04,000 --> 00:00:06,000\n我们走吧。\n\n"
EN = "1\n00:00:01,000 --> 00:00:03,000\nHello, world.\n\n2\n00:00:04,000 --> 00:00:06,000\nLet's go.\n\n"


class MergeOverwriteTests(unittest.TestCase):
    """The GUI asks before replacing an existing merged file; the CLI keeps overwriting."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="biss-r2-merge-"))
        self.zh = self.dir / "Movie.zh.srt"
        self.en = self.dir / "Movie.en.srt"
        self.zh.write_text(ZH, encoding="utf-8")
        self.en.write_text(EN, encoding="utf-8")
        self.out = self.dir / "Movie.zh-en.srt"
        self.out.write_text("keep me", encoding="utf-8")

    def _merge(self, **kw):
        merger = BilingualMerger(enable_mixed_realignment=False, **kw)
        return merger, merger.merge_subtitle_files(self.zh, self.en, None, "srt")

    def test_declined_keeps_the_existing_file(self):
        asked = []
        with self.assertRaises(OverwriteDeclined) as ctx:
            self._merge(confirm_overwrite=lambda p: asked.append(p.name) or False)
        self.assertIsInstance(ctx.exception, MergeCancelled)
        self.assertEqual(asked, ["Movie.zh-en.srt"])
        self.assertEqual(self.out.read_text(encoding="utf-8"), "keep me")

    def test_accepted_replaces(self):
        _merger, ok = self._merge(confirm_overwrite=lambda p: True)
        self.assertTrue(ok)
        self.assertIn("Hello, world.", self.out.read_text(encoding="utf-8"))

    def test_default_overwrites_without_asking(self):
        _merger, ok = self._merge()
        self.assertTrue(ok)
        self.assertIn("你好", self.out.read_text(encoding="utf-8"))


class BatchPerFileResultTests(unittest.TestCase):
    """The Batch tab lists each file as soon as it is done, with the reason for failures."""

    def test_convert_reports_each_file(self):
        folder = Path(tempfile.mkdtemp(prefix="biss-r2-batch-"))
        good = folder / "a.zh.srt"
        good.write_bytes(ZH.encode("gb18030"))
        fine = folder / "b.en.srt"
        fine.write_text(EN, encoding="utf-8")
        bad = folder / "c.srt"
        bad.write_text(EN, encoding="utf-8")
        seen = []
        bp = BatchProcessor(auto_confirm=True)
        real = bp.converter.convert_file

        def convert(path, **kw):
            if path.name == "c.srt":
                raise OSError("disk full")
            return real(path, **kw)

        with mock.patch.object(bp.converter, "convert_file", side_effect=convert):
            results = bp.process_subtitles_batch([good, fine, bad], operation="convert", parallel=False,
                                                 file_result_callback=lambda p, s, e: seen.append((p.name, s, e)),
                                                 keep_backup=False)
        self.assertEqual(seen, [("a.zh.srt", "converted", None), ("b.en.srt", "unchanged", None),
                                ("c.srt", "failed", "disk full")])
        self.assertEqual(results["failed"], 1)

    def test_parallel_convert_reports_each_file(self):
        folder = Path(tempfile.mkdtemp(prefix="biss-r2-batch-"))
        files = []
        for i in range(3):
            f = folder / f"f{i}.en.srt"
            f.write_text(EN, encoding="utf-8")
            files.append(f)
        seen = []
        lock = threading.Lock()

        def record(p, s, e):
            with lock:
                seen.append(p.name)

        BatchProcessor(auto_confirm=True).process_subtitles_batch(files, operation="convert", parallel=True,
                                                                  file_result_callback=record)
        self.assertEqual(sorted(seen), ["f0.en.srt", "f1.en.srt", "f2.en.srt"])

    def test_directory_merge_reports_each_video(self):
        folder = Path(tempfile.mkdtemp(prefix="biss-r2-batch-"))
        for name in ("A.mkv", "B.mkv", "C.mkv"):
            (folder / name).write_bytes(b"x")
        bp = BatchProcessor(auto_confirm=False)
        bp._process_single_video = lambda video, *a, **kw: video.name == "A.mkv"
        seen = []
        with mock.patch("core.video_containers.VideoContainerHandler.list_subtitle_tracks", return_value=[]):
            bp.process_directory_interactive(
                folder, pattern="*", video_only=True,
                confirm_callback=lambda v, i, n: "n" if v.name == "C.mkv" else "y",
                result_callback=lambda v, s: seen.append((v.name, s)))
        self.assertEqual(seen, [("A.mkv", "merged"), ("B.mkv", "failed"), ("C.mkv", "skipped")])



if __name__ == "__main__":
    unittest.main()
