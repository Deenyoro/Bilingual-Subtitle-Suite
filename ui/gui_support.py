"""
Display-independent helpers for the Tkinter GUI.

Everything here can be imported and unit-tested without a display:
settings persistence, input validation, formatting of file facts,
external-tool discovery and "open folder" helpers.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from utils.i18n import t
from utils.logging_config import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

SETTINGS_FILENAME = "gui_settings.json"
SETTINGS_VERSION = 1

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": SETTINGS_VERSION,
    "geometry": "",           # "WxH+X+Y" of the last normal-state window
    "zoomed": False,          # window was maximized when closed
    "last_tab": "merge",
    "locale": "",             # "" = follow --lang / system locale
    "details_open": False,    # the Details (log) pane
    "dirs": {},               # last folder per dialog kind
    "tool_dirs": [],          # extra folders searched for ffmpeg/mkvtoolnix
    "merge": {
        "format": "srt",
        "top": "first",
        "autosync": True,
        "autoalign": False,
        "threshold": 0.8,
        "advanced_open": False,
    },
    "shift": {"overwrite": False, "backup": True},
    "convert": {"encoding": "utf-8", "backup": True, "fix_fonts": True},
    "split": {"format": "ass", "strip": True},
    "batch": {"op": "convert", "recursive": True, "backup": True, "autoconfirm": False},
}


def settings_dir() -> Path:
    """Folder that holds gui_settings.json.

    Windows: %APPDATA%\\BISS.  Elsewhere: $XDG_CONFIG_HOME/biss (~/.config/biss).
    BISS_CONFIG_DIR overrides both (portable installs, tests).
    """
    override = os.environ.get("BISS_CONFIG_DIR", "").strip()
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "BISS"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "biss"


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    """Overlay loaded values on defaults, keeping unknown keys and type-checking known ones."""
    result = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if key in defaults and isinstance(defaults[key], dict):
            if isinstance(value, dict):
                result[key] = _merge_defaults(defaults[key], value) if defaults[key] else dict(value)
            continue
        if key in defaults and defaults[key] is not None:
            want = type(defaults[key])
            if want is float and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = float(value)
            elif not isinstance(value, want) or (want is not bool and isinstance(value, bool)):
                continue  # wrong type: keep the default
        result[key] = value
    return result


class GuiSettings:
    """Small JSON settings store. Never raises on a missing or corrupt file."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else settings_dir() / SETTINGS_FILENAME
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)

    def load(self) -> GuiSettings:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data = _merge_defaults(DEFAULT_SETTINGS, loaded)
            else:
                logger.warning(f"Ignoring settings file with unexpected content: {self.path}")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.warning(f"Could not read GUI settings ({e}); using defaults")
        return self

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except OSError as e:
            logger.warning(f"Could not save GUI settings: {e}")
            return False

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    # Remembered folders -------------------------------------------------
    def last_dir(self, kind: str) -> str | None:
        """Last folder used for a dialog kind, falling back to any known folder."""
        dirs = self.data.get("dirs") or {}
        for key in (kind, "subtitle", "video", "output", "folder"):
            d = dirs.get(key)
            if d and os.path.isdir(d):
                return d
        return None

    def remember_path(self, kind: str, path: str) -> None:
        if not path:
            return
        p = Path(path)
        folder = p if p.is_dir() else p.parent
        self.data.setdefault("dirs", {})[kind] = str(folder)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

THRESHOLD_MIN = 0.5
THRESHOLD_MAX = 1.0

_TIMESTAMP_RE = re.compile(r"^\s*(\d{1,2}):([0-5]?\d):([0-5]?\d)(?:[,.](\d{1,3}))?\s*$")


def parse_threshold(text: str) -> float:
    """Parse the merge "match strictness" value; raises ValueError with a friendly message."""
    try:
        value = float(str(text).strip().replace(",", "."))
    except ValueError:
        raise ValueError(t("ui.valid.threshold_number", low=THRESHOLD_MIN, high=THRESHOLD_MAX)) from None
    if not THRESHOLD_MIN <= value <= THRESHOLD_MAX:
        raise ValueError(t("ui.valid.threshold_range", low=THRESHOLD_MIN, high=THRESHOLD_MAX, value=f"{value:g}"))
    return value


def parse_timestamp(text: str) -> float:
    """Parse HH:MM:SS[,mmm] into seconds; raises ValueError."""
    m = _TIMESTAMP_RE.match(text or "")
    if not m:
        raise ValueError(t("ui.valid.timestamp"))
    h, mnt, s, ms = m.groups()
    ms_val = int((ms or "0").ljust(3, "0"))
    return int(h) * 3600 + int(mnt) * 60 + int(s) + ms_val / 1000.0


