"""Regression tests: the merged file puts on top exactly the track the window
says is on top ("On top: Track 1 | Track 2"), also after Swap Tracks and for
languages the old CJK check missed (kana-only Japanese, Hangul-only Korean).

GUI tests need a display (run under xvfb-run on Linux) and are skipped otherwise.
Run with: python -m unittest discover -s tests
"""

import contextlib
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scratch import scratch_dir

from processors.merger import BilingualMerger

HAS_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))


def srt(*lines: str) -> str:
    return "".join(f"{i}\n00:00:0{2 * i - 1},000 --> 00:00:0{2 * i},500\n{text}\n\n"
                   for i, text in enumerate(lines, 1))


ZH = srt("你好，世界。", "我们走吧。")
EN = srt("Hello, world.", "Let's go.")
KO = srt("안녕하세요.", "가자.")
JA = srt("こんにちは。", "いこう。")
FR = srt("Bonjour le monde.", "On y va.")


def first_cue_lines(path: Path) -> list[str]:
    block = path.read_text(encoding="utf-8-sig").strip().split("\n\n")[0]
    return block.splitlines()[2:]


class SlotOrderTests(unittest.TestCase):
    """BilingualMerger(order="slots"): 'first' is Track 1, 'second' is Track 2."""

    def setUp(self):
        self.dir = scratch_dir("biss-r4-order-")

    def _merge(self, track1: str, track2: str, top: str, **kw) -> list[str]:
        a = self.dir / "a.srt"
        b = self.dir / "b.srt"
        a.write_text(track1, encoding="utf-8")
        b.write_text(track2, encoding="utf-8")
        out = self.dir / f"out-{len(list(self.dir.iterdir()))}.srt"
        merger = BilingualMerger(top_language=top, order="slots", **kw)
        self.assertTrue(merger.merge_subtitle_files(a, b, out, "srt"))
        return first_cue_lines(out)

    def test_every_language_pair_follows_the_chosen_track(self):
        pairs = [(ZH, EN), (EN, ZH), (KO, EN), (EN, KO), (JA, EN), (EN, JA), (FR, EN), (ZH, JA)]
        for realign in (False, True):
            for t1, t2 in pairs:
                first1 = t1.splitlines()[2]
                first2 = t2.splitlines()[2]
                with self.subTest(t1=first1, t2=first2, realign=realign):
                    self.assertEqual(self._merge(t1, t2, "first", enable_mixed_realignment=realign),
                                     [first1, first2])
                    self.assertEqual(self._merge(t1, t2, "second", enable_mixed_realignment=realign),
                                     [first2, first1])

    def test_default_order_is_unchanged_for_the_cli(self):
        self.assertEqual(BilingualMerger().order, "language")
        with self.assertRaises(ValueError):
            BilingualMerger(order="sideways")


