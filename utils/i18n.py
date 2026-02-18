"""
Internationalization (i18n) support for Bilingual Subtitle Suite.

Provides a simple translation system with JSON locale files.
Supports: English (en), Chinese (zh), Japanese (ja), Korean (ko).

Usage:
    from utils.i18n import t, set_locale, get_locale

    set_locale("zh")       # Switch to Chinese
    print(t("app.name"))   # Prints localized app name
"""

import json
import locale
import os
from pathlib import Path
from typing import Optional

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_current_locale = "en"
_strings = {}
_fallback_strings = {}


def _load_locale(lang: str) -> dict:
    """Load a locale JSON file and return the flattened key-value dict."""
    locale_file = _LOCALES_DIR / f"{lang}.json"
    if not locale_file.exists():
        return {}
    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _flatten(data)
    except (json.JSONDecodeError, OSError):
        return {}


def _flatten(obj: dict, prefix: str = "") -> dict:
    """Flatten nested dict into dot-separated keys."""
    items = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten(v, key))
        else:
            items[key] = v
    return items


def set_locale(lang: str) -> None:
    """Set the active locale.

    Args:
        lang: Language code (en, zh, ja, ko).
    """
    global _current_locale, _strings, _fallback_strings
    lang = lang.lower().strip()

    # Normalize common variants
    lang_map = {
        "cn": "zh", "chinese": "zh", "zh-cn": "zh", "zh-tw": "zh",
        "jp": "ja", "japanese": "ja",
        "kr": "ko", "korean": "ko",
        "english": "en",
    }
    lang = lang_map.get(lang, lang)

    if lang not in ("en", "zh", "ja", "ko"):
        lang = "en"

    _current_locale = lang
    _fallback_strings = _load_locale("en")
    if lang == "en":
        _strings = _fallback_strings
    else:
        _strings = _load_locale(lang)


def get_locale() -> str:
    """Return the current locale code."""
    return _current_locale


def get_available_locales() -> list:
    """Return list of available locale codes."""
    locales = []
    for f in _LOCALES_DIR.glob("*.json"):
        locales.append(f.stem)
    return sorted(locales)


def detect_system_locale() -> str:
    """Detect system locale and return matching language code."""
    # Check environment variable first
    env_lang = os.environ.get("BISS_LANG", "").strip()
    if env_lang:
        return env_lang

    try:
        sys_locale = locale.getdefaultlocale()[0] or ""
    except (ValueError, AttributeError):
        sys_locale = ""

    sys_locale = sys_locale.lower()
    if sys_locale.startswith("zh"):
        return "zh"
    elif sys_locale.startswith("ja"):
        return "ja"
    elif sys_locale.startswith("ko"):
        return "ko"
    return "en"


def t(key: str, **kwargs) -> str:
    """Translate a key to the current locale.

    Args:
        key: Dot-separated translation key (e.g. "menu.merge").
        **kwargs: Format parameters for string interpolation.

    Returns:
        Translated string, or English fallback, or the key itself.
    """
    # Ensure locale is loaded
    if not _strings and not _fallback_strings:
        set_locale(_current_locale)

    text = _strings.get(key) or _fallback_strings.get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# Auto-initialize with English on import
set_locale("en")