def parse_offset(text: str) -> int:
    """Parse a timing offset into milliseconds.

    Accepts "-2.5s", "+1500ms", "1.5 s", "1.5 seconds" and "-00:00:02,500".
    Raises ValueError with a message that can be shown to the user as-is.
    """
    raw = (text or "").strip().lower().replace(" ", "")
    if not raw:
        raise ValueError(t("ui.valid.offset_empty"))
    sign = 1
    body = raw
    if body[0] in "+-":
        sign = -1 if body[0] == "-" else 1
        body = body[1:]
    body = body.replace("seconds", "s").replace("second", "s").replace("secs", "s").replace("sec", "s")
    try:
        if ":" in body:
            return sign * round(parse_timestamp(body) * 1000)
        if body.endswith("ms"):
            return sign * int(float(body[:-2]))
        if body.endswith("s"):
            return sign * round(float(body[:-1]) * 1000)
        number = float(body)
    except ValueError:
        raise ValueError(t("ui.valid.offset_format")) from None
    if number == 0:
        return 0
    # A bare number is ambiguous (the CLI reads "2" as 2 ms); ask for a unit
    # instead of silently guessing.
    raise ValueError(t("ui.valid.offset_unit", n=text.strip()))


def format_offset(ms: int) -> str:
    """Format milliseconds the way users type offsets: +1.5s, -0.25s, 0s."""
    if ms == 0:
        return "0s"
    seconds = ms / 1000.0
    return f"{seconds:+.3f}".rstrip("0").rstrip(".") + "s"


# --------------------------------------------------------------------------
# Formatting file facts
# --------------------------------------------------------------------------

LANGUAGE_NAMES = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "fr": "French", "de": "German", "es": "Spanish",
}

ENCODING_NAMES = {
    "utf_8": "UTF-8", "utf-8": "UTF-8", "utf8": "UTF-8",
    "utf_8_sig": "UTF-8 (BOM)", "utf-8-sig": "UTF-8 (BOM)",
    "gb18030": "GB18030", "gbk": "GBK", "gb2312": "GB2312",
    "big5": "Big5", "shift_jis": "Shift-JIS", "shift-jis": "Shift-JIS",
    "cp932": "Shift-JIS", "euc_kr": "EUC-KR", "cp949": "EUC-KR",
    "ascii": "ASCII", "utf_16": "UTF-16", "utf-16": "UTF-16",
    "cp1252": "Windows-1252", "windows-1252": "Windows-1252",
    "latin_1": "Latin-1", "iso-8859-1": "Latin-1",
}


def language_name(code: str | None) -> str:
    if not code or code == "unknown":
        return t("ui.lang.unknown_language")
    name = LANGUAGE_NAMES.get(code.lower())
    return t(f"ui.lang.{name.lower()}") if name else code.upper()


def encoding_name(enc: str | None) -> str:
    if not enc:
        return t("ui.convert.enc_unknown_short")
    key = enc.strip().lower()
    return ENCODING_NAMES.get(key, ENCODING_NAMES.get(key.replace("-", "_"), enc.upper().replace("_", "-")))


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def describe_subtitle(info: dict[str, Any]) -> str:
    """One-line summary: "Chinese · 6 lines · 0:19 · UTF-8"."""
    if info.get("error"):
        return t("ui.chip.cant_read", error=info['error'])
    parts = [language_name(info.get("language"))]
    if info.get("events") is not None:
        n = info["events"]
        parts.append(t("ui.chip.one_line") if n == 1 else t("ui.preview.lines", n=n))
    if info.get("duration"):
        parts.append(format_duration(info["duration"]))
    if info.get("encoding"):
        parts.append(encoding_name(info["encoding"]))
    return " · ".join(parts)


def analyze_subtitle(path: Path) -> dict[str, Any]:
    """Collect language, line count, duration and encoding for a subtitle file.

    Slow on big files; call from a worker thread.
    """
    from core.encoding_detection import EncodingDetector
    from core.language_detection import LanguageDetector
    from core.subtitle_formats import SubtitleFormatFactory

    info: dict[str, Any] = {"path": str(path), "name": path.name}
    try:
        info["encoding"] = EncodingDetector.detect_encoding(path)
    except (OSError, ValueError, TypeError):
        info["encoding"] = None
    try:
        lang = LanguageDetector.detect_language_from_filename(str(path))
        if lang == "unknown":
            lang = LanguageDetector.detect_subtitle_language(path)
        info["language"] = lang
    except (OSError, ValueError, UnicodeDecodeError):
        info["language"] = "unknown"
    try:
        sub = SubtitleFormatFactory.parse_file(path)
        info["events"] = len(sub.events)
        info["duration"] = sub.events[-1].end if sub.events else 0
        info["bilingual_ratio"] = (LanguageDetector.detect_bilingual_events(sub.events)
                                   if sub.events else 0.0)
    except Exception as e:  # noqa: BLE001 - parsing errors come in many shapes
        info["error"] = str(e) or type(e).__name__
    return info


