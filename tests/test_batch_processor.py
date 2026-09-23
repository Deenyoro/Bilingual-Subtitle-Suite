"""Regression tests for batch encoding conversion.

Run with: python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scratch import scratch_dir

from processors.batch_processor import BatchProcessor

SRT_TEXT = (
    "1\n00:00:01,000 --> 00:00:03,000\n我们今天晚上去哪里吃饭？\n\n"
    "2\n00:00:04,000 --> 00:00:06,000\n这个问题我还没有想好。\n\n"
    "3\n00:00:07,000 --> 00:00:09,000\n那就去学校旁边的中国餐馆吧。\n\n"
)


class BatchConvertTests(unittest.TestCase):
    def _make_files(self, directory: Path):
        utf8 = directory / "utf8.srt"
        utf8.write_text(SRT_TEXT, encoding="utf-8")
        gbk = directory / "gbk.srt"
        gbk.write_bytes(SRT_TEXT.encode("gbk"))
        return [utf8, gbk]

    def _run(self, parallel: bool):
        paths = self._make_files(scratch_dir("biss-batch-convert-"))
        results = BatchProcessor(max_workers=2).process_subtitles_batch(
            paths, operation="convert", parallel=parallel)
        converted = [p.read_text(encoding="utf-8") for p in paths]
        return results, converted

    def test_parallel_convert(self):
        # Regression: the parallel path raised NameError (Tuple not imported).
        results, converted = self._run(parallel=True)
        self.assertEqual(results['failed'], 0, results['errors'])
        self.assertEqual(results['successful'], 1)
        self.assertEqual(results['unchanged'], 1)
        self.assertEqual(converted, [SRT_TEXT, SRT_TEXT])

    def test_parallel_matches_sequential(self):
        par, _ = self._run(parallel=True)
        seq, _ = self._run(parallel=False)
        for key in ('total', 'successful', 'unchanged', 'failed'):
            self.assertEqual(par[key], seq[key], key)


if __name__ == "__main__":
    unittest.main()
