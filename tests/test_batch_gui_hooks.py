"""Regression tests for the batch hooks the GUI relies on.

Run with: python -m unittest discover -s tests
"""

import builtins
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processors.batch_processor import BatchProcessor

SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"


def _no_input(*_a, **_kw):
    raise AssertionError("input() must not be called from the GUI code path")


class DirectoryMergeHooksTests(unittest.TestCase):
    """process_directory_interactive must be usable from a GUI (no console)."""

    def setUp(self):
        # Fresh temp folder per test (not removed, so runs can be inspected).
        root = Path(tempfile.mkdtemp(prefix="biss-batch-test-"))
        (root / "sub").mkdir()
        for rel in ("A.mkv", "notes.txt", "A.en.srt", "sub/B.mp4"):
            (root / rel).write_bytes(b"x")
        self.root = root
        patcher = mock.patch("core.video_containers.VideoContainerHandler.list_subtitle_tracks",
                             return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _processor(self, processed):
        bp = BatchProcessor(auto_confirm=False)

        def fake_single(video_file, *_a, **_kw):
            processed.append(video_file.name)
            return True

        bp._process_single_video = fake_single
        return bp

    def test_confirm_callback_replaces_input_and_filters_videos(self):
        processed, asked, progress = [], [], []
        bp = self._processor(processed)
        with mock.patch.object(builtins, "input", _no_input):
            results = bp.process_directory_interactive(
                self.root, pattern="*", recursive=True, video_only=True,
                confirm_callback=lambda v, i, n: asked.append((v.name, i, n)) or "y",
                progress_callback=lambda i, n, v: progress.append((i, n, v.name if v else None)))
        # Only the two videos are counted: no .txt/.srt, and the subfolder is included.
        self.assertEqual(results["total"], 2)
        self.assertEqual(results["successful"], 2)
        self.assertEqual(sorted(processed), ["A.mkv", "B.mp4"])
        self.assertEqual([a[1:] for a in asked], [(1, 2), (2, 2)])
        self.assertEqual(progress[-1], (2, 2, None))

    def test_skip_and_quit_answers(self):
        processed = []
        bp = self._processor(processed)
        answers = iter(["n", "q"])
        with mock.patch.object(builtins, "input", _no_input):
            results = bp.process_directory_interactive(
                self.root, pattern="*", recursive=True, video_only=True,
                confirm_callback=lambda *a: next(answers))
        self.assertEqual(results["skipped"], 1)
        self.assertEqual(results["successful"], 0)
        self.assertEqual(processed, [])

    def test_cancel_event_stops_before_next_file(self):
        processed = []
        bp = self._processor(processed)
        cancel = threading.Event()

        def confirm(video, index, total):
            cancel.set()  # user pressed Cancel while the first file was being asked about
            return "y"

        results = bp.process_directory_interactive(
            self.root, pattern="*", recursive=True, video_only=True,
            confirm_callback=confirm, cancel_event=cancel)
        self.assertTrue(results.get("cancelled"))
        self.assertEqual(len(processed), 1)

    def test_cli_defaults_unchanged(self):
        """Without the new keywords the old behaviour (glob, non-recursive, input()) is kept."""
        processed = []
        bp = self._processor(processed)
        with mock.patch.object(builtins, "input", return_value="y") as fake_input:
            results = bp.process_directory_interactive(self.root, pattern="*.mkv")
        self.assertEqual(results["total"], 1)
        self.assertEqual(fake_input.call_count, 1)


class BatchConvertHooksTests(unittest.TestCase):
    def _files(self, root: Path, n=3):
        paths = []
        for i in range(n):
            p = root / f"f{i}.srt"
            p.write_bytes(SRT.encode("utf-16"))
            paths.append(p)
        return paths

    def test_progress_callback_sequential(self):
        paths = self._files(Path(tempfile.mkdtemp(prefix="biss-batch-test-")))
        seen = []
        results = BatchProcessor().process_subtitles_batch(
            paths, parallel=False, progress_callback=lambda d, t, p: seen.append((d, t)))
        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(results["failed"], 0, results["errors"])

    def test_cancel_sequential(self):
        paths = self._files(Path(tempfile.mkdtemp(prefix="biss-batch-test-")))
        cancel = threading.Event()
        results = BatchProcessor().process_subtitles_batch(
            paths, parallel=False, cancel_event=cancel,
            progress_callback=lambda d, t, p: cancel.set())
        self.assertTrue(results.get("cancelled"))
        self.assertEqual(results["successful"] + results["unchanged"] + results["failed"], 1)


if __name__ == "__main__":
    unittest.main()
