"""Regression tests for status/action-bar consistency, FFmpeg guidance on the
sync controls, batch result wording and batch backups.

GUI tests need a display (run under xvfb-run on Linux) and are skipped otherwise.
Run with: python -m unittest discover -s tests
"""

import contextlib
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import gui_support as gs

HAS_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))
EN = "1\n00:00:01,000 --> 00:00:03,000\nHello, world.\n\n"


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


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class GuiConsistencyTests(unittest.TestCase):
    def setUp(self):
        # Scratch files go to a fresh temp folder (not removed, so runs can be inspected).
        self.tmp = Path(tempfile.mkdtemp(prefix="biss-gui-r3-test-"))
        env = mock.patch.dict(os.environ, {"BISS_CONFIG_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        from ui.gui import BISSGui
        self.app = BISSGui()
        self.addCleanup(self._destroy)
        # Wait for the start-up tool check so it cannot overwrite what a test sets.
        self.pump(lambda: self.app._env_checked)

    def _destroy(self):
        import tkinter as tk
        self.app._stop_pump()
        with contextlib.suppress(tk.TclError):  # already closed by the test
            self.app.root.destroy()

    def pump(self, until=None, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            self.app.root.update()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return until is None

    def test_status_bar_drops_saved_once_the_action_bar_moves_on(self):
        self.app._select_tab("merge")
        bar = self.app._bars["merge"]
        bar.finish("success", "Saved Movie.zh-en.srt")
        self.app._set_status("✔ Saved Movie.zh-en.srt", "merge")
        self.assertEqual(self.app.status_var.get(), "✔ Saved Movie.zh-en.srt")
        bar.set_hint("Ready. Will save Movie.zh-en.srt")  # the user changed an input
        self.assertEqual(self.app.status_var.get(), "Ready")

    def test_background_recheck_keeps_result_and_status(self):
        self.app._select_tab("shift")
        bar = self.app._bars["shift"]
        bar.finish("success", "Saved offset.en.shifted.srt")
        self.app._set_status("✔ Saved offset.en.shifted.srt", "shift")
        self.app._validate_shift(keep_result=True)
        self.assertTrue(bar.showing_result)
        self.assertEqual(self.app.status_var.get(), "✔ Saved offset.en.shifted.srt")

    def test_sync_controls_explain_and_disable_without_ffmpeg(self):
        self.app._apply_environment(["ffmpeg", "ffprobe"], [], False)
        self.pump(timeout=0.1)
        self.assertEqual(set(self.app._sync_ffmpeg_ui), {"shift", "convert"})
        for banner, buttons in self.app._sync_ffmpeg_ui.values():
            self.assertTrue(banner.visible)
            self.assertTrue(banner.buttons.winfo_children(), "banner offers Check again / Locate / Download")
            for btn in buttons:
                self.assertTrue(btn.instate(["disabled"]))
        self.app._apply_environment([], [], False)
        for banner, buttons in self.app._sync_ffmpeg_ui.values():
            self.assertFalse(banner.visible)
            for btn in buttons:
                self.assertFalse(btn.instate(["disabled"]))

    def test_convert_sync_banner_does_not_cover_the_note(self):
        banner, _ = self.app._sync_ffmpeg_ui["convert"]
        rows = [int(w.grid_info()["row"]) for w in self.app.sync_options_frame.grid_slaves()
                if w is not banner]
        self.assertNotIn(3, rows)

    def test_match_video_without_ffmpeg_is_a_warning(self):
        sub = self.tmp / "clip.en.srt"
        sub.write_text(EN, encoding="utf-8")
        video = self.tmp / "clip.mkv"
        video.write_bytes(b"\0")
        self.app._apply_environment(["ffmpeg"], [], False)
        self.app._select_tab("shift")
        self.app.shift_file_var.set(str(sub))
        self.app.shift_mode_var.set("video")
        self.app._update_shift_mode()
        self.app.sync_video_var.set(str(video))
        bar = self.app._bars["shift"]
        self.assertTrue(bar.button.instate(["disabled"]))
        self.assertEqual(bar.icon.cget("text"), "⚠")

    def test_language_check_never_reorders_a_running_merge(self):
        zh = self.tmp / "b.srt"
        en = self.tmp / "a.srt"
        release = threading.Event()

        def slow_detect(path):
            release.wait(5)
            return "Chinese" if path.name == "b.srt" else "English"

        self.app.chinese_file_var.set(str(en))
        self.app.english_file_var.set(str(zh))
        with mock.patch.object(self.app, "_detect_file_language", side_effect=slow_detect):
            self.app._order_tracks_by_language([str(en), str(zh)])
            self.app._bars["merge"].start("Merging…")  # the user clicked Merge meanwhile
            release.set()
            self.pump(timeout=0.5)
        self.app._bars["merge"].finish("cancelled", "Merge stopped")
        self.assertEqual(self.app.chinese_file_var.get(), str(en))
        self.assertEqual(self.app.english_file_var.get(), str(zh))


if __name__ == "__main__":
    unittest.main()