class _GuiCase(unittest.TestCase):
    """Shared set-up: a fresh window with a Chinese and an English subtitle file."""

    def setUp(self):
        self.tmp = scratch_dir("biss-gui-r4-order-")
        env = mock.patch.dict(os.environ, {"BISS_CONFIG_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        from ui.gui import BISSGui
        self.app = BISSGui()
        self.addCleanup(self._destroy)
        self.pump(lambda: self.app._env_checked)
        self.zh = self.tmp / "Movie.zh.srt"
        self.en = self.tmp / "Movie.en.srt"
        self.zh.write_text(ZH, encoding="utf-8")
        self.en.write_text(EN, encoding="utf-8")
        self.out = self.tmp / "merged.srt"

    def _destroy(self):
        import tkinter as tk
        self.app._stop_pump()
        with contextlib.suppress(tk.TclError):
            self.app.root.destroy()

    def pump(self, until=None, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            self.app.root.update()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return until is None

    def _set_tracks(self, track1: Path, track2: Path):
        for slot, path in (("chinese", track1), ("english", track2)):
            getattr(self.app, f"{slot}_source_var").set("external")
            getattr(self.app, f"{slot}_file_var").set(str(path))
        self.app._update_chinese_source()
        self.app._update_english_source()
        self.app.merge_output_var.set(str(self.out))

    def _merge(self) -> list[str]:
        self.app._execute_merge()
        self.assertTrue(self.pump(lambda: not self.app._bars["merge"].busy))
        self.assertIn("merged.srt", self.app._bars["merge"].message.cget("text"))
        return first_cue_lines(self.out)


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class GuiMergeOrderTests(_GuiCase):
    def test_swap_then_merge_puts_track_1_on_top(self):
        self._set_tracks(self.zh, self.en)
        self.app._swap_merge_files()
        self.assertEqual(self.app.chinese_file_var.get(), str(self.en))
        self.app.merge_top_var.set("first")
        self.assertEqual(self._merge(), ["Hello, world.", "你好，世界。"])
        self.app.merge_top_var.set("second")
        with mock.patch.object(self.app, "_confirm_replace", return_value=True):
            self.assertEqual(self._merge(), ["你好，世界。", "Hello, world."])

    def test_language_check_cannot_swap_tracks_while_replace_dialog_is_open(self):
        self.out.write_text("old", encoding="utf-8")
        self._set_tracks(self.en, self.zh)
        self.app.merge_top_var.set("first")
        release = threading.Event()

        def slow_detect(path):
            release.wait(5)
            return "Chinese" if path == self.zh else "English"

        def replace_dialog(_target):
            # While the modal dialog is up, the language check finishes and Tk keeps
            # processing events, like a real dialog does.
            release.set()
            self.pump(timeout=0.5)
            return True

        with mock.patch.object(self.app, "_detect_file_language", side_effect=slow_detect), \
                mock.patch.object(self.app, "_confirm_replace", side_effect=replace_dialog):
            self.app._order_tracks_by_language([str(self.en), str(self.zh)])
            lines = self._merge()
        self.assertEqual(self.app.chinese_file_var.get(), str(self.en))
        self.assertEqual(lines, ["Hello, world.", "你好，世界。"])

    def test_status_bar_names_the_folder_not_the_same_result_again(self):
        self._set_tracks(self.zh, self.en)
        self.app._select_tab("merge")
        self._merge()
        self.assertIn("Saved merged.srt", self.app._bars["merge"].message.cget("text"))
        status = self.app.status_var.get()
        self.assertNotIn("merged.srt", status)
        self.assertIn(str(self.tmp), status)


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class GuiFfmpegGuidanceTests(_GuiCase):
    """Every screen that needs FFmpeg says so before the user clicks Start."""

    def test_batch_merge_from_videos_shows_the_ffmpeg_note(self):
        self.app._select_tab("batch")
        self.app.batch_dir_var.set(str(self.tmp))
        self.app._apply_environment(["ffmpeg"], [], False)
        self.app.batch_op_var.set("convert")
        self.app._update_batch_options()
        self.assertFalse(self.app.batch_banner.visible)
        self.app.batch_op_var.set("merge")
        self.app._update_batch_options()
        bar = self.app._bars["batch"]
        self.assertTrue(self.app.batch_banner.visible)
        self.assertTrue(self.app.batch_banner.buttons.winfo_children())
        self.assertEqual(bar.icon.cget("text"), "⚠")
        self.assertIn("FFmpeg", bar.message.cget("text"))
        self.app._apply_environment([], [], False)
        self.assertFalse(self.app.batch_banner.visible)
        self.assertIn("Click Start", bar.message.cget("text"))

    def test_convert_sync_button_is_disabled_without_ffmpeg(self):
        video = self.tmp / "clip.mkv"
        video.write_bytes(b"\0")
        self.app._select_tab("convert")
        self.app.convert_file_var.set(str(self.en))
        self.app.convert_type_var.set("sync")
        self.app._update_convert_type()
        self.app.sync_video_var.set(str(video))
        self.app._apply_environment(["ffmpeg"], [], False)
        self.assertTrue(self.app._bars["convert"].button.instate(["disabled"]))
        self.app._apply_environment([], [], False)
        self.assertFalse(self.app._bars["convert"].button.instate(["disabled"]))
        self.app.convert_type_var.set("encoding")
        self.app._apply_environment(["ffmpeg"], [], False)
        self.app._update_convert_type()
        self.assertFalse(self.app._bars["convert"].button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
