"""GUI smoke tests. They need a display (run under xvfb-run on Linux) and are
skipped otherwise.

Run with: python -m unittest discover -s tests
"""

import contextlib
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scratch import scratch_dir

HAS_DISPLAY = sys.platform in ("win32", "darwin") or bool(os.environ.get("DISPLAY"))
ZH = "1\n00:00:01,000 --> 00:00:03,000\n你好，世界。\n\n2\n00:00:04,000 --> 00:00:06,000\n我们走吧。\n\n"
EN = "1\n00:00:01,000 --> 00:00:03,000\nHello, world.\n\n2\n00:00:04,000 --> 00:00:06,000\nLet's go.\n\n"


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        # Scratch files go to a fresh temp folder (not removed, so runs can be inspected).
        self.tmp = Path(scratch_dir("biss-gui-test-"))
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

    # ---- round 2 ------------------------------------------------------------
    def _two_files(self):
        zh = self.tmp / "Movie.zh.srt"
        en = self.tmp / "Movie.en.srt"
        zh.write_text(ZH, encoding="utf-8")
        en.write_text(EN, encoding="utf-8")
        return zh, en

    def test_dropped_files_are_placed_by_language_without_blocking(self):
        zh, en = self._two_files()
        other = self.tmp / "extra.en.srt"
        other.write_text(EN, encoding="utf-8")
        self.app._on_merge_drop([str(en), str(zh), str(other)])  # wrong order, one too many
        # Placed at once; the language check runs in the background and then swaps.
        self.assertEqual(self.app.chinese_file_var.get(), str(en))
        self.assertTrue(self.pump(lambda: self.app.chinese_file_var.get() == str(zh)))
        self.assertEqual(self.app.english_file_var.get(), str(en))
        self.assertIn("extra.en.srt", self.app._bars["merge"].message.cget("text"))

    def test_merge_asks_before_replacing_and_keeps_file_on_no(self):
        zh, en = self._two_files()
        out = self.tmp / "Movie.zh-en.srt"
        out.write_text("keep me", encoding="utf-8")
        self.app.chinese_source_var.set("external")
        self.app.english_source_var.set("external")
        self.app.chinese_file_var.set(str(zh))
        self.app.english_file_var.set(str(en))
        self.app.merge_autosync_var.set(False)
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            self.app._execute_merge()
            self.assertTrue(self.pump(lambda: not self.app._bars["merge"].busy))
        self.assertTrue(ask.called)
        self.assertEqual(out.read_text(encoding="utf-8"), "keep me")
        self.assertIn("kept", self.app._bars["merge"].message.cget("text"))

    def test_shift_asks_before_replacing_existing_output(self):
        src = self.tmp / "clip.en.srt"
        src.write_text(EN, encoding="utf-8")
        existing = self.tmp / "clip.en.shifted.srt"
        existing.write_text("old", encoding="utf-8")
        self.app.shift_file_var.set(str(src))
        self.app.shift_offset_var.set("+1s")
        with mock.patch("tkinter.messagebox.askyesno", return_value=False):
            self.app._execute_shift()
        self.assertFalse(self.app._bars["shift"].busy)
        self.assertEqual(existing.read_text(encoding="utf-8"), "old")

    def test_language_switch_rebuilds_in_place_and_keeps_input(self):
        from utils.i18n import set_locale
        zh, _en = self._two_files()
        self.app.chinese_source_var.set("external")
        self.app.chinese_file_var.set(str(zh))
        self.app.shift_offset_var.set("-2s")
        self.app._select_tab("shift")
        try:
            self.app._locale_var.set("zh")
            self.app._change_language()
            self.pump(timeout=0.2)
            self.assertEqual(self.app.notebook.tab(self.app._tabs["merge"], "text"), "合并")
            self.assertEqual(self.app.merge_btn.cget("text"), "合并字幕")
            self.assertEqual(self.app.chinese_file_var.get(), str(zh))
            self.assertEqual(self.app.shift_offset_var.get(), "-2s")
            self.assertEqual(self.app._current_tab_key(), "shift")
            self.assertEqual(self.app.chinese_auto_lang_var.get(), "中文")
        finally:
            set_locale("en")

    def test_convert_hint_follows_the_chosen_file(self):
        sub = self.tmp / "legacy.zh.srt"
        sub.write_bytes(ZH.encode("gb18030"))
        self.app._select_tab("convert")
        self.app.convert_file_var.set(str(sub))
        self.assertTrue(self.pump(lambda: "legacy.zh.srt" in self.app._bars["convert"].message.cget("text")))
        self.assertIn("Ready to convert", self.app._bars["convert"].message.cget("text"))

    def test_status_bar_shows_the_open_tabs_status(self):
        self.app._set_status("✔ Saved Movie.zh-en.srt", "merge")
        self.app._select_tab("shift")
        self.pump(timeout=0.1)
        self.assertEqual(self.app.status_var.get(), "Ready")
        self.app._select_tab("merge")
        self.pump(timeout=0.1)
        self.assertEqual(self.app.status_var.get(), "✔ Saved Movie.zh-en.srt")

    def test_long_path_entry_shows_the_file_name(self):
        deep = self.tmp / ("a-very-long-folder-name-" * 6) / "Episode.S01E07.zh.srt"
        deep.parent.mkdir(parents=True)
        deep.write_text(ZH, encoding="utf-8")
        self.app._select_tab("split")
        self.app.root.geometry("950x697+0+0")
        self.app.split_file_var.set(str(deep))
        self.pump(timeout=0.3)
        entry = self.app._drop_rows[[str(e.cget("textvariable")) for e, _ in self.app._drop_rows].index(
            str(self.app.split_file_var))][0]
        self.assertGreater(entry.xview()[0], 0.0)
        self.assertEqual(entry.xview()[1], 1.0)

    def test_explorer_drop_goes_through_tkdnd_binding(self):
        if not self.app._dnd:
            self.skipTest(f"tkdnd not loadable here: {self.app._dnd_error}")
        zh, en = self._two_files()
        root = self.app.root
        script = str(root.tk.call("bind", self.app.merge_drop_zone._w, "<<Drop>>"))
        data = " ".join(f"{{{p}}}" for p in (en, zh))  # a Tcl list, as tkdnd substitutes for %D
        self.assertEqual(root.tk.eval(script.replace("%D", "{" + data + "}")), "copy")
        self.assertTrue(self.pump(lambda: self.app.chinese_file_var.get() == str(zh)))
        self.assertEqual(self.app.english_file_var.get(), str(en))


if __name__ == "__main__":
    unittest.main()
