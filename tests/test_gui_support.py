"""Tests for the display-independent GUI helpers (settings, validation, formatting).

Run with: python -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import gui_support as gs


class SettingsTests(unittest.TestCase):
    def setUp(self):
        # Fresh temp folder per test (not removed, so runs can be inspected).
        self.dir = tempfile.mkdtemp(prefix="biss-settings-test-")
        self.path = Path(self.dir) / "gui_settings.json"

    def test_missing_file_gives_defaults(self):
        s = gs.GuiSettings(self.path).load()
        self.assertEqual(s.get("merge.format"), "srt")
        self.assertTrue(s.get("merge.autosync"))

    def test_round_trip(self):
        s = gs.GuiSettings(self.path).load()
        s.set("merge.format", "ass")
        s.remember_path("subtitle", str(Path(self.dir) / "movie.srt"))
        self.assertTrue(s.save())
        again = gs.GuiSettings(self.path).load()
        self.assertEqual(again.get("merge.format"), "ass")
        self.assertEqual(again.last_dir("subtitle"), self.dir)

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("{not json", encoding="utf-8")
        s = gs.GuiSettings(self.path).load()
        self.assertEqual(s.get("merge.format"), "srt")

    def test_old_or_foreign_values_do_not_break_loading(self):
        self.path.write_text(json.dumps({
            "merge": {"format": "ass", "threshold": 1, "autosync": "yes"},
            "shift": "not a dict",
            "future_key": {"kept": True},
        }), encoding="utf-8")
        s = gs.GuiSettings(self.path).load()
        self.assertEqual(s.get("merge.format"), "ass")
        self.assertEqual(s.get("merge.threshold"), 1.0)      # int accepted for float
        self.assertIs(s.get("merge.autosync"), True)         # wrong type -> default
        self.assertEqual(s.get("shift.overwrite"), False)    # bad section -> defaults
        self.assertEqual(s.get("future_key"), {"kept": True})  # unknown keys preserved

    def test_settings_dir_override(self):
        with mock.patch.dict(os.environ, {"BISS_CONFIG_DIR": self.dir}):
            self.assertEqual(gs.settings_dir(), Path(self.dir))

    def test_last_dir_skips_missing_folders(self):
        s = gs.GuiSettings(self.path)
        s.data["dirs"] = {"video": "/definitely/not/here", "subtitle": self.dir}
        self.assertEqual(s.last_dir("video"), self.dir)


class ValidationTests(unittest.TestCase):
    def test_offsets(self):
        cases = {"-2.5s": -2500, "+1500ms": 1500, "1.5 s": 1500, "1.5 seconds": 1500,
                 "-00:00:02,500": -2500, "00:01:00.5": 60500, "0": 0, "-0.5s": -500}
        for text, ms in cases.items():
            self.assertEqual(gs.parse_offset(text), ms, text)

    def test_bad_offsets_have_friendly_messages(self):
        for text in ("", "abc", "1.5 minutes", "2"):
            with self.assertRaises(ValueError) as ctx:
                gs.parse_offset(text)
            self.assertNotIn("could not convert", str(ctx.exception))
        with self.assertRaisesRegex(ValueError, "unit"):
            gs.parse_offset("2")  # bare numbers are ambiguous

    def test_format_offset_round_trips(self):
        for ms in (-1500, 500, 1000, 0, -250):
            self.assertEqual(gs.parse_offset(gs.format_offset(ms)), ms)
        self.assertEqual(gs.format_offset(-1500), "-1.5s")

    def test_threshold(self):
        self.assertEqual(gs.parse_threshold("0.8"), 0.8)
        self.assertEqual(gs.parse_threshold("0,9"), 0.9)
        for bad in ("abc", "", "1.5", "0.1"):
            with self.assertRaises(ValueError):
                gs.parse_threshold(bad)

    def test_timestamp(self):
        self.assertEqual(gs.parse_timestamp("00:00:50,000"), 50.0)
        self.assertAlmostEqual(gs.parse_timestamp("1:02:03.5"), 3723.5)
        with self.assertRaises(ValueError):
            gs.parse_timestamp("50s")


class FormattingTests(unittest.TestCase):
    def test_describe(self):
        info = {"language": "zh", "events": 6, "duration": 19.5, "encoding": "utf_8"}
        self.assertEqual(gs.describe_subtitle(info), "Chinese · 6 lines · 0:19 · UTF-8")
        self.assertIn("Couldn't read", gs.describe_subtitle({"error": "bad"}))
        self.assertEqual(gs.format_duration(3725), "1:02:05")
        self.assertEqual(gs.encoding_name("gb18030"), "GB18030")

    def test_pick_track_for_language(self):
        tracks = [SimpleNamespace(track_id="2", language="eng"),
                  SimpleNamespace(track_id="3", language="jpn"),
                  SimpleNamespace(track_id="4", language="chi"),
                  SimpleNamespace(track_id="5", language="ita")]
        self.assertEqual(gs.pick_track_for_language(tracks, "Japanese"), "3")
        self.assertEqual(gs.pick_track_for_language(tracks, "English"), "2")
        self.assertEqual(gs.pick_track_for_language(tracks, "Other"), "5")
        self.assertIsNone(gs.pick_track_for_language(tracks, "Korean"))
        self.assertIsNone(gs.pick_track_for_language(tracks, "Any"))

    def test_fit_geometry_keeps_window_on_screen(self):
        area = (0, 0, 1366, 728)
        w, h, x, y = gs.fit_geometry(950, 983, None, None, area)
        self.assertLessEqual(h, 728)
        self.assertGreaterEqual(y, 0)
        w, h, x, y = gs.fit_geometry(900, 600, 3000, -50, area)  # saved on a monitor that is gone
        self.assertLessEqual(x + w, 1366)
        self.assertGreaterEqual(y, 0)
        self.assertEqual(gs.parse_geometry("950x750+10+-20"), (950, 750, 10, -20))


class MkvinfoParsingTests(unittest.TestCase):
    def test_parse_tracks(self):
        from ui.gui_support import parse_mkvinfo_tracks
        out = (
            "|+ Tracks\n"
            "| + Track\n"
            "|  + Track number: 1 (track ID for mkvmerge & mkvextract: 0)\n"
            "|  + Track type: video\n"
            "| + Track\n"
            "|  + Track number: 3 (track ID for mkvmerge & mkvextract: 2)\n"
            "|  + Track type: subtitles\n"
            "|  + Codec ID: S_TEXT/UTF8\n"
            "|  + Language: chi\n"
            "|  + Language (IETF BCP 47): zh-Hans\n"
            "|  + Name: Simplified\n")
        tracks = parse_mkvinfo_tracks(out)
        subs = [t for t in tracks if t["type"] == "subtitles"]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["id"], 2)
        self.assertEqual(subs[0]["language"], "zh-Hans")
        self.assertEqual(subs[0]["codec"], "S_TEXT/UTF8")
        self.assertEqual(subs[0]["name"], "Simplified")


if __name__ == "__main__":
    unittest.main()