# --------------------------------------------------------------------------
# Track language choice ("Language:" combobox of Auto-detect tracks)
# --------------------------------------------------------------------------

LANGUAGE_TRACK_CODES = {
    "Chinese": {"chi", "zho", "zh", "chs", "cht", "cmn", "yue", "zh-hans", "zh-hant", "zh-cn", "zh-tw"},
    "Japanese": {"jpn", "ja", "jp"},
    "Korean": {"kor", "ko"},
    "English": {"eng", "en", "en-us", "en-gb"},
    "Spanish": {"spa", "es", "es-419", "es-es"},
    "French": {"fre", "fra", "fr", "fr-fr", "fr-ca"},
    "German": {"ger", "deu", "de", "de-de"},
}


def pick_track_for_language(tracks: Iterable[Any], language: str) -> str | None:
    """Track id (as str) of the first embedded track in `language`, or None.

    "Any" returns None (let the merger choose). "Other" picks the first track
    whose language is none of the listed ones.
    """
    if not language or language == "Any":
        return None
    known = set().union(*LANGUAGE_TRACK_CODES.values())
    codes = LANGUAGE_TRACK_CODES.get(language)
    for track in tracks:
        lang = (getattr(track, "language", None) or "").strip().lower()
        if language == "Other":
            if lang and lang not in known and lang not in ("und", "unknown"):
                return str(track.track_id)
        elif codes and (lang in codes or lang.split("-")[0] in codes):
            return str(track.track_id)
    return None


# --------------------------------------------------------------------------
# Video helpers
# --------------------------------------------------------------------------

def glob_escape(text: str) -> str:
    """Escape glob metacharacters in a file name stem (e.g. 'Movie [1080p]')."""
    return re.sub(r"([\[\]*?])", r"[\1]", text)


def parse_mkvinfo_tracks(output: str) -> list[dict[str, Any]]:
    """Parse `mkvinfo` text output into track dicts (id, type, language, codec, name)."""
    tracks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in output.split('\n'):
        match = re.search(r'Track number: \d+ \(track ID for mkvmerge & mkvextract: (\d+)\)', line)
        if match:
            if current:
                tracks.append(current)
            current = {'id': int(match.group(1)), 'type': 'unknown', 'language': '', 'codec': '', 'name': ''}
            continue
        if current is None:
            continue
        if 'Track type:' in line:
            low = line.lower()
            if 'video' in low:
                current['type'] = 'video'
            elif 'audio' in low:
                current['type'] = 'audio'
            elif 'subtitle' in low:
                current['type'] = 'subtitles'
        if 'Language (IETF BCP 47):' in line:
            m = re.search(r'Language \(IETF BCP 47\): (\S+)', line)
            if m:
                current['language'] = m.group(1)
        elif 'Language:' in line and not current['language']:
            m = re.search(r'Language: (\S+)', line)
            if m:
                current['language'] = m.group(1)
        if 'Codec ID:' in line:
            m = re.search(r'Codec ID: (\S+)', line)
            if m:
                current['codec'] = m.group(1)
        if '+ Name:' in line:
            m = re.search(r'\+ Name: (.+)', line)
            if m:
                current['name'] = m.group(1).strip()
    if current:
        tracks.append(current)
    return tracks


# --------------------------------------------------------------------------
# Batch results
# --------------------------------------------------------------------------

def summarize_batch_convert(results: dict[str, Any]) -> tuple[bool, str]:
    """(ok, text) for BatchProcessor.process_subtitles_batch results."""
    converted = results.get("successful", 0)
    unchanged = results.get("unchanged", 0)
    failed = results.get("failed", 0)
    parts = [t("ui.batch.sum_converted", n=converted), t("ui.batch.sum_fine", n=unchanged)]
    if failed:
        parts.append(t("ui.batch.sum_failed", n=failed))
    text = t("ui.batch.sum_sep").join(parts)
    if results.get("cancelled"):
        text = t("ui.batch.sum_stopped") + text
    return failed == 0, text


def summarize_batch_merge(results: dict[str, Any]) -> tuple[bool, str]:
    """(ok, text) for BatchProcessor.process_directory_interactive results."""
    parts = [t("ui.batch.sum_merged", n=results.get('successful', 0))]
    if results.get("skipped"):
        parts.append(t("ui.batch.sum_skipped", n=results['skipped']))
    if results.get("failed"):
        parts.append(t("ui.batch.sum_failed", n=results['failed']))
    text = t("ui.batch.sum_sep").join(parts)
    if results.get("cancelled"):
        text = t("ui.batch.sum_stopped") + text
    return not results.get("failed"), text


