"""Regression tests for the GUI's translations and Explorer drop parsing
(no display needed).

Run with: python -m unittest discover -s tests
"""

import json
import re
import sys
import tkinter
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _flatten(obj, prefix=""):
    out = {}
    for key, value in obj.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, full))
        else:
            out[full] = value
    return out


def _locale(lang):
    return _flatten(json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8")))


class TranslationTests(unittest.TestCase):
    """Every string the GUI shows must exist in every language (no mixed-language UI)."""

    def test_every_gui_key_exists_in_english(self):
        en = _locale("en")
        used = set()
        for path in (ROOT / "ui").glob("*.py"):
            used |= set(re.findall(r"""\bt\(\s*["']((?:ui|gui|app)\.[\w.]+)["']""", path.read_text(encoding="utf-8")))
        self.assertGreater(len(used), 300)
        self.assertEqual(sorted(k for k in used if k not in en), [])

    def test_all_languages_have_the_same_ui_keys_and_placeholders(self):
        en = {k: v for k, v in _locale("en").items() if k.startswith("ui.")}
        fields = re.compile(r"{(\w+)}")
        for lang in ("zh", "ja", "ko"):
            other = {k: v for k, v in _locale(lang).items() if k.startswith("ui.")}
            self.assertEqual(set(other), set(en), lang)
            for key, text in en.items():
                self.assertEqual(set(fields.findall(other[key])), set(fields.findall(text)), f"{lang}:{key}")
                if key not in ("ui.batch.progress", "ui.batch.sum_sep", "ui.common.and") and len(text) > 12:
                    self.assertNotEqual(other[key], text, f"{lang}:{key} is not translated")

    def test_language_switch_translates_shared_helpers(self):
        from ui import gui_support as gs
        from utils.i18n import get_locale, set_locale
        before = get_locale()
        try:
            set_locale("zh")
            self.assertEqual(gs.describe_subtitle({"language": "zh", "events": 6, "duration": 19,
                                                   "encoding": "utf-8"}), "中文 · 6 行 · 0:19 · UTF-8")
            with self.assertRaises(ValueError) as ctx:
                gs.parse_offset("2")
            self.assertIn("2ms", str(ctx.exception))
        finally:
            set_locale(before)


class DropParsingTests(unittest.TestCase):
    def test_paths_with_spaces_and_uris(self):
        from ui.gui import parse_drop_data
        interp = tkinter.Tcl()
        paths = parse_drop_data(interp, "{/home/me/My Films/Movie.zh.srt} /home/me/Movie.en.srt "
                                        "file:///home/me/A%20B.mkv")
        self.assertEqual([Path(p).name for p in paths], ["Movie.zh.srt", "Movie.en.srt", "A B.mkv"])


if __name__ == "__main__":
    unittest.main()
