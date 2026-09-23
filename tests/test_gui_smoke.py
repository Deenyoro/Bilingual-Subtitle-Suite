"""GUI smoke tests. They need a display (run under xvfb-run on Linux) and are
skipped otherwise.

Run with: python -m unittest discover -s tests
"""

import contextlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAS_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))
ZH = "1\n00:00:01,000 --> 00:00:03,000\n你好，世界。\n\n2\n00:00:04,000 --> 00:00:06,000\n我们走吧。\n\n"
EN = "1\n00:00:01,000 --> 00:00:03,000\nHello, world.\n\n2\n00:00:04,000 --> 00:00:06,000\nLet's go.\n\n"


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        # Scratch files go to a fresh temp folder (not removed, so runs can be inspected).
        self.tmp = Path(tempfile.mkdtemp(prefix="biss-gui-test-"))
        env = mock.patch.dict(os.environ, {"BISS_CONFIG_DIR": str(self.tmp / "cfg")})
        env.start()
        self.addCleanup(env.stop)
        from ui.gui import BISSGui
        self.app = BISSGui()
        self.addCleanup(self._destroy)

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

    def test_tools_menu_selects_matching_tab(self):
        # Regression: menu entries were off by one after the Split tab was added.
        for key in ("merge", "extract", "split", "shift", "convert", "batch"):
            self.app._select_tab("merge")
            self.app._select_tab(key)
            self.assertEqual(self.app._current_tab_key(), key)

    def test_primary_button_visible_at_1366x768(self):
        self.app.root.geometry("950x697+0+0")
        self.pump(timeout=0.3)
        for key, bar in self.app._bars.items():
            self.app._select_tab(key)
            self.pump(timeout=0.1)
            btn = bar.button
            bottom = btn.winfo_rooty() + btn.winfo_height()
            win_bottom = self.app.root.winfo_rooty() + self.app.root.winfo_height()
            self.assertTrue(btn.winfo_ismapped(), key)
            self.assertLessEqual(bottom, win_bottom, key)

    def test_bad_threshold_is_reported_inline(self):
        self.app.merge_threshold_var.set("abc")
        self.app.chinese_source_var.set("external")
        self.app.english_source_var.set("external")
        zh = self.tmp / "a.zh.srt"
        en = self.tmp / "a.en.srt"
        zh.write_text(ZH, encoding="utf-8")
        en.write_text(EN, encoding="utf-8")
        self.app.chinese_file_var.set(str(zh))
        self.app.english_file_var.set(str(en))
        self.app._execute_merge()
        self.assertIn("Match strictness", self.app._bars["merge"].message.cget("text"))
        self.assertFalse(self.app._bars["merge"].busy)

    def test_merge_runs_off_the_ui_thread_and_reports_output(self):
        zh = self.tmp / "Movie.zh.srt"
        en = self.tmp / "Movie.en.srt"
        zh.write_text(ZH, encoding="utf-8")
        en.write_text(EN, encoding="utf-8")
        self.app.chinese_source_var.set("external")
        self.app.english_source_var.set("external")
        self.app.chinese_file_var.set(str(zh))
        self.app.english_file_var.set(str(en))
        self.app.merge_autosync_var.set(False)
        self.app._execute_merge()
        self.assertTrue(self.app._bars["merge"].busy)  # returned at once; work is on a thread
        self.assertTrue(self.pump(lambda: not self.app._bars["merge"].busy))
        text = self.app._bars["merge"].message.cget("text")
        self.assertIn("Saved Movie.zh-en.srt", text)
        self.assertTrue((self.tmp / "Movie.zh-en.srt").exists())

    def test_shift_defaults_to_new_file_and_needs_offset(self):
        src = self.tmp / "clip.en.srt"
        src.write_text(EN, encoding="utf-8")
        self.app.shift_file_var.set(str(src))
        self.pump(timeout=0.2)
        self.assertTrue(self.app.shift_output_var.get().endswith("clip.en.shifted.srt"))
        self.assertTrue(self.app.shift_btn.instate(["disabled"]))  # no offset yet
        self.app._nudge_offset("-1s")
        self.app._nudge_offset("-0.5s")
        self.assertEqual(self.app.shift_offset_var.get(), "-1.5s")
        self.assertTrue(self.app.shift_btn.instate(["!disabled"]))
        self.app._execute_shift()
        self.assertTrue(self.pump(lambda: not self.app._bars["shift"].busy))
        self.assertEqual(src.read_text(encoding="utf-8"), EN)  # original untouched
        self.assertTrue((self.tmp / "clip.en.shifted.srt").exists())

    def test_settings_saved_on_close(self):
        self.app.merge_format_var.set("ass")
        self.app._select_tab("shift")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            self.app._on_close()
        cfg = self.tmp / "cfg" / "gui_settings.json"
        self.assertTrue(cfg.exists())
        import json
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertEqual(data["merge"]["format"], "ass")
        self.assertEqual(data["last_tab"], "shift")


if __name__ == "__main__":
    unittest.main()