# --------------------------------------------------------------------------
# External tools
# --------------------------------------------------------------------------

TOOL_GROUPS = {
    "ffmpeg": ("ffmpeg", "ffprobe"),
    "mkvtoolnix": ("mkvextract", "mkvinfo"),
}

WINDOWS_DEFAULT_TOOL_DIRS = [
    r"C:\Program Files\MKVToolNix",
    r"C:\Program Files (x86)\MKVToolNix",
    r"C:\ffmpeg\bin",
]


def add_tool_dirs(dirs: Iterable[str]) -> list[str]:
    """Append existing folders to PATH for this process (subprocesses inherit it)."""
    added = []
    current = os.environ.get("PATH", "").split(os.pathsep)
    for d in dirs:
        if d and os.path.isdir(d) and d not in current:
            current.append(d)
            added.append(d)
    if added:
        os.environ["PATH"] = os.pathsep.join(current)
    return added


def missing_tools(group: str) -> list[str]:
    return [tool for tool in TOOL_GROUPS[group] if shutil.which(tool) is None]


def folder_has_tools(folder: str, group: str) -> bool:
    exe = ".exe" if sys.platform == "win32" else ""
    return all(os.path.isfile(os.path.join(folder, tool + exe)) for tool in TOOL_GROUPS[group])


def install_hint(group: str) -> str:
    """Short, platform-specific install advice."""
    if group == "ffmpeg":
        if sys.platform == "win32":
            return t("ui.tools.hint_ffmpeg_win")
        if sys.platform == "darwin":
            return t("ui.tools.hint_ffmpeg_mac")
        return t("ui.tools.hint_ffmpeg_linux")
    if sys.platform == "win32":
        return t("ui.tools.hint_mkv_win")
    if sys.platform == "darwin":
        return t("ui.tools.hint_mkv_mac")
    return t("ui.tools.hint_mkv_linux")


DOWNLOAD_PAGES = {
    "ffmpeg": "https://ffmpeg.org/download.html",
    "mkvtoolnix": "https://mkvtoolnix.download/downloads.html",
}


# --------------------------------------------------------------------------
# Opening files and folders
# --------------------------------------------------------------------------

def reveal_in_file_manager(path: Path) -> None:
    """Open the folder containing path, selecting the file where the OS supports it."""
    path = Path(path)
    if sys.platform == "win32":
        if path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path if path.is_dir() else path.parent))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if path.exists() else ["open", str(path.parent)])
    else:
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])


def open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# --------------------------------------------------------------------------
# Windows integration
# --------------------------------------------------------------------------

def enable_windows_dpi_awareness() -> None:
    """Make the process DPI aware so Windows does not bitmap-stretch (blur) the UI.

    Must run before the first Tk() is created. System-DPI awareness is used
    rather than per-monitor: Tk 8.6 does not rescale on WM_DPICHANGED, so
    per-monitor mode would leave the window wrongly sized on a second monitor
    with a different scale factor, while system awareness keeps it crisp on
    the primary monitor and correctly sized everywhere.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception as e:  # noqa: BLE001 - never block startup on this
        logger.debug(f"DPI awareness not set: {e}")


def set_windows_app_id(app_id: str = "BISS.BilingualSubtitleSuite") -> None:
    """Group the window under its own taskbar button/icon instead of python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError) as e:
        logger.debug(f"AppUserModelID not set: {e}")


def windows_work_area() -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the primary monitor's work area (excludes the taskbar)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right, rect.bottom
    except (AttributeError, OSError, ValueError) as e:
        logger.debug(f"Work area unavailable: {e}")
    return None


def parse_geometry(geometry: str) -> tuple[int, int, int, int] | None:
    m = re.fullmatch(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)", geometry or "")
    if not m:
        return None
    w, h, x, y = m.groups()
    return int(w), int(h), int(x.replace("+", "")), int(y.replace("+", ""))


def fit_geometry(width: int, height: int, x: int | None, y: int | None,
                 area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Clamp a window rectangle into the work area; centre it when x/y are None."""
    left, top, right, bottom = area
    aw, ah = right - left, bottom - top
    width, height = min(width, aw), min(height, ah)
    if x is None or y is None:
        x = left + (aw - width) // 2
        y = top + max(0, (ah - height) // 3)
    x = min(max(x, left), right - width)
    y = min(max(y, top), bottom - height)
    return width, height, x, y
