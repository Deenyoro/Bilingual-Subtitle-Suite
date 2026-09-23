"""
Graphical interface for the Bilingual Subtitle Suite (Tkinter/ttk).

Layout: compact header, one notebook tab per task, and on every tab a
scrolling body with a fixed action bar underneath (status/progress, Cancel,
primary button), so the main action is always visible. A collapsible
Details pane shows the log.

Threading contract: long work runs in worker threads that never touch Tk.
Workers hand UI updates to the main thread through ``self._post`` (a queue
drained by an ``after`` pump); ``self._call_in_main`` asks the user a
question from a worker and waits for the answer.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.gui_support import (
    DOWNLOAD_PAGES,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    WINDOWS_DEFAULT_TOOL_DIRS,
    GuiSettings,
    add_tool_dirs,
    analyze_subtitle,
    describe_subtitle,
    enable_windows_dpi_awareness,
    encoding_name,
    fit_geometry,
    folder_has_tools,
    format_offset,
    glob_escape,
    install_hint,
    missing_tools,
    parse_geometry,
    parse_mkvinfo_tracks,
    parse_offset,
    parse_threshold,
    parse_timestamp,
    pick_track_for_language,
    reveal_in_file_manager,
    set_windows_app_id,
    summarize_batch_convert,
    summarize_batch_merge,
    windows_work_area,
)
from ui.widgets import (
    ERROR,
    MUTED,
    PAD,
    PAD_L,
    PAD_S,
    SUCCESS,
    ActionBar,
    Banner,
    Collapsible,
    InfoChip,
    ScrollableFrame,
    setup_theme,
)
from utils.constants import (
    APP_NAME,
    APP_VERSION,
    VIDEO_EXTENSIONS,
    is_lite_build,
)
from utils.i18n import get_locale, set_locale, t
from utils.logging_config import get_logger

logger = get_logger(__name__)

SUBTITLE_TYPES = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
VIDEO_TYPES = [("Video files", "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"), ("All files", "*.*")]
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}
LANGUAGE_CHOICES = ["Any", "Chinese", "Japanese", "Korean", "English", "Spanish", "French", "German", "Other"]
UI_LANGUAGES = (("en", "English"), ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어"))


def _subtitle_types():
    return [(t("ui.ft.subtitles"), "*.srt *.ass *.ssa *.vtt"), (t("ui.ft.all"), "*.*")]


def _video_types():
    return [(t("ui.ft.videos"), "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"), (t("ui.ft.all"), "*.*")]


def _lang_label(choice: str) -> str:
    """Display name of a LANGUAGE_CHOICES value in the UI language."""
    return t(f"ui.lang.{choice.lower()}")


def _lang_choice(label: str) -> str:
    """LANGUAGE_CHOICES value for a display name (any UI language, or the value itself)."""
    for choice in LANGUAGE_CHOICES:
        if label in (choice, _lang_label(choice)):
            return choice
    return label or "Any"


def parse_drop_data(tk_app: tk.Misc, data: str) -> list[str]:
    """Paths from a tkdnd <<Drop>> payload ('{C:/My Files/a.srt} C:/b.srt')."""
    try:
        items = tk_app.tk.splitlist(data)
    except tk.TclError:
        items = [data]
    paths = []
    for item in items:
        item = str(item).strip()
        if item.startswith("file://"):
            from urllib.parse import unquote, urlparse
            item = unquote(urlparse(item).path)
            if sys.platform == "win32" and len(item) > 2 and item[0] == "/" and item[2] == ":":
                item = item[1:]
        if item:
            paths.append(os.path.normpath(item))
    return paths


def enable_drag_and_drop(root: tk.Misc) -> tuple[bool, str]:
    """Load the optional tkdnd extension (tkinterdnd2) into an existing Tk root.

    Returns (True, "") on success, or (False, reason) - the app then keeps
    working without drag-and-drop - when the package or its native library
    is missing.
    """
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        return False, "tkinterdnd2 is not installed"
    loader = getattr(TkinterDnD, "require", None) or getattr(TkinterDnD, "_require", None)
    if loader is None:
        return False, "this tkinterdnd2 version has no loader"
    try:
        loader(root)
        return True, ""
    except (RuntimeError, tk.TclError, OSError) as e:
        try:
            detail = root.tk.eval("set errorInfo").splitlines()[0]
        except tk.TclError:
            detail = ""
        return False, f"{e} {detail}".strip()

TAB_KEYS = ["merge", "extract", "split", "shift", "convert", "batch"]


def _sync_to_new_file(syncer, video_path: Path, sub_path: Path, target: Path, track_index):
    """Detect the offset on ``sub_path`` and write the shifted copy to ``target``.

    Nothing is written to ``target`` unless detection succeeded, so a failure
    leaves any existing file at ``target`` exactly as it was.
    """
    import shutil

    from processors.timing_adjuster import TimingAdjuster

    result = syncer.detect_offset(video_path, sub_path, track_index, None)
    if not result.success:
        return result
    if result.offset_ms == 0:
        shutil.copy2(sub_path, target)
        result.message = "No offset detected - subtitles appear to be in sync"
        return result
    shift_ms = -result.offset_ms
    if TimingAdjuster(create_backup=False).adjust_by_offset(sub_path, shift_ms, output_path=target):
        result.message = (f"Shifted by {shift_ms:+d}ms (offset was {result.offset_ms:+d}ms, "
                          f"{result.match_count}/{result.total_compared} matches)")
        result.subtitle = target
    else:
        result.success = False
        result.message = f"Failed to apply timing shift of {shift_ms:+d}ms"
    return result


def _resource_path(*parts: str) -> Path:
    """Path of a bundled data file (works from source and from the PyInstaller exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


class LogHandler(logging.Handler):
    """Custom logging handler that sends logs to a queue for GUI display."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        self.last_error: str | None = None

    def emit(self, record):
        msg = self.format(record)
        if record.levelno >= logging.ERROR:
            self.last_error = record.getMessage()
        self.log_queue.put(msg)


class DragDropMixin:
    """Mixin to add drag-and-drop support (active only when tkdnd is loaded)."""

    def setup_drag_drop(self, widget, callback, on_enter=None, on_leave=None):
        """Accept files dropped from Explorer on widget; callback(list_of_paths).

        Talks to tkdnd through Tcl directly, so it works with any tkinterdnd2
        version and is a silent no-op when tkdnd is not loaded.
        """
        if not getattr(self, "_dnd", False):
            return False
        try:
            tk_app = widget.tk
            tk_app.call("tkdnd::drop_target", "register", widget._w, "DND_Files")

            def dropped(data):
                try:
                    callback(parse_drop_data(widget, data))
                except Exception:  # noqa: BLE001 - report any failure to the user
                    widget._root().report_callback_exception(*sys.exc_info())
                return "copy"

            def entered(*_):
                if on_enter:
                    on_enter()
                return "copy"

            def left(*_):
                if on_leave:
                    on_leave()
                return "copy"

            tk_app.call("bind", widget._w, "<<Drop>>", widget.register(dropped) + " %D")
            tk_app.call("bind", widget._w, "<<DropEnter>>", widget.register(entered))
            tk_app.call("bind", widget._w, "<<DropLeave>>", widget.register(left))
            return True
        except tk.TclError as e:
            logger.debug(f"Drag and drop unavailable: {e}")
            return False


class SubtitleInfoPanel(ttk.Frame):
    """One-line summary of a subtitle file (kept for API compatibility).

    ``update_info`` analyses the file on a worker thread and updates the label
    from the Tk thread.
    """

    def __init__(self, parent, title="Subtitle Info"):
        super().__init__(parent)
        self.chip = InfoChip(self)
        self.chip.pack(fill=tk.X)

    def update_info(self, file_path: Path | None = None):
        if not file_path or not Path(file_path).exists():
            self.chip.clear()
            return
        self.chip.show(t("ui.common.reading_file"), "busy")
        result: dict[str, Any] = {}

        def work():
            result.update(analyze_subtitle(Path(file_path)))

        def poll(thread):
            if thread.is_alive():
                self.after(100, lambda: poll(thread))
            else:
                self.chip.show(describe_subtitle(result), "error" if result.get("error") else "ok")

        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.after(100, lambda: poll(th))


class BISSGui(DragDropMixin):
    """Main GUI application class."""

    def __init__(self):
        # Must happen before the first Tk() so Windows does not blur the UI.
        enable_windows_dpi_awareness()
        set_windows_app_id()

        self.settings = GuiSettings().load()
        self._apply_saved_locale()
        extra_dirs = list(self.settings.get("tool_dirs", []) or [])
        if sys.platform == "win32":
            extra_dirs += WINDOWS_DEFAULT_TOOL_DIRS
        add_tool_dirs(extra_dirs)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"{APP_NAME}")
        self._dnd, self._dnd_error = enable_drag_and_drop(self.root)
        self.scale = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)

        # Initialize PGSRip wrapper
        self._pgsrip_wrapper = None
        self._pgs_available = False
        self._is_lite = is_lite_build()
        try:
            from third_party import PGSRipWrapper, is_pgsrip_available
            if is_pgsrip_available():
                self._pgsrip_wrapper = PGSRipWrapper()
                self._pgs_available = True
        except Exception as e:  # noqa: BLE001 - optional component, any failure means "not available"
            logger.debug(f"PGSRip unavailable: {e}")

        # Theme, fonts and styles
        self.style = ttk.Style(self.root)
        self._palette = setup_theme(self.root)
        self._set_window_icon()

        # Queues for thread-safe logging and UI updates
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._running: dict[str, threading.Event] = {}
        self._closing = False
        self._analysis_after: dict[str, str] = {}
        self._analysis_gen: dict[str, int] = {}
        self._file_info: dict[str, dict[str, Any]] = {}
        self._translation_key_available = False
        self._missing: dict[str, list[str]] = {"ffmpeg": [], "mkvtoolnix": []}
        self._env_checked = False
        self._tab_status: dict[str, str] = {}
        self._end_pending: list[Callable[[], None]] = []
        self._end_job: str | None = None
        self._preview_dir: Path | None = None
        self._setup_logging()

        # Build the interface
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self._restore_state()
        if self._dnd:
            logger.info("Drag and drop is enabled")
        else:
            logger.info(f"Drag and drop is not available ({self._dnd_error}); use the Browse buttons.")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._report_callback_exception

        self._pump_queues()
        self._place_window()
        self.root.deiconify()
        threading.Thread(target=self._check_environment, daemon=True).start()

    # ======================================================================
    # Setup helpers
    # ======================================================================

    def _apply_saved_locale(self):
        saved = self.settings.get("locale") or ""
        cli_lang = any(a == "--lang" or a.startswith("--lang=") for a in sys.argv)
        if saved and not cli_lang and not os.environ.get("BISS_LANG"):
            set_locale(saved)

    def _set_window_icon(self):
        self._icons = []
        try:
            for size in (256, 48, 32, 16):
                p = _resource_path("images", f"biss-icon-{size}.png")
                if p.exists():
                    self._icons.append(tk.PhotoImage(master=self.root, file=str(p)))
            if self._icons:
                self.root.iconphoto(True, *self._icons)
        except tk.TclError as e:
            logger.debug(f"Could not set window icon: {e}")

    def _setup_logging(self):
        """Set up logging to display in GUI."""
        self.log_handler = LogHandler(self.log_queue)
        self.log_handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)

    def _place_window(self):
        """Size the window from its content, clamped to the screen's work area."""
        self.root.update_idletasks()
        area = windows_work_area() or (0, 0, self.root.winfo_screenwidth(),
                                       self.root.winfo_screenheight() - int(48 * self.scale))
        aw, ah = area[2] - area[0], area[3] - area[1]
        min_w = min(int(640 * self.scale), aw)
        min_h = min(int(480 * self.scale), ah)
        self.root.minsize(min_w, min_h)

        want_w = min(max(self.root.winfo_reqwidth(), int(900 * self.scale)), int(1100 * self.scale),
                     int(aw * 0.92))
        want_h = min(self.root.winfo_reqheight(), int(ah * 0.94))
        x = y = None
        saved = parse_geometry(self.settings.get("geometry", ""))
        if saved:
            want_w, want_h, x, y = max(saved[0], min_w), max(saved[1], min_h), saved[2], saved[3]
        w, h, x, y = fit_geometry(want_w, want_h, x, y, area)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        if self.settings.get("zoomed") and sys.platform == "win32":
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def _center_window(self):
        """Kept for compatibility; placement is handled by _place_window."""
        self._place_window()

    def _build_ui(self):
        """Create every widget that shows text (called again when the language changes)."""
        self._create_header()
        self._create_main_interface()
        self._create_details_pane()
        self._create_status_bar()
        self._create_menu()
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed(), add="+")
        self._setup_drop_targets()

    # ======================================================================
    # Shell: header, tabs, details, status bar, menus
    # ======================================================================

    def _create_header(self):
        """Compact header: logo mark, product name, tagline."""
        header = ttk.Frame(self.root, padding=(PAD_L, PAD, PAD_L, PAD_S))
        header.grid(row=0, column=0, sticky="ew")
        self.header_frame = header
        header.columnconfigure(2, weight=1)

        self.logo_image = None
        size = 28 if self.scale < 1.25 else (42 if self.scale < 1.75 else 56)
        logo_path = _resource_path("images", f"biss-logo-{size}.png")
        if logo_path.exists():
            try:
                self.logo_image = tk.PhotoImage(master=self.root, file=str(logo_path))
                ttk.Label(header, image=self.logo_image).grid(row=0, column=0, sticky="w", padx=(0, PAD))
            except tk.TclError as e:
                logger.debug(f"Could not load logo: {e}")
        if self.logo_image is None:
            self._create_text_header(header)
        ttk.Label(header, text="Bilingual Subtitle Suite", style="Heading.TLabel").grid(
            row=0, column=1, sticky="w")
        ttk.Label(header, text=f"{t('app.tagline')}  ·  v{APP_VERSION}", style="Caption.TLabel").grid(
            row=0, column=3, sticky="e")

    def _create_text_header(self, parent):
        """Create text-based header when the logo is unavailable."""
        ttk.Label(parent, text="BISS", style="Title.TLabel", foreground="#0067C0").grid(
            row=0, column=0, sticky="w", padx=(0, PAD))

    def _create_main_interface(self):
        """Create the tabbed interface."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=PAD, pady=(0, 0))
        self.notebook.enable_traversal()  # Ctrl+Tab / Ctrl+Shift+Tab
        self._tabs: dict[str, ttk.Frame] = {}
        self._bars: dict[str, ActionBar] = {}
        self._scrollers: dict[str, ScrollableFrame] = {}
        self._drop_rows: list[tuple[tk.Widget, Callable[[list[str]], None]]] = []

        self._create_merge_tab()
        self._create_extract_tab()
        self._create_split_tab()
        self._create_shift_tab()
        self._create_convert_tab()
        self._create_batch_tab()

    def _new_tab(self, key: str, title: str):
        """A tab = scrolling body (row 0) + separator + fixed action bar (row 2)."""
        frame = ttk.Frame(self.notebook)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        scroller = ScrollableFrame(frame)
        scroller.grid(row=0, column=0, sticky="nsew")
        ttk.Separator(frame, orient="horizontal").grid(row=1, column=0, sticky="ew")
        self.notebook.add(frame, text=title)
        self._tabs[key] = frame
        self._scrollers[key] = scroller
        body = scroller.body
        body.columnconfigure(0, weight=1)
        return frame, body

    def _add_action_bar(self, key: str, text: str, command: Callable, hint: str) -> ActionBar:
        bar = ActionBar(self._tabs[key], text=text, command=command, hint=hint)
        bar.grid(row=2, column=0, sticky="ew")
        self._bars[key] = bar
        return bar

    def _create_details_pane(self):
        """Collapsible log ('Details')."""
        self.details_frame = ttk.Frame(self.root, padding=(PAD, PAD_S, PAD, 0))
        self.details_frame.columnconfigure(0, weight=1)
        top = ttk.Frame(self.details_frame)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text=t('gui.output_log'), style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(top, text=t("ui.common.copy"), command=self._copy_log, style="Link.TButton").grid(
            row=0, column=1, padx=(PAD_S, 0))
        ttk.Button(top, text=t('gui.clear'), command=self._clear_log, style="Link.TButton").grid(row=0, column=2, padx=(PAD_S, 0))
        self.log_text = scrolledtext.ScrolledText(self.details_frame, height=8, state='disabled',
                                                  font="BissMono", wrap=tk.WORD, relief="flat",
                                                  borderwidth=1, highlightthickness=1)
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(PAD_S, 0))
        if not hasattr(self, "details_open"):
            self.details_open = tk.BooleanVar(master=self.root, value=False)

    def _create_status_bar(self):
        """Status text on the left, Details toggle and size grip on the right."""
        status_frame = ttk.Frame(self.root, padding=(PAD, 2, 0, 2))
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_frame = status_frame
        self.status_var = tk.StringVar(value=t('gui.status_ready'))
        ttk.Label(status_frame, textvariable=self.status_var, anchor='w', style="Caption.TLabel").grid(
            row=0, column=0, sticky="ew")
        self.details_btn = ttk.Button(status_frame, style="Toolbutton", command=self._toggle_details)
        self.details_btn.grid(row=0, column=1, sticky="e", padx=(PAD, 0))
        ttk.Sizegrip(status_frame).grid(row=0, column=2, sticky="se")
        self._update_details_button()

    def _toggle_details(self, show: bool | None = None):
        opened = (not self.details_open.get()) if show is None else show
        self.details_open.set(opened)
        if opened:
            self.details_frame.grid(row=2, column=0, sticky="nsew")
            self.log_text.see(tk.END)
        else:
            self.details_frame.grid_remove()
        self._update_details_button()

    def _update_details_button(self):
        arrow = "▾" if self.details_open.get() else "▴"
        self.details_btn.configure(text=f"{t('ui.common.details')} {arrow}")

    def _create_menu(self):
        """Create the menu bar (generated from the tab registry)."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.file_menu'), menu=file_menu, underline=0)
        file_menu.add_command(label=t('gui.open_subtitle'), command=self._open_subtitle,
                              accelerator="Ctrl+O", underline=0)
        file_menu.add_command(label=t('gui.open_video'), command=self._open_video,
                              underline=5 if get_locale() == "en" else -1)
        file_menu.add_separator()
        file_menu.add_command(label=t('gui.preview'), command=lambda: self._show_subtitle_preview(),
                              accelerator="Ctrl+P", underline=0)
        file_menu.add_separator()
        file_menu.add_command(label=t('gui.exit'), command=self._on_close, accelerator="Alt+F4",
                              underline=1 if get_locale() == "en" else -1)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.tools_menu'), menu=tools_menu, underline=0)
        labels = {
            "merge": t('gui.merge_subtitles'), "extract": t('gui.extract_tracks'),
            "split": t('gui.split_bilingual'), "shift": t('gui.shift_timing'),
            "convert": t('gui.convert_encoding'), "batch": t('gui.batch_operations'),
        }
        self._tools_menu = tools_menu
        for i, key in enumerate(TAB_KEYS, start=1):
            if key == "batch":
                tools_menu.add_separator()
            tools_menu.add_command(label=labels[key], accelerator=f"Ctrl+{i}",
                                   command=lambda k=key: self._select_tab(k))

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.view_menu'), menu=view_menu, underline=0)
        view_menu.add_checkbutton(label=t('gui.show_details'), variable=self.details_open,
                                  command=lambda: self._toggle_details(self.details_open.get()),
                                  accelerator="Ctrl+L", underline=5 if get_locale() == "en" else -1)
        lang_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Language" if get_locale() == "en" else f"{t('gui.language')} (Language)",
                              menu=lang_menu, underline=0 if get_locale() == "en" else -1)
        self._locale_var = tk.StringVar(master=self.root, value=get_locale())
        for code, name in UI_LANGUAGES:
            lang_menu.add_radiobutton(label=name, value=code, variable=self._locale_var,
                                      command=self._change_language)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.help_menu'), menu=help_menu, underline=0)
        help_menu.add_command(label=t('gui.quick_guide'), command=self._show_help, accelerator="F1", underline=0)
        help_menu.add_command(label=t('gui.shortcuts'), command=self._show_shortcuts, underline=0)
        help_menu.add_separator()
        help_menu.add_command(label=t('gui.about'), command=self._show_about, underline=0)

    def _bind_shortcuts(self):
        self.root.bind('<Control-o>', lambda e: self._open_subtitle())
        self.root.bind('<Control-p>', lambda e: self._show_subtitle_preview())
        self.root.bind('<Control-l>', lambda e: self._toggle_details())
        self.root.bind('<F1>', lambda e: self._show_help())
        self.root.bind('<Control-Return>', lambda e: self._run_current_tab())
        self.root.bind('<Control-KP_Enter>', lambda e: self._run_current_tab())
        for i, key in enumerate(TAB_KEYS, start=1):
            self.root.bind(f'<Control-Key-{i}>', lambda e, k=key: self._select_tab(k))

    def _select_tab(self, key: str):
        self.notebook.select(self._tabs[key])

    def _on_tab_changed(self):
        """Show the status of the tab you are looking at, not of the one you left."""
        key = self._current_tab_key()
        self.status_var.set(self._tab_status.get(key) or t('gui.status_ready'))
    def _current_tab_key(self) -> str:
        current = self.notebook.select()
        for key, frame in self._tabs.items():
            if str(frame) == current:
                return key
        return "merge"

    def _run_current_tab(self):
        bar = self._bars.get(self._current_tab_key())
        if bar and bar.button.instate(["!disabled"]):
            bar.button.invoke()
        return "break"

    def _change_language(self):
        """View > Language: switch the whole window to the new language right away."""
        code = self._locale_var.get()
        if code == get_locale():
            return
        if self._running:
            self._locale_var.set(get_locale())
            messagebox.showinfo(t("ui.lang_switch.title"), t("ui.lang_switch.busy"), parent=self.root)
            return
        self.settings.set("locale", code)
        self.settings.save()
        set_locale(code)
        self._rebuild_ui()

    # Variables whose values are language-specific display text.
    _LANG_VARS = ("chinese_auto_lang_var", "english_auto_lang_var")
    # Variables owned by the shell, not by a tab (kept across a rebuild).
    _SHELL_VARS = ("details_open", "_locale_var", "status_var")

    def _snapshot_ui(self) -> dict[str, Any]:
        """Everything the user entered or loaded, so a rebuild loses nothing."""
        snap: dict[str, Any] = {"vars": {}, "combos": {}}
        for name, value in list(vars(self).items()):
            if isinstance(value, tk.Variable) and name not in self._SHELL_VARS:
                try:
                    snap["vars"][name] = value.get()
                except tk.TclError:
                    pass
        for name in self._LANG_VARS:
            if name in snap["vars"]:
                snap["vars"][name] = _lang_choice(snap["vars"][name])
        if not str(snap["vars"].get("sync_track_var", "")).startswith("s:"):
            snap["vars"].pop("sync_track_var", None)  # "(auto-detect)" is shown in the new language
        for name in ("chinese_track_combo", "english_track_combo", "pgs_track_combo", "sync_track_combo"):
            combo = getattr(self, name, None)
            if combo is not None:
                snap["combos"][name] = list(combo.cget("values") or ())
        snap["tab"] = self._current_tab_key()
        snap["log"] = self.log_text.get("1.0", "end-1c")
        snap["batch_results"] = list(self.batch_results.get(0, tk.END))
        snap["extract_rows"] = [self.extract_tree.item(i, "values") for i in self.extract_tree.get_children()]
        selected = set(self.extract_tree.selection())
        snap["extract_selected"] = [n for n, i in enumerate(self.extract_tree.get_children()) if i in selected]
        snap["advanced_open"] = self.merge_advanced.opened
        return snap

    def _rebuild_ui(self):
        """Recreate all widgets in the current language, keeping the user's input."""
        snap = self._snapshot_ui()
        self._collect_settings()
        for job in list(self._analysis_after.values()):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._analysis_after.clear()
        for key in list(self._analysis_gen):
            self._analysis_gen[key] += 1  # results still on their way belong to old widgets
        for child in list(self.root.winfo_children()):
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self._build_ui()
        for name, value in snap["vars"].items():
            var = getattr(self, name, None)
            if isinstance(var, tk.Variable):
                if name in self._LANG_VARS:
                    value = _lang_label(value)
                try:
                    var.set(value)
                except tk.TclError:
                    pass
        for name, values in snap["combos"].items():
            combo = getattr(self, name, None)
            if combo is not None:
                combo.configure(values=values)
        for values in snap["extract_rows"]:
            self.extract_tree.insert("", "end", values=values)
        items = self.extract_tree.get_children()
        self.extract_tree.selection_set([items[i] for i in snap["extract_selected"] if i < len(items)])
        for line in snap["batch_results"]:
            self.batch_results.insert(tk.END, line)
        self.log_text.configure(state="normal")
        self.log_text.insert("1.0", snap["log"] + ("\n" if snap["log"] else ""))
        self.log_text.configure(state="disabled")
        if snap["advanced_open"] != self.merge_advanced.opened:
            self.merge_advanced.toggle()
        self._update_chinese_source()
        self._update_english_source()
        self._update_shift_mode()
        self._update_shift_output()
        self._update_convert_type()
        self._update_batch_options()
        if self._env_checked:
            self._apply_environment(self._missing["ffmpeg"], self._missing["mkvtoolnix"],
                                    self._translation_key_available)
        self._tab_status.clear()
        self._select_tab(snap["tab"])
        self._toggle_details(bool(self.details_open.get()))
        self.status_var.set(t('gui.status_ready'))

    # ======================================================================
    # Threading helpers
    # ======================================================================

    def _post(self, fn: Callable[[], Any]):
        """Run fn on the Tk main thread (safe to call from any thread)."""
        self._ui_queue.put(fn)

    def _call_in_main(self, fn: Callable[[], Any], cancel: threading.Event | None = None):
        """From a worker: run fn on the main thread and wait for its result."""
        done = threading.Event()
        box: dict[str, Any] = {}

        def run():
            try:
                box["value"] = fn()
            finally:
                done.set()

        self._post(run)
        while not done.wait(0.1):
            if self._closing or (cancel is not None and cancel.is_set()):
                return None
        return box.get("value")

    def _pump_queues(self):
        """Drain the log and UI queues (runs on the main thread every 50 ms)."""
        lines = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if lines:
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, "\n".join(lines) + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        for _ in range(200):
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:  # noqa: BLE001 - report any failure to the user
                self._report_callback_exception(*sys.exc_info())
        if not self._closing:
            self._pump_job = self.root.after(50, self._pump_queues)

    def _stop_pump(self):
        self._closing = True
        if self._end_job is not None:
            try:
                self.root.after_cancel(self._end_job)
            except tk.TclError:
                pass
            self._end_job = None
        job = getattr(self, "_pump_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        for job in list(self._analysis_after.values()):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    # Kept for compatibility with older callers.
    def _poll_log_queue(self):
        pass

    def _run_task(self, key: str, start_text: str, work: Callable[[threading.Event], Any],
                  done: Callable[[bool, Any, bool], None], cancellable: bool = False,
                  determinate: bool = False, status: str | None = None):
        """Run work(cancel_event) on a worker thread with the tab's action bar showing progress.

        done(ok, result_or_exception, cancelled) runs on the main thread.
        """
        bar = self._bars[key]
        cancel = threading.Event()
        self._running[key] = cancel
        self.log_handler.last_error = None
        bar.start(start_text, cancellable=cancellable, on_cancel=cancel.set, determinate=determinate)
        running_status = status or start_text
        self._set_status(running_status, key)

        def runner():
            try:
                result, ok = work(cancel), True
            except Exception as e:  # noqa: BLE001 - reported to the user in done()
                logger.error(f"{type(e).__name__}: {e}")
                logger.debug(traceback.format_exc())
                result, ok = e, False

            def finish():
                self._running.pop(key, None)
                if self._closing:
                    return
                try:
                    done(ok, result, cancel.is_set())
                finally:
                    if bar.busy:  # done() forgot to finish the bar
                        bar.finish("info", t("ui.common.finished"))
                    if self._tab_status.get(key) == running_status:  # never leave "…ing" behind
                        self._set_status(t('gui.status_ready'), key)

            self._post(finish)

        threading.Thread(target=runner, daemon=True, name=f"biss-{key}").start()

    def _fail(self, key: str, what: str, error: Any, dialog: bool = True):
        """Show a failure inline (and in a dialog): what failed, why, where to look."""
        reason = str(error) if error else (self.log_handler.last_error or "")
        reason = reason.strip() or t("ui.common.no_details")
        text = f"{what}: {reason}"
        self._bars[key].finish("error", text,
                               actions=[(t("ui.common.show_details"), lambda: self._toggle_details(True))])
        self._set_status(f"✖ {what}", key)
        if dialog:
            messagebox.showerror(what, f"{reason}\n\n{t('ui.common.see_details')}", parent=self.root)

    def _invalid(self, key: str, message: str, focus: tk.Widget | None = None):
        """Inline validation error in the tab's action bar (no modal dialog)."""
        self._bars[key].finish("error", message)
        self.root.bell()
        if focus is not None:
            try:
                focus.focus_set()
            except tk.TclError:
                pass

    def _output_actions(self, path: Path | None, preview: bool = True):
        actions = []
        if path:
            actions.append((t("ui.common.open_folder"), lambda p=Path(path): self._reveal(p)))
            if preview and Path(path).suffix.lower() in SUBTITLE_EXTENSIONS:
                actions.append((t("ui.common.preview"), lambda p=str(path): self._show_subtitle_preview(p)))
        return actions

    def _reveal(self, path: Path):
        try:
            reveal_in_file_manager(path)
        except Exception as e:  # noqa: BLE001 - report any failure to the user
            messagebox.showerror(t("ui.common.cant_open_folder"), str(e), parent=self.root)

    def _confirm_replace(self, path: Path) -> bool:
        """Ask before overwriting an existing output file (main thread only)."""
        return bool(messagebox.askyesno(
            t("ui.replace.title"), t("ui.replace.message", name=Path(path).name),
            detail=t("ui.replace.detail", folder=str(Path(path).parent)),
            icon="warning", default="no", parent=self.root))

    def _report_callback_exception(self, exc, val, tb):
        """Friendly dialog instead of a traceback in the (hidden) console."""
        details = "".join(traceback.format_exception(exc, val, tb))
        logger.error(f"Unexpected error: {val}")
        logging.getLogger(__name__).debug(details)
        try:
            self._show_error_details(t("ui.error.title"), f"{val}\n\n{t('ui.error.body')}", details)
        except tk.TclError:
            sys.stderr.write(details)

    def _show_error_details(self, title: str, message: str, details: str):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        ttk.Label(win, text=message, wraplength=int(460 * self.scale), justify="left",
                  padding=(PAD_L, PAD_L, PAD_L, PAD)).grid(row=0, column=0, sticky="ew")
        text = scrolledtext.ScrolledText(win, height=10, width=80, font="BissMono", wrap="none")
        text.insert("1.0", details)
        text.configure(state="disabled")
        text.grid(row=1, column=0, sticky="nsew", padx=PAD_L)
        buttons = ttk.Frame(win, padding=PAD_L)
        buttons.grid(row=2, column=0, sticky="e")

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(details)

        ttk.Button(buttons, text=t("ui.error.copy_details"), command=copy).pack(side="left", padx=(0, PAD))
        close = ttk.Button(buttons, text=t("ui.common.close"), command=win.destroy, default="active")
        close.pack(side="left")
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())
        close.focus_set()

    # ======================================================================
    # Environment: external tools and API key (checked off the UI thread)
    # ======================================================================

    def _check_environment(self):
        ffmpeg_missing = missing_tools("ffmpeg")
        mkv_missing = missing_tools("mkvtoolnix")
        key = False
        try:
            import core.translation_service  # noqa: F401  (loads .env)
            key = bool(os.getenv("GOOGLE_TRANSLATE_API_KEY"))
        except Exception as e:  # noqa: BLE001 - report any failure to the user
            logger.debug(f"Translation service unavailable: {e}")
        self._post(lambda: self._apply_environment(ffmpeg_missing, mkv_missing, key))

    def _apply_environment(self, ffmpeg_missing: list[str], mkv_missing: list[str], key: bool):
        self._missing = {"ffmpeg": ffmpeg_missing, "mkvtoolnix": mkv_missing}
        self._env_checked = True
        self._translation_key_available = key
        if key:
            self._translation_check.state(["!disabled"])
            self._translation_hint.configure(text="")
        else:
            self.merge_translation_var.set(False)
            self._translation_check.state(["disabled"])
            self._translation_hint.configure(text=t("ui.merge.translation_needs_key"))
        self._refresh_tool_banners()
        self._validate_shift()
        self._update_convert_hint(keep_result=True)

    def _refresh_tool_banners(self):
        missing = self._missing
        if missing["mkvtoolnix"]:
            self.extract_banner.show(t("ui.extract.banner_missing") + " " + install_hint("mkvtoolnix"),
                                     self._tool_banner_actions("mkvtoolnix"))
            self._bars["extract"].set_hint(t("ui.extract.hint_install"), "warning")
        else:
            self.extract_banner.hide()
            self._bars["extract"].set_hint(self._extract_hint)
        video = self.merge_video_var.get().strip()
        if missing["ffmpeg"] and video:
            self.merge_banner.show(t("ui.merge.banner_ffmpeg") + " " + install_hint("ffmpeg"),
                                   self._tool_banner_actions("ffmpeg"))
        else:
            self.merge_banner.hide()

    def _tool_banner_actions(self, group: str):
        return [(t("ui.tools.check_again"), self._recheck_tools),
                (t("ui.tools.locate"), lambda g=group: self._locate_tool_folder(g)),
                (t("ui.tools.download"), lambda g=group: self._open_download_page(g))]

    def _recheck_tools(self):
        self._missing = {"ffmpeg": missing_tools("ffmpeg"), "mkvtoolnix": missing_tools("mkvtoolnix")}
        self._refresh_tool_banners()
        found = [g for g, m in self._missing.items() if not m]
        self._set_status(t("ui.tools.found", names=", ".join(found)) if found else t("ui.tools.still_missing"))
        if not self._missing["ffmpeg"] and self.merge_video_var.get().strip():
            self._scan_video_tracks(quiet=True)

    def _locate_tool_folder(self, group: str):
        exe = "ffmpeg.exe" if group == "ffmpeg" else "mkvextract.exe"
        folder = filedialog.askdirectory(title=t("ui.tools.choose_folder", exe=exe),
                                         initialdir=self.settings.last_dir("tools"), parent=self.root)
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not folder_has_tools(folder, group):
            bin_dir = os.path.join(folder, "bin")
            if folder_has_tools(bin_dir, group):
                folder = bin_dir
            else:
                messagebox.showerror(t("ui.tools.not_found_title"), t("ui.tools.not_found", exe=exe, folder=folder),
                                     parent=self.root)
                return
        add_tool_dirs([folder])
        dirs = list(self.settings.get("tool_dirs", []) or [])
        if folder not in dirs:
            dirs.append(folder)
        self.settings.set("tool_dirs", dirs)
        self.settings.remember_path("tools", folder)
        self.settings.save()
        self._recheck_tools()

    def _open_download_page(self, group: str):
        import webbrowser
        webbrowser.open(DOWNLOAD_PAGES[group])

    # ======================================================================
    # File dialogs with remembered folders
    # ======================================================================

    def _ask_open(self, kind: str, title: str, filetypes, multiple: bool = False):
        opts = {"title": title, "filetypes": filetypes, "parent": self.root}
        initial = self.settings.last_dir(kind)
        if initial:
            opts["initialdir"] = initial
        if multiple:
            result = filedialog.askopenfilenames(**opts)
            paths = list(self.root.tk.splitlist(result)) if isinstance(result, str) else list(result or [])
            if paths:
                self.settings.remember_path(kind, paths[0])
            return paths
        path = filedialog.askopenfilename(**opts)
        if path:
            self.settings.remember_path(kind, path)
        return path

    def _ask_save(self, kind: str, title: str, filetypes, defaultextension: str, current: str = ""):
        opts = {"title": title, "filetypes": filetypes, "defaultextension": defaultextension,
                "parent": self.root}
        if current:
            opts["initialdir"] = str(Path(current).parent)
            opts["initialfile"] = Path(current).name
        elif self.settings.last_dir(kind):
            opts["initialdir"] = self.settings.last_dir(kind)
        path = filedialog.asksaveasfilename(**opts)
        if path:
            self.settings.remember_path(kind, path)
        return path

    def _ask_dir(self, kind: str, title: str):
        opts = {"title": title, "parent": self.root}
        initial = self.settings.last_dir(kind)
        if initial:
            opts["initialdir"] = initial
        path = filedialog.askdirectory(**opts)
        if path:
            self.settings.remember_path(kind, path)
        return path

    # ======================================================================
    # Background file analysis (debounced, never on the UI thread)
    # ======================================================================

    def _analyze_later(self, key: str, path: str, render: Callable[[dict[str, Any] | None], None],
                       delay: int = 250, extra: Callable[[Path, dict[str, Any]], None] | None = None):
        """Analyse a subtitle file shortly after its path stops changing.

        extra(path, info) may add more facts; it runs on the worker thread too.
        """
        job = self._analysis_after.pop(key, None)
        if job:
            self.root.after_cancel(job)
        gen = self._analysis_gen[key] = self._analysis_gen.get(key, 0) + 1
        path = (path or "").strip()
        if not path or not Path(path).is_file():
            render(None)
            return
        cached = self._cached_info(path)
        if cached and extra is None:
            render(cached)
            return

        def start():
            self._analysis_after.pop(key, None)
            render({"busy": True})

            def work():
                try:
                    info = dict(self._cached_info(path) or analyze_subtitle(Path(path)))
                    if extra is not None:
                        extra(Path(path), info)
                except Exception as e:  # noqa: BLE001 - report any failure to the user
                    info = {"error": str(e) or type(e).__name__}
                info["_mtime"] = self._mtime(path)

                def deliver():
                    self._file_info[path] = info
                    if self._analysis_gen.get(key) == gen:
                        render(info)
                self._post(deliver)

            threading.Thread(target=work, daemon=True).start()

        self._analysis_after[key] = self.root.after(delay, start)

    @staticmethod
    def _mtime(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _cached_info(self, path: str) -> dict[str, Any] | None:
        info = self._file_info.get(path)
        if info and info.get("_mtime") == self._mtime(path):
            return info
        return None

    @staticmethod
    def _render_chip(chip: InfoChip, info: dict[str, Any] | None, extra: str = ""):
        if info is None:
            chip.clear()
        elif info.get("busy"):
            chip.show(t("ui.common.reading_file"), "busy")
        elif info.get("error"):
            chip.show(describe_subtitle(info), "error")
        else:
            chip.show(describe_subtitle(info) + extra, "ok")

    def _detect_file_language(self, path: Path) -> str:
        """Detect language of a subtitle file (display name, e.g. 'Chinese')."""
        try:
            from core.language_detection import LanguageDetector
            lang = LanguageDetector.detect_language_from_filename(str(path))
            if lang == 'unknown':
                lang = LanguageDetector.detect_subtitle_language(path)
            return {'zh': 'Chinese', 'en': 'English', 'ja': 'Japanese', 'ko': 'Korean'}.get(lang, lang.upper())
        except (OSError, ValueError, UnicodeDecodeError):
            return ""

    # ======================================================================
    # Common widgets
    # ======================================================================

    def _path_row(self, parent, row: int, var: tk.StringVar, browse: Callable,
                  label: str | None = None, preview: bool = False, extra=(),
                  drop: Callable[[list[str]], None] | None = None):
        """label | entry (stretches) | Browse... | [Preview] | extras

        drop(paths) handles files dropped on the row (defaults to filling the field).
        """
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew")
        col = 0
        if label:
            ttk.Label(frame, text=label).grid(row=0, column=col, sticky="w", padx=(0, PAD))
            col += 1
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=0, column=col, sticky="ew")
        frame.columnconfigure(col, weight=1)
        col += 1

        def show_end(*_):
            # Long paths: keep the file name (the end) visible, unless the user is typing.
            if entry.winfo_exists() and self.root.focus_get() is not entry:
                entry.icursor(tk.END)
                entry.xview_moveto(1.0)

        var.trace_add("write", lambda *a: self._show_entry_end_later(show_end))
        entry.bind("<Configure>", show_end, add="+")
        entry.bind("<FocusOut>", show_end, add="+")
        ttk.Button(frame, text=t("ui.common.browse"), command=browse).grid(row=0, column=col, padx=(PAD_S + 2, 0))
        col += 1
        if preview:
            ttk.Button(frame, text=t("ui.common.preview"),
                       command=lambda: self._show_subtitle_preview(var.get())).grid(row=0, column=col, padx=(PAD_S, 0))
            col += 1
        for text, cmd in extra:
            ttk.Button(frame, text=text, command=cmd).grid(row=0, column=col, padx=(PAD_S, 0))
            col += 1
        handler = drop or (lambda paths: var.set(paths[0]) if paths else None)
        self._drop_rows.append((entry, handler))
        return frame, entry

    def _show_entry_end_later(self, show_end: Callable[[], None]):
        """Run show_end once Tk is idle (one shared idle job, cancelled on close)."""
        self._end_pending.append(show_end)
        if self._end_job is None and not self._closing:
            self._end_job = self.root.after_idle(self._flush_entry_ends)

    def _flush_entry_ends(self):
        self._end_job = None
        pending, self._end_pending = self._end_pending, []
        for fn in pending:
            try:
                fn()
            except tk.TclError:
                pass  # the entry was destroyed (language switch)

    def _section(self, parent, row: int, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=(PAD_L, PAD_S + 2, PAD_L, PAD_L - 2))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD))
        frame.columnconfigure(0, weight=1)
        return frame

    @staticmethod
    def _caption(parent, text: str = "", width: int = 300, **kw) -> ttk.Label:
        """Grey helper text that re-wraps to the width it is given (put it in a weighted column)."""
        kw.setdefault("style", "Caption.TLabel")
        label = ttk.Label(parent, text=text, justify="left", wraplength=width, **kw)
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(120, e.width)))
        return label

    @staticmethod
    def _intro(parent, row: int, text: str):
        label = ttk.Label(parent, text=text, style="Caption.TLabel", justify="left", wraplength=560)
        label.grid(row=row, column=0, sticky="ew", pady=(0, PAD))
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(200, e.width)))
        return label

    # ======================================================================
    # Merge tab
    # ======================================================================

    def _create_merge_tab(self):
        """Create the Merge Subtitles tab - primary function."""
        tab, body = self._new_tab("merge", t('gui.tab_merge').strip())
        self.merge_tab = tab
        self.scanned_tracks = []
        self.external_subs_found = []
        self.language_options = [_lang_label(c) for c in LANGUAGE_CHOICES]

        self._intro(body, 0, t("ui.merge.intro"))

        # --- quick start / drop zone ---------------------------------------
        quick = ttk.Frame(body, style="Drop.TFrame", padding=(PAD, PAD_S + 2))
        quick.grid(row=1, column=0, sticky="ew", pady=(0, PAD))
        quick.columnconfigure(2, weight=1)
        self.merge_drop_zone = quick
        ttk.Button(quick, text=t("ui.merge.add_files"), command=self._add_subtitle_files).grid(
            row=0, column=0, sticky="w")
        ttk.Button(quick, text=t("ui.merge.choose_video"), command=self._browse_merge_video).grid(
            row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self.merge_drop_label = self._caption(
            quick, t("ui.merge.drop_hint") if self._dnd else t("ui.merge.add_hint"), style="Drop.TLabel")
        self.merge_drop_label.grid(row=0, column=2, sticky="ew", padx=(PAD, 0))

        # --- video ----------------------------------------------------------
        video_frame = self._section(body, 2, t("ui.merge.video_section"))
        self.merge_video_frame = video_frame
        self.merge_video_var = tk.StringVar()
        self.merge_video_var.trace_add('write', lambda *a: self._on_video_changed())
        self._path_row(video_frame, 0, self.merge_video_var, self._browse_merge_video,
                       extra=[(t("ui.merge.scan_tracks"), self._scan_video_tracks)], drop=self._on_merge_drop)
        self.tracks_frame = ttk.Frame(video_frame)
        self.tracks_frame.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))
        self.tracks_label = ttk.Label(self.tracks_frame, text=t("ui.merge.no_video"), style='Caption.TLabel',
                                      wraplength=560, justify="left")
        self.tracks_label.pack(anchor='w', fill=tk.X)
        self.tracks_label.bind("<Configure>", lambda e: self.tracks_label.configure(wraplength=max(200, e.width)))
        self.merge_banner = Banner(video_frame, row=2, column=0, sticky="ew", pady=(PAD, 0))

        # --- tracks ---------------------------------------------------------
        self._create_track_section(body, 3, "chinese", t("ui.merge.track1"), "Chinese")
        self._create_track_section(body, 4, "english", t("ui.merge.track2"), "English")

        # --- options --------------------------------------------------------
        options = self._section(body, 5, t("ui.merge.options"))
        row0 = ttk.Frame(options)
        row0.grid(row=0, column=0, sticky="ew")
        ttk.Label(row0, text=t("ui.merge.output_format")).pack(side=tk.LEFT)
        self.merge_format_var = tk.StringVar(value=self.settings.get("merge.format", "srt"))
        fmt = ttk.Combobox(row0, textvariable=self.merge_format_var, values=['srt', 'ass'],
                           width=5, state='readonly')
        fmt.pack(side=tk.LEFT, padx=(PAD_S, PAD_L + PAD))
        self.merge_format_var.trace_add('write', lambda *a: self._update_merge_hint())
        ttk.Label(row0, text=t("ui.merge.on_top")).pack(side=tk.LEFT)
        self.merge_top_var = tk.StringVar(value=self.settings.get("merge.top", "first"))
        ttk.Radiobutton(row0, text=t("ui.merge.track1_short"), variable=self.merge_top_var,
                        value="first").pack(side=tk.LEFT, padx=(PAD_S, 0))
        ttk.Radiobutton(row0, text=t("ui.merge.track2_short"), variable=self.merge_top_var,
                        value="second").pack(side=tk.LEFT, padx=(PAD, 0))
        ttk.Button(row0, text=t("ui.merge.swap"), command=self._swap_merge_files).pack(
            side=tk.LEFT, padx=(PAD_L, 0))

        self.merge_autosync_var = tk.BooleanVar(value=bool(self.settings.get("merge.autosync", True)))
        ttk.Checkbutton(options, text=t("ui.merge.autosync"),
                        variable=self.merge_autosync_var).grid(row=1, column=0, sticky="w", pady=(PAD, 0))

        adv = Collapsible(options, t("ui.merge.advanced"), opened=bool(self.settings.get("merge.advanced_open")),
                          on_toggle=lambda o: self.settings.set("merge.advanced_open", o))
        adv.grid(row=2, column=0, sticky="ew", pady=(PAD_S, 0))
        self.merge_advanced = adv
        self.merge_autoalign_var = tk.BooleanVar(value=bool(self.settings.get("merge.autoalign", False)))
        ttk.Checkbutton(adv.body, text=t("ui.merge.autoalign"),
                        variable=self.merge_autoalign_var).grid(row=0, column=0, columnspan=3, sticky="w")
        self.merge_translation_var = tk.BooleanVar(value=False)
        self._translation_check = ttk.Checkbutton(adv.body, text=t("ui.merge.translation"),
                                                  variable=self.merge_translation_var)
        self._translation_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(PAD_S, 0))
        self._translation_hint = self._caption(adv.body)
        self._translation_hint.grid(row=2, column=0, columnspan=3, sticky="ew", padx=(PAD_L + PAD, 0))
        ttk.Label(adv.body, text=t("ui.merge.strictness")).grid(row=3, column=0, sticky="w", pady=(PAD_S, 0))
        self.merge_threshold_var = tk.StringVar(value=f"{float(self.settings.get('merge.threshold', 0.8)):g}")
        ttk.Spinbox(adv.body, textvariable=self.merge_threshold_var, from_=THRESHOLD_MIN, to=THRESHOLD_MAX,
                    increment=0.05, width=6, format="%.2f").grid(row=3, column=1, sticky="w",
                                                                  padx=(PAD_S, 0), pady=(PAD_S, 0))
        adv.body.columnconfigure(2, weight=1)
        self._caption(adv.body, t("ui.merge.strictness_hint", low=THRESHOLD_MIN, high=THRESHOLD_MAX),
                      width=200).grid(row=3, column=2, sticky="ew", padx=(PAD, 0), pady=(PAD_S, 0))

        # --- output ---------------------------------------------------------
        output = self._section(body, 6, t("ui.common.output"))
        self.merge_output_var = tk.StringVar()
        self.merge_output_var.trace_add('write', lambda *a: self._update_merge_hint())
        self._path_row(output, 0, self.merge_output_var, self._browse_merge_output, label=t("ui.common.save_as"))
        self.merge_output_hint = self._caption(output, width=500)
        self.merge_output_hint.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        bar = self._add_action_bar("merge", t("ui.merge.button"), self._execute_merge, t("ui.merge.hint_start"))
        self.merge_btn = bar.button
        # Old attribute names, kept for scripts that poke at the GUI.
        self.merge_progress = bar.progressbar
        self.merge_progress_label = bar.message

        self._update_chinese_source()
        self._update_english_source()
        self._update_merge_hint()

    def _create_track_section(self, body, row: int, slot: str, title: str, default_lang: str):
        frame = self._section(body, row, title)
        radios = ttk.Frame(frame)
        radios.grid(row=0, column=0, sticky="w")
        source_var = tk.StringVar(value="auto")
        update = self._update_chinese_source if slot == "chinese" else self._update_english_source
        for i, (text, value) in enumerate(((t("ui.merge.src_auto"), "auto"), (t("ui.merge.src_embedded"), "embedded"),
                                           (t("ui.merge.src_file"), "external"))):
            ttk.Radiobutton(radios, text=text, variable=source_var, value=value, command=update).pack(
                side=tk.LEFT, padx=(0 if i == 0 else PAD_L + PAD, 0))

        auto_frame = ttk.Frame(frame)
        auto_frame.columnconfigure(2, weight=1)
        ttk.Label(auto_frame, text=t("ui.merge.language")).grid(row=0, column=0, sticky="w")
        auto_lang_var = tk.StringVar(value=_lang_label(default_lang))
        ttk.Combobox(auto_frame, textvariable=auto_lang_var, values=self.language_options,
                     width=12, state='readonly').grid(row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self._caption(auto_frame, t("ui.merge.auto_hint")).grid(row=0, column=2, sticky="ew", padx=(PAD, 0))

        track_frame = ttk.Frame(frame)
        track_frame.columnconfigure(1, weight=1)
        ttk.Label(track_frame, text=t("ui.merge.track")).grid(row=0, column=0, sticky="w")
        track_var = tk.StringVar()
        combo = ttk.Combobox(track_frame, textvariable=track_var, width=45, state='readonly')
        combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(track_frame, text=t("ui.common.preview"),
                   command=lambda: self._preview_embedded_track(slot)).grid(row=0, column=2, padx=(PAD_S, 0))

        file_var = tk.StringVar()
        file_frame, _ = self._path_row(frame, 1, file_var, lambda: self._browse_sub_file(slot),
                                       label=t("ui.merge.file"), preview=True,
                                       drop=lambda paths, s=slot: self._drop_on_track(s, paths))
        file_frame.grid_remove()
        chip = InfoChip(frame)
        file_var.trace_add('write', lambda *a: self._on_track_file_changed(slot))

        setattr(self, f"{slot}_source_var", source_var)
        setattr(self, f"{slot}_auto_frame", auto_frame)
        setattr(self, f"{slot}_auto_lang_var", auto_lang_var)
        setattr(self, f"{slot}_track_frame", track_frame)
        setattr(self, f"{slot}_track_var", track_var)
        setattr(self, f"{slot}_track_combo", combo)
        setattr(self, f"{slot}_file_frame", file_frame)
        setattr(self, f"{slot}_file_var", file_var)
        setattr(self, f"{slot}_chip", chip)

    def _update_track_source(self, slot: str):
        source = getattr(self, f"{slot}_source_var").get()
        auto_f = getattr(self, f"{slot}_auto_frame")
        track_f = getattr(self, f"{slot}_track_frame")
        file_f = getattr(self, f"{slot}_file_frame")
        chip = getattr(self, f"{slot}_chip")
        for f in (auto_f, track_f, file_f):
            f.grid_remove()
        target = {"auto": auto_f, "embedded": track_f, "external": file_f}.get(source)
        if target is not None:
            target.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        if source == "external":
            chip.grid(row=2, column=0, sticky="ew", pady=(PAD_S, 0))
        else:
            chip.grid_remove()
        self._update_merge_hint()

    def _update_chinese_source(self):
        """Update Track 1 subtitle source UI."""
        self._update_track_source("chinese")

    def _update_english_source(self):
        """Update Track 2 subtitle source UI."""
        self._update_track_source("english")

    def _on_track_file_changed(self, slot: str):
        path = getattr(self, f"{slot}_file_var").get()
        chip = getattr(self, f"{slot}_chip")

        def render(info):
            extra = ""
            if info and not info.get("busy") and info.get("bilingual_ratio", 0) > 0.3:
                extra = "  ⚠ " + t("ui.merge.already_bilingual")
            self._render_chip(chip, info, extra)
            self._update_merge_hint(keep_result=True)

        self._analyze_later(f"merge-{slot}", path, render)
        self._update_merge_hint()

    # Kept for compatibility
    def _on_chinese_file_changed(self):
        self._on_track_file_changed("chinese")

    def _on_english_file_changed(self):
        self._on_track_file_changed("english")

    def _predicted_merge_output(self) -> Path | None:
        """Where Merge will save when "Save as" is empty and two files are set (None if unknown)."""
        video = self.merge_video_var.get().strip()
        s1, s2 = self.chinese_source_var.get(), self.english_source_var.get()
        f1 = self.chinese_file_var.get().strip() if s1 == "external" else ""
        f2 = self.english_file_var.get().strip() if s2 == "external" else ""
        if not (f1 and f2) or (video and (s1 != "external" or s2 != "external")):
            return None
        i1, i2 = self._cached_info(f1), self._cached_info(f2)
        if not (i1 and i2) or i1.get("error") or i2.get("error"):
            return None
        try:
            from core.language_detection import LanguageDetector
            return LanguageDetector.generate_bilingual_filename(
                Path(f1), i1.get("language", "unknown"), i2.get("language", "unknown"),
                self.merge_format_var.get() or "srt")
        except Exception:  # noqa: BLE001 - only a hint; the merger decides
            return None

    def _update_merge_hint(self, keep_result: bool | None = None):
        """Explain where the result will be saved and whether Merge is ready.

        keep_result: background updates (file analysis, automatic track order)
        must not wipe a result or message the user has not seen yet.
        """
        if not hasattr(self, "merge_output_hint") or "merge" not in self._bars:
            return
        if keep_result is None:
            keep_result = getattr(self, "_merge_hint_keep", False)
        video = self.merge_video_var.get().strip()
        s1, s2 = self.chinese_source_var.get(), self.english_source_var.get()
        f1 = self.chinese_file_var.get().strip() if s1 == "external" else ""
        f2 = self.english_file_var.get().strip() if s2 == "external" else ""
        custom = self.merge_output_var.get().strip()
        predicted = None if custom else self._predicted_merge_output()

        if custom:
            self.merge_output_hint.configure(text="")
        elif predicted:
            self.merge_output_hint.configure(
                text=t("ui.merge.out_predicted", name=predicted.name, folder=str(predicted.parent)))
        elif video:
            self.merge_output_hint.configure(text=t("ui.merge.out_next_to_video"))
        else:
            self.merge_output_hint.configure(text=t("ui.merge.out_next_to_track1"))

        bar = self._bars["merge"]
        if bar.busy:
            return
        if (s1 == "external" and not f1) or (s2 == "external" and not f2):
            hint = t("ui.merge.hint_choose_file")
        elif not video and not f1 and not f2:
            hint = t("ui.merge.hint_start")
        else:
            target = Path(custom).name if custom else (predicted.name if predicted else "")
            hint = t("ui.merge.hint_ready_named", name=target) if target else t("ui.merge.hint_ready")
        bar.set_hint(hint, keep_result=keep_result)

    def _add_subtitle_files(self):
        """Pick one or two subtitle files; assign each to a track by detected language."""
        paths = self._ask_open("subtitle", t("ui.merge.dlg_add_files"), _subtitle_types(), multiple=True)
        if paths:
            self._add_subtitle_paths(paths)

    def _add_subtitle_paths(self, paths: list[str]):
        """Put one or two subtitle files on the tracks; the language is checked in the background.

        Both files are placed at once (Track 1 = first); when detection finds
        the CJK file on Track 2 the tracks are swapped, so the UI never waits.
        """
        paths = [str(p) for p in paths]
        ignored = paths[2:]
        paths = paths[:2]
        if not paths:
            return
        if len(paths) == 1:
            self._assign_subtitle(paths[0])
        else:
            for slot, path in zip(("chinese", "english"), paths):
                getattr(self, f"{slot}_source_var").set("external")
                getattr(self, f"{slot}_file_var").set(path)
            self._update_chinese_source()
            self._update_english_source()
            self._order_tracks_by_language(paths)
        bar = self._bars["merge"]
        bar.reset()
        if ignored:
            bar.finish("info", t("ui.merge.extra_ignored", n=len(ignored),
                                 names=", ".join(Path(p).name for p in ignored[:3])))

    def _order_tracks_by_language(self, paths: list[str]):
        """Swap the two tracks if only Track 2 turns out to be Chinese/Japanese/Korean."""
        gen = self._analysis_gen["merge-order"] = self._analysis_gen.get("merge-order", 0) + 1

        def work():
            langs = [self._detect_file_language(Path(p)) for p in paths]

            def apply():
                if self._analysis_gen.get("merge-order") != gen:
                    return
                current = [self.chinese_file_var.get(), self.english_file_var.get()]
                cjk = {'Chinese', 'Japanese', 'Korean'}
                if current == paths and langs[1] in cjk and langs[0] not in cjk:
                    self._merge_hint_keep = True
                    try:
                        self.chinese_file_var.set(paths[1])
                        self.english_file_var.set(paths[0])
                    finally:
                        self._merge_hint_keep = False
            self._post(apply)

        threading.Thread(target=work, daemon=True).start()

    def _assign_subtitle(self, path: str, lang: str | None = None):
        """Put one subtitle file on a free track (Chinese/Japanese/Korean prefers Track 1)."""
        slot = None
        if lang is None:
            # Fill an empty external slot first so a second file does not overwrite the first.
            for candidate in ("chinese", "english"):
                if not (getattr(self, f"{candidate}_source_var").get() == "external"
                        and getattr(self, f"{candidate}_file_var").get()):
                    slot = candidate
                    break
            slot = slot or "chinese"
            getattr(self, f"{slot}_file_var").set(path)
            getattr(self, f"{slot}_source_var").set("external")
            self._update_chinese_source()
            self._update_english_source()
            self._refine_single_assignment(slot, path)
            return
        slot = "chinese" if lang in ('Chinese', 'Japanese', 'Korean') else "english"
        other = "english" if slot == "chinese" else "chinese"
        if (getattr(self, f"{slot}_source_var").get() == "external" and getattr(self, f"{slot}_file_var").get()
                and not (getattr(self, f"{other}_source_var").get() == "external"
                         and getattr(self, f"{other}_file_var").get())):
            slot = other
        getattr(self, f"{slot}_file_var").set(path)
        getattr(self, f"{slot}_source_var").set("external")
        self._update_chinese_source()
        self._update_english_source()

    def _refine_single_assignment(self, slot: str, path: str):
        """After placing one file, move it to the other track if its language says so."""
        gen = self._analysis_gen["merge-order"] = self._analysis_gen.get("merge-order", 0) + 1

        def work():
            lang = self._detect_file_language(Path(path))

            def apply():
                if self._analysis_gen.get("merge-order") != gen:
                    return
                if getattr(self, f"{slot}_file_var").get() != path:
                    return
                want = "chinese" if lang in ('Chinese', 'Japanese', 'Korean') else "english"
                other_file = getattr(self, f"{want}_file_var").get()
                other_used = getattr(self, f"{want}_source_var").get() == "external" and other_file
                if want != slot and not other_used:
                    self._merge_hint_keep = True
                    try:
                        getattr(self, f"{slot}_file_var").set("")
                        getattr(self, f"{slot}_source_var").set("auto")
                        getattr(self, f"{want}_file_var").set(path)
                        getattr(self, f"{want}_source_var").set("external")
                        self._update_chinese_source()
                        self._update_english_source()
                    finally:
                        self._merge_hint_keep = False
            self._post(apply)

        threading.Thread(target=work, daemon=True).start()

    def _drop_on_track(self, slot: str, paths: list[str]):
        """Files dropped on a track's file field: the first goes to that track."""
        subs = [p for p in paths if Path(p).suffix.lower() in SUBTITLE_EXTENSIONS] or paths
        if not subs:
            return
        if len(subs) > 1:
            self._add_subtitle_paths(subs)
            return
        getattr(self, f"{slot}_file_var").set(subs[0])
        getattr(self, f"{slot}_source_var").set("external")
        self._update_track_source(slot)

    def _on_merge_drop(self, paths: list[str]):
        """Files dropped anywhere on the Merge tab: videos and subtitles go where they belong."""
        videos = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
        subs = [p for p in paths if Path(p).suffix.lower() in SUBTITLE_EXTENSIONS]
        others = [p for p in paths if p not in videos and p not in subs]
        if videos:
            self.merge_video_var.set(videos[0])
        if subs:
            self._add_subtitle_paths(subs)
        if others and not (videos or subs):
            self._invalid("merge", t("ui.drop.unsupported", name=Path(others[0]).name))
        self._select_tab("merge")

    def _swap_merge_files(self):
        """Swap all settings between Track 1 and Track 2."""
        self._analysis_gen["merge-order"] = self._analysis_gen.get("merge-order", 0) + 1
        for name in ("source_var", "auto_lang_var", "track_var", "file_var"):
            a, b = getattr(self, f"chinese_{name}"), getattr(self, f"english_{name}")
            va, vb = a.get(), b.get()
            a.set(vb)
            b.set(va)
        self._update_chinese_source()
        self._update_english_source()

    def _on_video_changed(self):
        """Video path changed: look for subtitles next to it and inside it (debounced)."""
        job = self._analysis_after.pop("merge-video", None)
        if job:
            self.root.after_cancel(job)
        self._update_merge_hint()
        video_path = self.merge_video_var.get().strip()
        if not video_path:
            self.tracks_label.config(text=t("ui.merge.no_video"))
            self.merge_banner.hide()
            return
        self._analysis_after["merge-video"] = self.root.after(
            300, lambda: self._scan_video_tracks(quiet=True))

    def _find_external_subs(self, video_path: Path):
        """Find external subtitle files next to the video (worker-safe: no Tk calls)."""
        found = []
        for ext in ['.srt', '.ass', '.ssa', '.vtt']:
            for sub_file in video_path.parent.glob(f"{glob_escape(video_path.stem)}*{ext}"):
                if sub_file.is_file():
                    found.append(sub_file)
        return found

    def _scan_video_tracks(self, quiet: bool = False):
        """Scan the video for embedded subtitle tracks and nearby subtitle files."""
        self._analysis_after.pop("merge-video", None)
        video_path = self.merge_video_var.get().strip()
        if not video_path:
            if not quiet:
                self._invalid("merge", t("ui.merge.choose_video_first"))
            return
        if not Path(video_path).is_file():
            self.tracks_label.config(text=t("ui.merge.video_not_found_short"))
            if not quiet:
                self._invalid("merge", t("ui.merge.video_not_found", path=video_path))
            return

        self._missing["ffmpeg"] = missing_tools("ffmpeg")
        ffmpeg_missing = bool(self._missing["ffmpeg"])
        self._refresh_tool_banners()
        self.tracks_label.config(text=t("ui.merge.looking"))
        self._set_status(t("ui.merge.status_scanning"), "merge")
        gen = self._analysis_gen["merge-video"] = self._analysis_gen.get("merge-video", 0) + 1

        def do_scan():
            external = self._find_external_subs(Path(video_path))
            tracks, error = [], None
            if not ffmpeg_missing:
                try:
                    from core.video_containers import VideoContainerHandler
                    tracks = VideoContainerHandler().list_subtitle_tracks(Path(video_path))
                except Exception as e:  # noqa: BLE001 - report any failure to the user
                    error = str(e)
            self._post(lambda: self._apply_scan(gen, video_path, tracks, external, ffmpeg_missing, error))

        threading.Thread(target=do_scan, daemon=True).start()

    def _apply_scan(self, gen, video_path, tracks, external, ffmpeg_missing, error):
        if self._analysis_gen.get("merge-video") != gen:
            return
        self.scanned_tracks = tracks
        self.external_subs_found = external
        labels, chinese_tracks, english_tracks = [], [], []
        for tr in tracks:
            lang = tr.language or t("ui.lang.unknown")
            title = f" - {tr.title}" if tr.title else ""
            label = f"{t('ui.merge.track_label', id=tr.track_id)}: {lang}{title} ({tr.codec})"
            labels.append(label)
            lang_lower = (tr.language or "").lower()
            if any(c in lang_lower for c in ['chi', 'zh', 'cn', 'jpn', 'ja', 'kor', 'ko']):
                chinese_tracks.append(label)
            elif any(c in lang_lower for c in ['eng', 'en']):
                english_tracks.append(label)
        self._scan_track_ids = {label: str(tr.track_id) for label, tr in zip(labels, tracks)}
        self.chinese_track_combo['values'] = labels
        self.english_track_combo['values'] = labels
        if chinese_tracks:
            self.chinese_track_var.set(chinese_tracks[0])
        elif labels:
            self.chinese_track_var.set(labels[0])
        if english_tracks:
            self.english_track_var.set(english_tracks[0])
        elif len(labels) > 1:
            self.english_track_var.set(labels[1])
        elif labels:
            self.english_track_var.set(labels[0])

        parts = []
        if ffmpeg_missing:
            parts.append(t("ui.merge.scan_no_ffmpeg"))
        elif error:
            parts.append(t("ui.merge.scan_error", error=error))
        elif tracks:
            parts.append(t("ui.merge.scan_found", n=len(tracks)))
        else:
            parts.append(t("ui.merge.scan_none"))
        if external:
            names = ", ".join(f.name for f in external[:3])
            more = t("ui.merge.scan_more", n=len(external) - 3) if len(external) > 3 else ""
            parts.append(t("ui.merge.scan_external", n=len(external), names=names) + more)
        self.tracks_label.config(text=" · ".join(parts))
        self._set_status(t('gui.status_ready'), "merge")
        self._update_merge_hint()

    @staticmethod
    def _track_id_from_label(label: str) -> str | None:
        """'Track 3: eng (subrip)' (in any UI language) -> '3'."""
        if not label:
            return None
        head = label.split(":")[0]
        digits = "".join(ch for ch in head if ch.isdigit())
        return digits or None

    def _preview_dir_path(self) -> Path:
        """One temp folder per session for extracted preview tracks (reused, not piled up in %TEMP%)."""
        if self._preview_dir is None or not self._preview_dir.is_dir():
            import tempfile
            self._preview_dir = Path(tempfile.mkdtemp(prefix="biss-preview-"))
        return self._preview_dir

    def _preview_embedded_track(self, track_type: str):
        """Preview an embedded subtitle track by extracting it to a temp file."""
        key = "merge"
        if self._bars[key].busy:
            return
        video_path = self.merge_video_var.get().strip()
        if not video_path or not Path(video_path).exists():
            self._invalid(key, t("ui.merge.choose_video_first"))
            return
        track_label = getattr(self, f"{track_type}_track_var").get()
        if not track_label:
            self._invalid(key, t("ui.merge.choose_track_first"))
            return
        track_id = self._track_id_from_label(track_label)
        folder = self._preview_dir_path()

        def work(cancel):
            from core.video_containers import VideoContainerHandler
            handler = VideoContainerHandler()
            tracks = handler.list_subtitle_tracks(Path(video_path))
            track = next((tr for tr in tracks if str(tr.track_id) == track_id), None)
            if track is None:
                raise RuntimeError(t("ui.merge.track_missing", id=track_id))
            suffix = '.ass' if (track.codec or '').lower() in ('ass', 'ssa') else '.srt'
            target = folder / f"track{track_id}{suffix}"
            result = handler.extract_subtitle_track(Path(video_path), track, target)
            if not result or not Path(result).exists():
                raise RuntimeError(t("ui.merge.track_extract_failed"))
            return str(result)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok:
                self._fail(key, t("ui.merge.preview_failed"), result)
                return
            bar.reset()
            self._set_status(t('gui.status_ready'), key)
            self._show_subtitle_preview(result)

        self._run_task(key, t("ui.merge.extracting_preview", id=track_id), work, done)

    def _browse_merge_video(self):
        path = self._ask_open("video", t("ui.dlg.select_video"), _video_types())
        if path:
            self.merge_video_var.set(path)

    def _browse_merge_output(self):
        fmt = self.merge_format_var.get() or "srt"
        types = [(t("ui.ft.srt"), "*.srt"), (t("ui.ft.ass"), "*.ass"), (t("ui.ft.all"), "*.*")]
        if fmt == "ass":
            types = [types[1], types[0], types[2]]
        path = self._ask_save("output", t("ui.merge.dlg_save"), types, f".{fmt}",
                              current=self.merge_output_var.get().strip())
        if path:
            self.merge_output_var.set(path)
            ext = Path(path).suffix.lower().lstrip(".")
            if ext in ("srt", "ass"):
                self.merge_format_var.set(ext)

    def _browse_sub_file(self, lang_type: str):
        """Browse for the Track 1 ('chinese') or Track 2 ('english') subtitle file."""
        title = t("ui.merge.dlg_track1") if lang_type == 'chinese' else t("ui.merge.dlg_track2")
        path = self._ask_open("subtitle", title, _subtitle_types())
        if path:
            getattr(self, f"{lang_type}_file_var").set(path)

    def _execute_merge(self):
        """Validate on the UI thread, then merge on a worker thread."""
        key = "merge"
        if self._bars[key].busy:
            return
        video_path = self.merge_video_var.get().strip()
        chinese_source = self.chinese_source_var.get()
        english_source = self.english_source_var.get()

        paths: dict[str, Path | None] = {}
        tracks: dict[str, str | None] = {}
        for slot, name, source in (("chinese", t("ui.merge.track1_short"), chinese_source),
                                   ("english", t("ui.merge.track2_short"), english_source)):
            paths[slot] = None
            tracks[slot] = None
            if source == "external":
                p = getattr(self, f"{slot}_file_var").get().strip()
                if not p:
                    self._invalid(key, t("ui.merge.err_no_file", track=name))
                    return
                if not Path(p).is_file():
                    self._invalid(key, t("ui.merge.err_file_missing", track=name, path=p))
                    return
                paths[slot] = Path(p)
            elif source == "embedded":
                if not video_path:
                    self._invalid(key, t("ui.merge.err_embedded_no_video", track=name))
                    return
                tracks[slot] = self._track_id_from_label(getattr(self, f"{slot}_track_var").get())

        if chinese_source == "auto" and english_source == "auto" and not video_path:
            self._invalid(key, t("ui.merge.hint_start"))
            return
        if video_path and not Path(video_path).is_file():
            self._invalid(key, t("ui.merge.video_not_found", path=video_path))
            return
        if (paths["chinese"] or paths["english"]) and not (paths["chinese"] and paths["english"]) and not video_path:
            self._invalid(key, t("ui.merge.err_one_file"))
            return
        try:
            threshold = parse_threshold(self.merge_threshold_var.get())
        except ValueError as e:
            if not self.merge_advanced.opened:
                self.merge_advanced.toggle()
            self._invalid(key, str(e))
            return

        output_path = self.merge_output_var.get().strip() or None
        output_format = self.merge_format_var.get()
        if output_path:
            ext = Path(output_path).suffix.lower().lstrip(".")
            if ext in ("srt", "ass"):
                output_format = ext
            else:
                output_path = str(Path(output_path).with_suffix(f".{output_format}"))
        # Ask before replacing a file we can name now; names chosen by the merger are asked later.
        known_target = Path(output_path) if output_path else self._predicted_merge_output()
        confirmed: set[str] = set()
        if known_target is not None and known_target.exists():
            if not self._confirm_replace(known_target):
                self._bars[key].finish("cancelled", t("ui.merge.kept_existing", name=known_target.name))
                return
            confirmed.add(os.path.normcase(str(known_target)))
        options = {
            "auto_align": self.merge_autoalign_var.get(),
            "use_translation": self.merge_translation_var.get() and self._translation_key_available,
            "alignment_threshold": threshold,
            "enable_mixed_realignment": self.merge_autosync_var.get(),
            "top_language": self.merge_top_var.get(),
        }
        auto_langs = {"chinese": _lang_choice(self.chinese_auto_lang_var.get()) if chinese_source == "auto" else None,
                      "english": _lang_choice(self.english_auto_lang_var.get()) if english_source == "auto" else None}
        bar = self._bars[key]
        friendly = {"Finding Chinese subtitle": t("ui.merge.step_find1"),
                    "Finding English subtitle": t("ui.merge.step_find2"),
                    "Merging subtitles": t("ui.merge.step_merge"),
                    "Writing output": t("ui.merge.step_write"),
                    "Complete": t("ui.merge.step_done")}

        def work(cancel: threading.Event):
            from processors.merger import BilingualMerger, MergeCancelled

            # 1. Warn about inputs that are already bilingual (asked on the UI thread).
            for p in (paths["chinese"], paths["english"]):
                if not p:
                    continue
                info = self._cached_info(str(p)) or analyze_subtitle(p)
                ratio = info.get("bilingual_ratio", 0) or 0
                if ratio > 0.3:
                    proceed = self._call_in_main(lambda p=p, r=ratio: messagebox.askyesno(
                        t("ui.merge.bilingual_title"),
                        t("ui.merge.bilingual_body", name=p.name, ratio=f"{r:.0%}"), parent=self.root), cancel)
                    if not proceed:
                        return {"declined": True}

            # 2. Honour the "Language" choice of Auto-detect tracks.
            if video_path:
                wanted = {slot: lang for slot, lang in auto_langs.items()
                          if lang and lang != ("Chinese" if slot == "chinese" else "English")}
                if wanted:
                    try:
                        from core.video_containers import VideoContainerHandler
                        found = VideoContainerHandler().list_subtitle_tracks(Path(video_path))
                    except Exception as e:  # noqa: BLE001 - report any failure to the user
                        found = []
                        logger.warning(f"Could not list tracks for language choice: {e}")
                    for slot, lang in wanted.items():
                        tid = pick_track_for_language(found, lang)
                        if tid is not None:
                            tracks[slot] = tid
                            logger.info(f"{'Track 1' if slot == 'chinese' else 'Track 2'}: using track {tid} ({lang})")
                        elif lang != "Any":
                            logger.warning(f"No {lang} track found in the video; choosing automatically.")

            def progress(step: str, current: int, total: int):
                if cancel.is_set():
                    raise MergeCancelled()
                pct = int(current / total * 100) if total else None
                text = f"{friendly.get(step, step)}…"
                self._post(lambda: bar.progress(text, pct))

            def confirm_overwrite(target: Path) -> bool:
                if os.path.normcase(str(target)) in confirmed:
                    return True
                return bool(self._call_in_main(lambda: self._confirm_replace(target), cancel))

            logger.info(f"Starting merge operation for: {video_path or 'external files'}")
            merger = BilingualMerger(progress_callback=progress, confirm_overwrite=confirm_overwrite, **options)
            out = Path(output_path) if output_path else None
            try:
                if video_path and (chinese_source != "external" or english_source != "external"):
                    ok = merger.process_video(video_path=Path(video_path), chinese_sub=paths["chinese"],
                                              english_sub=paths["english"], output_format=output_format,
                                              output_path=out, chinese_track=tracks["chinese"],
                                              english_track=tracks["english"])
                else:
                    progress("Merging subtitles", 1, 2)
                    ok = merger.merge_subtitle_files(chinese_path=paths["chinese"], english_path=paths["english"],
                                                     output_path=out, output_format=output_format)
                    if ok:
                        progress("Complete", 2, 2)
            except MergeCancelled as e:
                if getattr(e, "overwrite_declined", False):
                    return {"kept": merger.last_output_path}
                return {"cancelled": True}
            return {"success": ok, "output": merger.last_output_path if ok else None}

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, t("ui.merge.failed"), result)
            elif result.get("declined"):
                bar.finish("cancelled", t("ui.merge.cancelled"))
                self._set_status(t('gui.status_ready'), key)
            elif "kept" in result:
                name = Path(result["kept"]).name if result["kept"] else ""
                bar.finish("cancelled", t("ui.merge.kept_existing", name=name))
                self._set_status(t('gui.status_ready'), key)
            elif result.get("cancelled"):
                bar.finish("cancelled", t("ui.merge.cancelled_nothing"))
                self._set_status(t("ui.merge.cancelled"), key)
            elif result.get("success"):
                out = result.get("output")
                name = out.name if out else t("ui.merge.the_result")
                bar.finish("success", t("ui.common.saved", name=name), actions=self._output_actions(out))
                self._set_status("✔ " + t("ui.common.saved", name=name), key)
            else:
                self._fail(key, t("ui.merge.failed"), None)

        self._run_task(key, t("ui.merge.starting"), work, done, cancellable=True, determinate=True,
                       status=t("ui.merge.status_running"))

    # ======================================================================
    # Extract tab
    # ======================================================================

    def _create_extract_tab(self):
        """Create the Extract Tracks tab (mkvextract)."""
        _tab, body = self._new_tab("extract", t('gui.tab_extract').strip())
        self._intro(body, 0, t("ui.extract.intro"))
        self.extract_banner = Banner(body, row=1, column=0, sticky="ew", pady=(0, PAD))

        file_frame = self._section(body, 2, t("ui.extract.video_section"))
        self.extract_file_var = tk.StringVar()
        self._path_row(file_frame, 0, self.extract_file_var, self._browse_extract_file,
                       extra=[(t("ui.common.load_tracks"), self._load_extract_tracks)],
                       drop=self._on_extract_drop)

        tracks_frame = self._section(body, 3, t("ui.extract.tracks_section"))
        tracks_frame.rowconfigure(0, weight=1)
        columns = ('id', 'language', 'codec', 'name')
        self.extract_tree = ttk.Treeview(tracks_frame, columns=columns, show='headings', height=7,
                                         selectmode='extended')
        from tkinter import font as tkfont
        heading_font = tkfont.nametofont("TkHeadingFont")
        body_font = tkfont.nametofont("TkDefaultFont")
        for col, text, sample, anchor in (('id', 'ID', '000', 'center'),
                                          ('language', t("ui.extract.col_language"), 'zh-Hans', 'center'),
                                          ('codec', t("ui.extract.col_codec"), 'S_TEXT/UTF8', 'w'),
                                          ('name', t("ui.extract.col_name"), 'Simplified Chinese (Signs)', 'w')):
            self.extract_tree.heading(col, text=text)
            px = max(heading_font.measure(text), body_font.measure(sample)) + int(20 * self.scale)
            self.extract_tree.column(col, width=px, minwidth=heading_font.measure(text) + int(12 * self.scale),
                                     anchor=anchor, stretch=(col == 'name'))
        scrollbar = ttk.Scrollbar(tracks_frame, orient=tk.VERTICAL, command=self.extract_tree.yview)
        self.extract_tree.configure(yscrollcommand=scrollbar.set)
        self.extract_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        sel = ttk.Frame(tracks_frame)
        sel.grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S + 2, 0))
        ttk.Button(sel, text=t("ui.extract.select_all"), command=self._extract_select_all).pack(side=tk.LEFT)
        ttk.Button(sel, text=t("ui.extract.select_none"), command=self._extract_select_none).pack(
            side=tk.LEFT, padx=(PAD_S, 0))
        self.extract_tree.bind("<<TreeviewSelect>>", lambda e: self._update_extract_hint())

        output_frame = self._section(body, 4, t("ui.common.output"))
        self.extract_output_var = tk.StringVar()
        self._path_row(output_frame, 0, self.extract_output_var, self._browse_extract_output,
                       label=t("ui.common.folder"), drop=self._drop_folder(self.extract_output_var))
        ttk.Label(output_frame, text=t("ui.extract.out_hint"), style='Caption.TLabel').grid(
            row=1, column=0, sticky="w", pady=(PAD_S, 0))
        self.extract_ocr_var = tk.BooleanVar(value=self._pgs_available)
        if self._is_lite:
            ocr_text = t("ui.extract.ocr_lite")
        elif not self._pgs_available:
            ocr_text = t("ui.extract.ocr_install")
        else:
            ocr_text = t("ui.extract.ocr")
        self._extract_ocr_check = ttk.Checkbutton(output_frame, text=ocr_text, variable=self.extract_ocr_var,
                                                  state='normal' if self._pgs_available else 'disabled')
        self._extract_ocr_check.grid(row=2, column=0, sticky="w", pady=(PAD_S, 0))

        self._extract_hint = t("ui.extract.hint_start")
        bar = self._add_action_bar("extract", t("ui.extract.button"), self._execute_extract, self._extract_hint)
        self.extract_btn = bar.button
        self.extract_progress = bar.progressbar
        self.extract_progress_label = bar.message
        self._extract_tracks = []

    def _update_extract_hint(self):
        if self._missing.get("mkvtoolnix"):
            return
        n = len(self.extract_tree.selection())
        total = len(self.extract_tree.get_children())
        if total:
            self._extract_hint = t("ui.extract.selected", n=n, total=total)
        self._bars["extract"].set_hint(self._extract_hint)

    def _browse_extract_file(self):
        filename = self._ask_open("video", t("ui.dlg.select_video"),
                                  [(t("ui.ft.videos"), "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"),
                                   (t("ui.ft.mkv"), "*.mkv"), (t("ui.ft.all"), "*.*")])
        if filename:
            self.extract_file_var.set(filename)
            self._load_extract_tracks()

    def _on_extract_drop(self, paths: list[str]):
        videos = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
        if not videos:
            if paths:
                self._invalid("extract", t("ui.drop.need_video", name=Path(paths[0]).name))
            return
        self.extract_file_var.set(videos[0])
        self._load_extract_tracks()

    def _drop_folder(self, var: tk.StringVar) -> Callable[[list[str]], None]:
        """Drop handler for a folder field: a dropped file means its folder."""
        def handler(paths: list[str]):
            if paths:
                p = Path(paths[0])
                var.set(str(p if p.is_dir() else p.parent))
        return handler

    def _browse_extract_output(self):
        dirname = self._ask_dir("output", t("ui.dlg.select_output_folder"))
        if dirname:
            self.extract_output_var.set(dirname)

    def _check_mkvtoolnix_available(self) -> tuple:
        """(available, missing_tools) for MKVToolNix (PATH lookup, no subprocess)."""
        missing = missing_tools("mkvtoolnix")
        return (len(missing) == 0, missing)

    def _show_mkvtoolnix_missing_dialog(self):
        """Explain how to get MKVToolNix for this platform."""
        messagebox.showerror(t("ui.extract.mkv_missing_title"),
                             t("ui.extract.mkv_missing_body") + "\n\n" + install_hint("mkvtoolnix"), parent=self.root)

    def _mkvtoolnix_ready(self) -> bool:
        available, missing = self._check_mkvtoolnix_available()
        self._missing["mkvtoolnix"] = missing
        self._refresh_tool_banners()
        if not available:
            self._bars["extract"].finish("error", t("ui.extract.mkv_missing_inline"))
            self._scrollers["extract"].scroll_to_top()
        return available

    def _load_extract_tracks(self):
        """Load tracks from an MKV file using mkvinfo (in the background)."""
        video_path = self.extract_file_var.get().strip()
        if not video_path:
            self._invalid("extract", t("ui.merge.choose_video_first"))
            return
        if self._bars["extract"].busy or not self._mkvtoolnix_ready():
            return
        if not Path(video_path).is_file():
            self._invalid("extract", t("ui.merge.video_not_found", path=video_path))
            return
        for item in self.extract_tree.get_children():
            self.extract_tree.delete(item)
        self._extract_tracks = []

        def work(cancel):
            result = subprocess.run(['mkvinfo', video_path], capture_output=True, timeout=120, check=False)
            return parse_mkvinfo_tracks(result.stdout.decode('utf-8', errors='replace'))

        def done(ok, result, cancelled):
            bar = self._bars["extract"]
            if not ok:
                if isinstance(result, subprocess.TimeoutExpired):
                    result = t("ui.extract.mkvinfo_timeout")
                self._fail("extract", t("ui.extract.read_failed"), result)
                return
            subs = [tr for tr in result if tr['type'] == 'subtitles']
            self._extract_tracks = subs
            for tr in subs:
                self.extract_tree.insert('', 'end', values=(tr['id'], tr['language'], tr['codec'], tr['name']))
            self._extract_select_all()
            bar.finish("info" if subs else "warning",
                       t("ui.extract.found", n=len(subs)) if subs else t("ui.extract.none"))
            self._set_status(t("ui.extract.found_status", n=len(subs)), "extract")

        self._run_task("extract", t("ui.extract.reading"), work, done)

    def _extract_select_all(self):
        self.extract_tree.selection_set(self.extract_tree.get_children())

    def _extract_select_none(self):
        self.extract_tree.selection_remove(*self.extract_tree.get_children())

    def _execute_extract(self):
        """Extract the selected tracks (cancellable)."""
        key = "extract"
        if self._bars[key].busy:
            return
        video_path = self.extract_file_var.get().strip()
        if not video_path:
            self._invalid(key, t("ui.merge.choose_video_first"))
            return
        if not self._mkvtoolnix_ready():
            return
        selected = self.extract_tree.selection()
        if not selected:
            self._invalid(key, t("ui.extract.select_one"))
            return
        output_dir = self.extract_output_var.get().strip() or str(Path(video_path).parent)
        if not Path(output_dir).is_dir():
            self._invalid(key, t("ui.common.folder_not_found", path=output_dir))
            return

        video_stem = Path(video_path).stem
        extract_args = []
        for item in selected:
            values = self.extract_tree.item(item, 'values')
            tid = values[0]
            lang = values[1] if values[1] else f"track{tid}"
            codec = str(values[2]).lower()
            if 'pgs' in codec or 's_vobsub' in codec:
                ext = '.sup'
            elif 's_text' in codec or 'subrip' in codec:
                ext = '.srt'
            else:
                ext = '.ass'
            extract_args.append(f"{tid}:{Path(output_dir) / f'{video_stem}.{lang}.{tid}{ext}'}")
        do_ocr = bool(self.extract_ocr_var.get() and self._pgsrip_wrapper)

        def work(cancel):
            cmd = ['mkvextract', video_path, 'tracks'] + extract_args
            logger.info(f"Running: mkvextract with {len(extract_args)} tracks")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    if cancel.is_set():
                        proc.terminate()
                        proc.communicate()
                        return {"cancelled": True}
            if proc.returncode != 0:
                raise RuntimeError((stderr or stdout or "mkvextract failed").strip().splitlines()[-1])
            ocr_results, outputs = [], []
            for arg in extract_args:
                tid, output = arg.split(':', 1)
                out_path = Path(output)
                outputs.append(out_path)
                logger.info(f"  Track {tid} -> {output}")
                if cancel.is_set():
                    break
                if do_ocr and out_path.suffix.lower() == '.sup' and out_path.exists():
                    srt_path = out_path.with_suffix('.srt')
                    self._post(lambda n=out_path.name: self._bars[key].progress(t("ui.extract.ocr_progress", name=n)))
                    try:
                        if self._pgsrip_wrapper.convert_subtitle_file(out_path, srt_path, 'eng'):
                            out_path.unlink()  # remove the raw .sup once OCR succeeded
                            outputs[-1] = srt_path
                            ocr_results.append(f"Track {tid}: OCR -> {srt_path.name}")
                        else:
                            ocr_results.append(f"Track {tid}: OCR failed, kept {out_path.name}")
                    except Exception as ocr_err:  # noqa: BLE001 - report any failure to the user
                        ocr_results.append(f"Track {tid}: OCR error: {ocr_err}")
            for line in ocr_results:
                logger.info(line)
            return {"outputs": outputs, "ocr": ocr_results, "cancelled": cancel.is_set()}

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok:
                self._fail(key, t("ui.extract.failed"), result)
            elif result.get("cancelled") and not result.get("outputs"):
                bar.finish("cancelled", t("ui.extract.cancelled"))
            else:
                outputs = result["outputs"]
                failed_ocr = [r for r in result.get("ocr", []) if "failed" in r or "error" in r]
                text = t("ui.extract.saved", n=len(outputs), folder=Path(output_dir).name or output_dir)
                if failed_ocr:
                    text += t("ui.extract.ocr_problems", n=len(failed_ocr))
                bar.finish("warning" if failed_ocr else "success", text,
                           actions=self._output_actions(outputs[0] if outputs else Path(output_dir), preview=False))
                self._set_status("✔ " + text, key)

        self._run_task(key, t("ui.extract.running", n=len(extract_args)), work, done, cancellable=True)

    # ======================================================================
    # Split tab
    # ======================================================================

    def _create_split_tab(self):
        """Create the Split Bilingual Subtitles tab."""
        _tab, body = self._new_tab("split", t('gui.tab_split').strip())
        self._intro(body, 0, t("ui.split.intro"))

        file_frame = self._section(body, 1, t("ui.split.file_section"))
        self.split_file_var = tk.StringVar()
        self.split_file_var.trace_add('write', lambda *a: self._on_split_file_changed())
        self._path_row(file_frame, 0, self.split_file_var, self._browse_split_file, preview=True,
                       drop=self._drop_subtitle(self.split_file_var, "split"))
        self.split_chip = InfoChip(file_frame)
        self.split_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))
        self.split_status_var = tk.StringVar(value=t("ui.split.select_file"))

        options = self._section(body, 2, t("ui.split.options"))
        lang_row = ttk.Frame(options)
        lang_row.grid(row=0, column=0, sticky="w")
        ttk.Label(lang_row, text=t("ui.split.name_cjk")).pack(side=tk.LEFT)
        self.split_lang1_var = tk.StringVar(value="zh")
        ttk.Combobox(lang_row, textvariable=self.split_lang1_var, width=6,
                     values=['zh', 'ja', 'ko', 'chi', 'jpn', 'kor']).pack(side=tk.LEFT, padx=(PAD_S, PAD_L + PAD))
        ttk.Label(lang_row, text=t("ui.split.name_other")).pack(side=tk.LEFT)
        self.split_lang2_var = tk.StringVar(value="en")
        ttk.Combobox(lang_row, textvariable=self.split_lang2_var, width=6,
                     values=['en', 'eng', 'fr', 'de', 'es']).pack(side=tk.LEFT, padx=(PAD_S, 0))
        ttk.Label(options, text=t("ui.split.codes_hint"),
                  style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(PAD_S, 0))

        fmt_row = ttk.Frame(options)
        fmt_row.grid(row=2, column=0, sticky="w", pady=(PAD, 0))
        ttk.Label(fmt_row, text=t("ui.split.cjk_format")).pack(side=tk.LEFT)
        self.split_format_var = tk.StringVar(value=self.settings.get("split.format", "ass"))
        ttk.Radiobutton(fmt_row, text=t("ui.split.fmt_ass"),
                        variable=self.split_format_var, value="ass").pack(side=tk.LEFT, padx=(PAD, PAD))
        ttk.Radiobutton(fmt_row, text=t("ui.split.fmt_srt"),
                        variable=self.split_format_var, value="srt").pack(side=tk.LEFT)
        self.split_strip_var = tk.BooleanVar(value=bool(self.settings.get("split.strip", True)))
        ttk.Checkbutton(options, text=t("ui.split.strip"),
                        variable=self.split_strip_var).grid(row=3, column=0, sticky="w", pady=(PAD, 0))

        out_frame = self._section(body, 3, t("ui.common.output"))
        self.split_output_dir_var = tk.StringVar()
        self._path_row(out_frame, 0, self.split_output_dir_var, self._browse_split_output_dir,
                       label=t("ui.common.folder"), drop=self._drop_folder(self.split_output_dir_var))
        ttk.Label(out_frame, text=t("ui.split.out_hint"),
                  style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(PAD_S, 0))

        bar = self._add_action_bar("split", t("ui.split.button"), self._execute_split, t("ui.split.hint_start"))
        self.split_btn = bar.button

    def _drop_subtitle(self, var: tk.StringVar, key: str) -> Callable[[list[str]], None]:
        """Drop handler for a single subtitle field."""
        def handler(paths: list[str]):
            subs = [p for p in paths if Path(p).suffix.lower() in SUBTITLE_EXTENSIONS]
            if subs:
                var.set(subs[0])
            elif paths:
                self._invalid(key, t("ui.drop.need_subtitle", name=Path(paths[0]).name))
        return handler

    def _browse_split_file(self):
        file_path = self._ask_open("subtitle", t("ui.split.dlg_select"),
                                   [(t("ui.ft.subtitles"), "*.srt *.ass *.ssa *.vtt"), (t("ui.ft.srt"), "*.srt"),
                                    (t("ui.ft.ass_ssa"), "*.ass *.ssa"), (t("ui.ft.all"), "*.*")])
        if file_path:
            self.split_file_var.set(file_path)

    def _browse_split_output_dir(self):
        dir_path = self._ask_dir("output", t("ui.dlg.select_output_folder"))
        if dir_path:
            self.split_output_dir_var.set(dir_path)

    def _on_split_file_changed(self):
        """Show language/lines and whether the file looks bilingual (analysed off-thread)."""
        path = self.split_file_var.get().strip()

        def render(info):
            bar = self._bars["split"]
            if info is None:
                self.split_chip.clear()
                self.split_status_var.set(t("ui.split.select_file"))
                bar.set_hint(t("ui.split.hint_start") if not path else t("ui.common.file_not_found_short"))
                return
            if info.get("busy") or info.get("error"):
                self._render_chip(self.split_chip, info)
                return
            base = describe_subtitle(dict(info, language=None)).split(" · ", 1)[-1]
            name = Path(path).name
            if info.get("split_bilingual"):
                self.split_status_var.set(t("ui.split.detected"))
                self.split_chip.show(f"{t('ui.split.chip_bilingual')} · {base}", "ok")
                bar.set_hint(t("ui.split.ready", name=name))
            else:
                self.split_status_var.set(t("ui.split.not_bilingual_status"))
                self.split_chip.show(f"{t('ui.split.chip_not_bilingual')} · {base}", "warning")
                bar.set_hint(t("ui.split.not_bilingual_hint"), "warning")

        def check_bilingual(p: Path, info: dict[str, Any]):
            from processors.splitter import BilingualSplitter
            info["split_bilingual"] = BilingualSplitter().is_bilingual(p)

        self._analyze_later("split", path, render, extra=check_bilingual)

    def _execute_split(self):
        """Execute the split operation."""
        key = "split"
        if self._bars[key].busy:
            return
        file_path = self.split_file_var.get().strip()
        if not file_path:
            self._invalid(key, t("ui.split.hint_start"))
            return
        input_path = Path(file_path)
        if not input_path.is_file():
            self._invalid(key, t("ui.common.file_not_found", path=file_path))
            return
        output_dir = Path(self.split_output_dir_var.get().strip()) if self.split_output_dir_var.get().strip() else None
        if output_dir and not output_dir.is_dir():
            self._invalid(key, t("ui.common.folder_not_found", path=output_dir))
            return
        lang1, lang2 = self.split_lang1_var.get().strip() or "zh", self.split_lang2_var.get().strip() or "en"
        strip_formatting = self.split_strip_var.get()
        lang1_format = self.split_format_var.get()

        def work(cancel):
            from processors.splitter import BilingualSplitter
            splitter = BilingualSplitter(strip_formatting=strip_formatting)
            return splitter.split_file(input_path=input_path, output_dir=output_dir, lang1_label=lang1,
                                       lang2_label=lang2, lang1_format=lang1_format)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok:
                self._fail(key, t("ui.split.failed"), result)
                return
            outputs = [p for p in result if p]
            if not outputs:
                bar.finish("warning", t("ui.split.nothing"))
                return
            names = t("ui.common.and").join(p.name for p in outputs)
            bar.finish("success", t("ui.common.saved", name=names), actions=self._output_actions(outputs[0]))
            self._set_status("✔ " + t("ui.common.saved", name=names), key)

        self._run_task(key, t("ui.split.running"), work, done)

    # ======================================================================
    # Shift tab
    # ======================================================================

    def _create_shift_tab(self):
        """Create the Shift Timing tab (manual offset, first-line time, or match a video)."""
        _tab, body = self._new_tab("shift", t('gui.tab_shift').strip())
        self._intro(body, 0, t("ui.shift.intro"))

        file_frame = self._section(body, 1, t("ui.shift.file_section"))
        self.shift_file_var = tk.StringVar()
        self.shift_file_var.trace_add('write', lambda *a: self._on_shift_file_changed())
        self._path_row(file_frame, 0, self.shift_file_var, self._browse_shift_file, preview=True,
                       drop=self._drop_subtitle(self.shift_file_var, "shift"))
        self.shift_chip = InfoChip(file_frame)
        self.shift_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        options = self._section(body, 2, t("ui.shift.options"))
        self.shift_mode_var = tk.StringVar(value="offset")
        mode_frame = ttk.Frame(options)
        mode_frame.grid(row=0, column=0, sticky="w", pady=(0, PAD))
        for i, (text, value) in enumerate(((t("ui.shift.mode_offset"), "offset"),
                                           (t("ui.shift.mode_first"), "first_line"),
                                           (t("ui.shift.mode_video"), "video"))):
            ttk.Radiobutton(mode_frame, text=text, variable=self.shift_mode_var, value=value,
                            command=self._update_shift_mode).pack(side=tk.LEFT, padx=(0 if i == 0 else PAD_L + PAD, 0))

        self.offset_frame = ttk.Frame(options)
        ttk.Label(self.offset_frame, text=t("ui.shift.offset")).grid(row=0, column=0, sticky="w")
        self.shift_offset_var = tk.StringVar(value="")
        self.shift_offset_entry = ttk.Entry(self.offset_frame, textvariable=self.shift_offset_var, width=12)
        self.shift_offset_entry.grid(row=0, column=1, sticky="w", padx=(PAD_S, PAD))
        quick_frame = ttk.Frame(self.offset_frame)
        quick_frame.grid(row=0, column=2, sticky="w")
        for offset in ["-5s", "-1s", "-0.5s", "+0.5s", "+1s", "+5s"]:
            ttk.Button(quick_frame, text=offset, width=5,
                       command=lambda o=offset: self._nudge_offset(o)).pack(side=tk.LEFT, padx=(0, 2))
        self.shift_offset_hint = ttk.Label(self.offset_frame, style="Caption.TLabel", text=t("ui.shift.offset_hint"))
        self.shift_offset_hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(PAD_S, 0))

        self.firstline_frame = ttk.Frame(options)
        ttk.Label(self.firstline_frame, text=t("ui.shift.first_to")).grid(row=0, column=0, sticky="w")
        self.shift_firstline_var = tk.StringVar(value="00:00:50,000")
        ttk.Entry(self.firstline_frame, textvariable=self.shift_firstline_var, width=14).grid(
            row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self.shift_firstline_hint = ttk.Label(self.firstline_frame, text=t("ui.shift.ts_format"),
                                              style='Caption.TLabel')
        self.shift_firstline_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S, 0))

        # Match a video: the same controls as Convert > Sync, sharing its variables.
        self._create_sync_vars()
        self.shift_video_frame = ttk.Frame(options)
        self.shift_video_frame.columnconfigure(0, weight=1)
        self.shift_sync_track_combo = self._build_sync_controls(self.shift_video_frame, "shift")

        output = self._section(body, 3, t("ui.common.output"))
        self.shift_overwrite_var = tk.BooleanVar(value=bool(self.settings.get("shift.overwrite", False)))
        ttk.Radiobutton(output, text=t("ui.shift.save_new"), variable=self.shift_overwrite_var, value=False,
                        command=self._update_shift_output).grid(row=0, column=0, sticky="w")
        self.shift_output_var = tk.StringVar()
        self._shift_output_auto = ""
        self.shift_output_row, self.shift_output_entry = self._path_row(
            output, 1, self.shift_output_var, self._browse_shift_output, label=t("ui.common.save_as"))
        self.shift_output_row.grid_configure(padx=(PAD_L + PAD, 0), pady=(PAD_S, PAD_S))
        ttk.Radiobutton(output, text=t("ui.shift.overwrite"), variable=self.shift_overwrite_var,
                        value=True, command=self._update_shift_output).grid(row=2, column=0, sticky="w")
        self.shift_backup_var = tk.BooleanVar(value=bool(self.settings.get("shift.backup", True)))
        self.shift_backup_check = ttk.Checkbutton(output, text=t("ui.shift.backup"),
                                                  variable=self.shift_backup_var)
        self.shift_backup_check.grid(row=3, column=0, sticky="w", padx=(PAD_L + PAD, 0), pady=(PAD_S, 0))

        bar = self._add_action_bar("shift", t("ui.shift.button"), self._execute_shift, t("ui.shift.hint_file"))
        self.shift_btn = bar.button
        for var in (self.shift_offset_var, self.shift_firstline_var, self.shift_output_var, self.sync_video_var):
            var.trace_add('write', lambda *a: self._validate_shift())
        self._update_shift_mode()
        self._update_shift_output()

    def _create_sync_vars(self):
        self.sync_video_var = tk.StringVar()
        self.sync_track_var = tk.StringVar(value=t("ui.sync.auto_track"))
        self.sync_result_var = tk.StringVar(value=t("ui.sync.explain"))
        self._sync_tracks_data = []

    def _build_sync_controls(self, parent, key: str) -> ttk.Combobox:
        """Video + reference track + Detect Offset, for the Shift and Convert tabs."""
        self._path_row(parent, 0, self.sync_video_var, lambda k=key: self._browse_sync_video(k),
                       label=t("ui.sync.video"), drop=lambda paths, k=key: self._on_sync_video_drop(k, paths))
        track_row = ttk.Frame(parent)
        track_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        track_row.columnconfigure(1, weight=1)
        ttk.Label(track_row, text=t("ui.sync.reference")).grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(track_row, textvariable=self.sync_track_var, width=50, state='readonly',
                             values=[t("ui.sync.auto_track")])
        combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(track_row, text=t("ui.common.load_tracks"), command=lambda k=key: self._load_sync_tracks(k)).grid(
            row=0, column=2, padx=(PAD_S, 0))
        btn_row = ttk.Frame(parent)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        btn_row.columnconfigure(1, weight=1)
        ttk.Button(btn_row, text=t("ui.sync.detect"), command=lambda k=key: self._detect_sync_offset(k)).grid(
            row=0, column=0, sticky="nw")
        self._caption(btn_row, textvariable=self.sync_result_var).grid(row=0, column=1, sticky="ew", padx=(PAD, 0))
        return combo

    def _nudge_offset(self, delta: str):
        """Quick buttons add to the current offset (-1s then -0.5s = -1.5s)."""
        try:
            current = parse_offset(self.shift_offset_var.get())
        except ValueError:
            current = 0
        self.shift_offset_var.set(format_offset(current + parse_offset(delta)))

    def _update_shift_mode(self):
        mode = self.shift_mode_var.get()
        frames = {"offset": self.offset_frame, "first_line": self.firstline_frame, "video": self.shift_video_frame}
        for frame in frames.values():
            frame.grid_remove()
        frames.get(mode, self.offset_frame).grid(row=1, column=0, sticky="ew")
        if "shift" in self._bars:
            self.shift_btn.configure(text=t("ui.shift.button_sync") if mode == "video" else t("ui.shift.button"))
        self._validate_shift()

    def _update_shift_output(self):
        overwrite = self.shift_overwrite_var.get()
        state = ["disabled"] if overwrite else ["!disabled"]
        for child in self.shift_output_row.winfo_children():
            try:
                child.state(state)
            except (AttributeError, tk.TclError):
                pass
        self.shift_backup_check.state(["!disabled"] if overwrite else ["disabled"])
        self._validate_shift()

    def _on_shift_file_changed(self):
        path = self.shift_file_var.get().strip()
        # Suggest "<name>.shifted.<ext>" unless the user typed their own output name.
        if path and (not self.shift_output_var.get() or self.shift_output_var.get() == self._shift_output_auto):
            p = Path(path)
            self._shift_output_auto = str(p.with_name(f"{p.stem}.shifted{p.suffix or '.srt'}"))
            self.shift_output_var.set(self._shift_output_auto)
        self._analyze_later("shift", path, lambda info: (self._render_chip(self.shift_chip, info),
                                                         self._validate_shift()))
        self._validate_shift()

    def _validate_shift(self) -> str | None:
        """Enable Apply only when the input is valid; explain what is missing."""
        if "shift" not in self._bars:
            return None
        problem = None
        path = self.shift_file_var.get().strip()
        mode = self.shift_mode_var.get()
        ready = t("ui.shift.ready")
        if mode == "offset":
            text = self.shift_offset_var.get()
            try:
                ms = parse_offset(text)
                self.shift_offset_hint.configure(
                    text=(t("ui.shift.will_later", s=f"{abs(ms) / 1000:g}") if ms > 0
                          else t("ui.shift.will_earlier", s=f"{abs(ms) / 1000:g}")) if ms
                    else t("ui.shift.offset_hint"),
                    style="Caption.TLabel")
                if ms == 0:
                    problem = t("ui.shift.need_offset")
                else:
                    ready = t("ui.shift.ready_offset", name=Path(path).name if path else "",
                              offset=format_offset(ms))
            except ValueError as e:
                if text.strip():
                    self.shift_offset_hint.configure(text=str(e), style="Error.TLabel")
                    problem = t("ui.shift.offset_problem", error=e)
                else:
                    self.shift_offset_hint.configure(text=t("ui.shift.offset_hint"), style="Caption.TLabel")
                    problem = t("ui.shift.need_offset")
        elif mode == "first_line":
            try:
                parse_timestamp(self.shift_firstline_var.get())
                self.shift_firstline_hint.configure(text=t("ui.shift.ts_format"), style="Caption.TLabel")
            except ValueError as e:
                self.shift_firstline_hint.configure(text=str(e), style="Error.TLabel")
                problem = str(e)
        else:
            video = self.sync_video_var.get().strip()
            if not video:
                problem = t("ui.sync.need_video")
            elif not Path(video).is_file():
                problem = t("ui.merge.video_not_found", path=video)
            elif self._missing.get("ffmpeg"):
                problem = t("ui.sync.need_ffmpeg") + " " + install_hint("ffmpeg")
            else:
                ready = t("ui.sync.ready", name=Path(path).name if path else "", video=Path(video).name)
        if not path:
            problem = t("ui.shift.hint_file")
        elif not Path(path).is_file():
            problem = t("ui.common.file_not_found_short")
        elif not self.shift_overwrite_var.get() and not self.shift_output_var.get().strip():
            problem = t("ui.shift.need_output")
        bar = self._bars["shift"]
        if not bar.busy:
            bar.button.state(["disabled"] if problem else ["!disabled"])
            bar.set_hint(problem or ready)
        return problem

    def _on_convert_file_changed(self, keep_result: bool = False):
        """Convert tab file changed: analyse subtitles, suggest output names, update guidance."""
        path = self.convert_file_var.get().strip()
        p = Path(path) if path else None
        if p and p.is_file():
            ext = p.suffix.lower()
            if ext in ('.ass', '.ssa'):
                self.ass_output_var.set(str(p.with_suffix('.srt')))
            if self.convert_type_var.get() == 'pgs_ocr':
                self._detect_pgs_tracks()
        if p and p.is_file() and p.suffix.lower() not in ('.sup', '.idx', '.sub') and \
                p.suffix.lower() not in VIDEO_EXTENSIONS:
            def render(info):
                self._render_chip(self.convert_chip, info)
                if info and not info.get("busy"):
                    enc = info.get("encoding")
                    self.detected_encoding_var.set(encoding_name(enc) if enc else t("ui.convert.enc_unknown"))
                    self.encoding_label.configure(style="Success.TLabel" if enc else "Error.TLabel")
                self._update_convert_hint(keep_result=True)
            self._analyze_later("convert", path, render)
        else:
            self._analyze_later("convert", "", lambda info: None)
            self.convert_chip.clear()
            self.detected_encoding_var.set(t("ui.convert.select_file"))
            self.encoding_label.configure(style="TLabel")
        self._update_convert_hint(keep_result=keep_result)

    def _update_convert_hint(self, keep_result: bool = False):
        """Action-bar guidance for the Convert tab: what is missing, or what will happen."""
        bar = self._bars.get("convert")
        if bar is None or bar.busy:
            return
        mode = self.convert_type_var.get()
        path = self.convert_file_var.get().strip()
        p = Path(path) if path else None
        exists = bool(p and p.is_file())
        name = p.name if p else ""
        if mode == "encoding":
            if not path:
                hint, kind = t("ui.convert.hint_encoding"), "hint"
            elif not exists:
                hint, kind = t("ui.common.file_not_found_short"), "warning"
            else:
                target = encoding_name(self.convert_encoding_var.get().strip() or "utf-8")
                info = self._cached_info(path) or {}
                current = info.get("encoding")
                if current and encoding_name(current) == target and not self.convert_force_var.get():
                    hint, kind = t("ui.convert.already", name=name, enc=target), "hint"
                else:
                    hint, kind = t("ui.convert.ready_encoding", name=name, enc=target), "hint"
        elif mode == "ass_to_srt":
            if not path:
                hint, kind = t("ui.convert.hint_ass"), "hint"
            elif not exists:
                hint, kind = t("ui.common.file_not_found_short"), "warning"
            elif p.suffix.lower() not in (".ass", ".ssa"):
                hint, kind = t("ui.convert.not_ass"), "warning"
            else:
                out = self.ass_output_var.get().strip() or str(p.with_suffix(".srt"))
                hint, kind = t("ui.convert.ready_ass", name=Path(out).name), "hint"
        elif mode == "pgs_ocr":
            if not path:
                hint, kind = t("ui.convert.hint_pgs"), "hint"
            elif not exists:
                hint, kind = t("ui.common.file_not_found_short"), "warning"
            else:
                out = self.pgs_output_var.get().strip() or str(p.with_suffix(".pgs.srt"))
                hint, kind = t("ui.convert.ready_pgs", name=Path(out).name), "hint"
        else:
            video = self.sync_video_var.get().strip()
            if not path:
                hint, kind = t("ui.convert.hint_sync"), "hint"
            elif not exists:
                hint, kind = t("ui.common.file_not_found_short"), "warning"
            elif not video:
                hint, kind = t("ui.sync.need_video"), "hint"
            elif self._missing.get("ffmpeg"):
                hint, kind = t("ui.sync.need_ffmpeg") + " " + install_hint("ffmpeg"), "warning"
            else:
                hint, kind = t("ui.sync.ready_in_place", name=name, video=Path(video).name), "hint"
        bar.set_hint(hint, kind, keep_result=keep_result)

    def _browse_shift_file(self):
        path = self._ask_open("subtitle", t("ui.dlg.select_subtitle"), _subtitle_types())
        if path:
            self.shift_file_var.set(path)

    def _browse_shift_output(self):
        current = self.shift_output_var.get().strip()
        ext = Path(current).suffix if current else ".srt"
        path = self._ask_save("output", t("ui.shift.dlg_save"),
                              [(t("ui.ft.srt"), "*.srt"), (t("ui.ft.ass"), "*.ass"), (t("ui.ft.all"), "*.*")],
                              ext or ".srt", current=current)
        if path:
            self.shift_output_var.set(path)

    def _execute_shift(self):
        """Apply the timing change (validated on the UI thread first)."""
        key = "shift"
        if self._bars[key].busy:
            return
        problem = self._validate_shift()
        if problem:
            self._invalid(key, problem)
            return
        input_path = Path(self.shift_file_var.get().strip())
        overwrite = self.shift_overwrite_var.get()
        output_path = None if overwrite else Path(self.shift_output_var.get().strip())
        if output_path and output_path.resolve() == input_path.resolve():
            output_path = None
            overwrite = True
        mode = self.shift_mode_var.get()
        if mode == "video" and not self._sync_inputs(key):
            return  # explained inline (e.g. FFmpeg missing) before asking anything else
        if output_path is not None and output_path.exists() and not self._confirm_replace(output_path):
            self._bars[key].finish("cancelled", t("ui.common.kept_existing", name=output_path.name))
            return
        create_backup = self.shift_backup_var.get() if overwrite else False
        if mode == "video":
            self._execute_sync(key, output_path=output_path, backup=create_backup)
            return
        offset_ms = parse_offset(self.shift_offset_var.get()) if mode == "offset" else 0
        timestamp = self.shift_firstline_var.get().strip()

        def work(cancel):
            from processors.timing_adjuster import TimingAdjuster
            adjuster = TimingAdjuster(create_backup=create_backup)
            if mode == "offset":
                return adjuster.adjust_by_offset(input_path, offset_ms, output_path)
            return adjuster.adjust_first_line_to(input_path, timestamp.replace(".", ","), output_path)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok or not result:
                self._fail(key, t("ui.shift.failed"), result if not ok else None)
                return
            target = output_path or input_path
            if mode == "offset":
                how = (t("ui.shift.how_later", s=f"{abs(offset_ms) / 1000:g}") if offset_ms > 0
                       else t("ui.shift.how_earlier", s=f"{abs(offset_ms) / 1000:g}"))
            else:
                how = t("ui.shift.how_first", ts=timestamp)
            note = t("ui.common.backup_kept") if overwrite and create_backup else ""
            text = t("ui.shift.saved", name=target.name, how=how) + note
            bar.finish("success", text, actions=self._output_actions(target))
            self._set_status("✔ " + text, key)

        self._run_task(key, t("ui.shift.running"), work, done)

    # ======================================================================
    # Convert tab
    # ======================================================================

    def _create_convert_tab(self):
        """Create the Convert tab (encoding, ASS->SRT, PGS OCR, sync to video)."""
        _tab, body = self._new_tab("convert", t('gui.tab_convert').strip())
        self._intro(body, 0, t("ui.convert.intro"))

        type_frame = self._section(body, 1, t("ui.convert.type_section"))
        self.convert_type_var = tk.StringVar(value="encoding")
        ttk.Radiobutton(type_frame, text=t("ui.convert.mode_encoding"),
                        variable=self.convert_type_var, value="encoding",
                        command=self._update_convert_type).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(type_frame, text=t("ui.convert.mode_ass"),
                        variable=self.convert_type_var, value="ass_to_srt",
                        command=self._update_convert_type).grid(row=1, column=0, sticky="w", pady=(2, 0))
        if self._is_lite:
            pgs_label, pgs_state = t("ui.convert.mode_pgs_lite"), 'disabled'
        elif not self._pgs_available:
            pgs_label, pgs_state = t("ui.convert.mode_pgs_install"), 'disabled'
        else:
            pgs_label, pgs_state = t("ui.convert.mode_pgs"), 'normal'
        self._pgs_radio = ttk.Radiobutton(type_frame, text=pgs_label, variable=self.convert_type_var,
                                          value="pgs_ocr", command=self._update_convert_type, state=pgs_state)
        self._pgs_radio.grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Radiobutton(type_frame, text=t("ui.convert.mode_sync"),
                        variable=self.convert_type_var, value="sync",
                        command=self._update_convert_type).grid(row=3, column=0, sticky="w", pady=(2, 0))

        self.convert_file_frame = self._section(body, 2, t("ui.convert.file_section"))
        self.convert_file_var = tk.StringVar()
        self.convert_file_var.trace_add('write', lambda *a: self._on_convert_file_changed())
        self._path_row(self.convert_file_frame, 0, self.convert_file_var, self._browse_convert_file, preview=True,
                       drop=self._on_convert_drop)
        self.convert_chip = InfoChip(self.convert_file_frame)
        self.convert_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        # Options live in a fixed slot so switching modes never reorders the page.
        host = ttk.Frame(body)
        host.grid(row=3, column=0, sticky="ew")
        host.columnconfigure(0, weight=1)
        self.convert_options_host = host

        # Encoding
        self.encoding_options_frame = self._section(host, 0, t("ui.convert.enc_section"))
        detect_row = ttk.Frame(self.encoding_options_frame)
        detect_row.grid(row=0, column=0, sticky="w")
        ttk.Label(detect_row, text=t("ui.convert.detected")).pack(side=tk.LEFT)
        self.detected_encoding_var = tk.StringVar(value=t("ui.convert.select_file"))
        self.encoding_label = ttk.Label(detect_row, textvariable=self.detected_encoding_var, font="BissBold")
        self.encoding_label.pack(side=tk.LEFT, padx=(PAD_S, 0))
        enc_row = ttk.Frame(self.encoding_options_frame)
        enc_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        enc_row.columnconfigure(2, weight=1)
        ttk.Label(enc_row, text=t("ui.convert.convert_to")).grid(row=0, column=0, sticky="w")
        self.convert_encoding_var = tk.StringVar(value=self.settings.get("convert.encoding", "utf-8"))
        ttk.Combobox(enc_row, textvariable=self.convert_encoding_var, width=12,
                     values=['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'big5', 'shift-jis']).grid(
            row=0, column=1, sticky="w", padx=(PAD_S, PAD))
        self._caption(enc_row, t("ui.convert.utf8_hint")).grid(row=0, column=2, sticky="ew")
        self.convert_backup_var = tk.BooleanVar(value=bool(self.settings.get("convert.backup", True)))
        ttk.Checkbutton(self.encoding_options_frame, text=t("ui.convert.backup"),
                        variable=self.convert_backup_var).grid(row=2, column=0, sticky="w", pady=(PAD_S + 2, 0))
        self.convert_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.encoding_options_frame, text=t("ui.convert.force"),
                        variable=self.convert_force_var).grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.convert_fix_fonts_var = tk.BooleanVar(value=bool(self.settings.get("convert.fix_fonts", True)))
        ttk.Checkbutton(self.encoding_options_frame, text=t("ui.convert.fix_fonts"),
                        variable=self.convert_fix_fonts_var).grid(row=4, column=0, sticky="w", pady=(2, 0))
        for var in (self.convert_encoding_var, self.convert_force_var):
            var.trace_add('write', lambda *a: self._update_convert_hint())

        # ASS -> SRT
        self.ass_options_frame = self._section(host, 0, t("ui.convert.ass_section"))
        self.ass_bilingual_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text=t("ui.convert.ass_keep_both"),
                        variable=self.ass_bilingual_var).grid(row=0, column=0, sticky="w")
        self.ass_strip_effects_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text=t("ui.convert.ass_strip"),
                        variable=self.ass_strip_effects_var).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.ass_output_var = tk.StringVar()
        row, _ = self._path_row(self.ass_options_frame, 2, self.ass_output_var, self._browse_ass_output,
                                label=t("ui.common.save_as"))
        row.grid_configure(pady=(PAD, 0))
        self.ass_output_var.trace_add('write', lambda *a: self._update_convert_hint())

        # PGS OCR
        self.pgs_options_frame = self._section(host, 0, t("ui.convert.pgs_section"))
        pgs_track_row = ttk.Frame(self.pgs_options_frame)
        pgs_track_row.grid(row=0, column=0, sticky="ew")
        pgs_track_row.columnconfigure(1, weight=1)
        ttk.Label(pgs_track_row, text=t("ui.convert.pgs_track")).grid(row=0, column=0, sticky="w")
        self.pgs_track_var = tk.StringVar()
        self.pgs_track_combo = ttk.Combobox(pgs_track_row, textvariable=self.pgs_track_var, width=50,
                                            state='readonly')
        self.pgs_track_combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(pgs_track_row, text=t("ui.convert.detect_tracks"), command=self._detect_pgs_tracks).grid(
            row=0, column=2, padx=(PAD_S, 0))
        pgs_lang_row = ttk.Frame(self.pgs_options_frame)
        pgs_lang_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        pgs_lang_row.columnconfigure(2, weight=1)
        ttk.Label(pgs_lang_row, text=t("ui.convert.ocr_language")).grid(row=0, column=0, sticky="w")
        self.pgs_lang_var = tk.StringVar(value="auto")
        self.pgs_lang_combo = ttk.Combobox(pgs_lang_row, textvariable=self.pgs_lang_var, width=10,
                                           state='readonly', values=['auto', 'eng', 'chi_sim', 'chi_tra', 'jpn', 'kor'])
        self.pgs_lang_combo.grid(row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self._caption(pgs_lang_row, t("ui.convert.ocr_auto_hint")).grid(
            row=0, column=2, sticky="ew", padx=(PAD, 0))
        self.pgs_output_var = tk.StringVar()
        row, _ = self._path_row(self.pgs_options_frame, 2, self.pgs_output_var, self._browse_pgs_output,
                                label=t("ui.common.save_as"))
        row.grid_configure(pady=(PAD, 0))
        self._pgs_detected_tracks = []

        # Sync (the same controls also live on the Shift Timing tab)
        self.sync_options_frame = self._section(host, 0, t("ui.convert.sync_section"))
        self.sync_track_combo = self._build_sync_controls(self.sync_options_frame, "convert")
        self._caption(self.sync_options_frame, t("ui.convert.sync_moved")).grid(
            row=3, column=0, sticky="ew", pady=(PAD_S, 0))
        self.sync_video_var.trace_add('write', lambda *a: self._update_convert_hint())

        bar = self._add_action_bar("convert", t("ui.convert.button_encoding"), self._execute_convert,
                                   t("ui.convert.hint_encoding"))
        self.convert_btn = bar.button
        self._update_convert_type()

    def _update_convert_type(self):
        """Show the options for the selected conversion (always in the same place)."""
        conv_type = self.convert_type_var.get()
        frames = {"encoding": self.encoding_options_frame, "ass_to_srt": self.ass_options_frame,
                  "pgs_ocr": self.pgs_options_frame, "sync": self.sync_options_frame}
        for frame in frames.values():
            frame.grid_remove()
        frames.get(conv_type, self.encoding_options_frame).grid()
        labels = {
            "encoding": (t("ui.convert.button_encoding"), self._execute_convert, t("ui.convert.file_section")),
            "ass_to_srt": (t("ui.convert.button_ass"), self._execute_ass_convert, t("ui.convert.file_ass")),
            "pgs_ocr": (t("ui.convert.button_pgs"), self._execute_pgs_convert, t("ui.convert.file_pgs")),
            "sync": (t("ui.convert.button_sync"), lambda: self._execute_sync("convert"), t("ui.convert.file_sync")),
        }
        text, command, file_title = labels.get(conv_type, labels["encoding"])
        self.convert_btn.config(text=text, command=command)
        self.convert_file_frame.configure(text=file_title)
        if "convert" in self._bars:
            self._bars["convert"].reset()
            self._update_convert_hint()

    def _browse_ass_output(self):
        path = self._ask_save("output", t("ui.convert.dlg_save_srt"), [(t("ui.ft.srt"), "*.srt"), (t("ui.ft.all"), "*.*")],
                              ".srt", current=self.ass_output_var.get().strip())
        if path:
            self.ass_output_var.set(path)

    def _on_convert_drop(self, paths: list[str]):
        if not paths:
            return
        mode = self.convert_type_var.get()
        if mode == "sync":
            videos = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
            subs = [p for p in paths if Path(p).suffix.lower() in SUBTITLE_EXTENSIONS]
            if videos:
                self.sync_video_var.set(videos[0])
            if subs:
                self.convert_file_var.set(subs[0])
            return
        if mode == "pgs_ocr":
            self.convert_file_var.set(paths[0])
            return
        self._drop_subtitle(self.convert_file_var, "convert")(paths)

    def _execute_ass_convert(self):
        """Execute ASS to SRT conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        input_path = self.convert_file_var.get().strip()
        output_path = self.ass_output_var.get().strip()
        if not input_path:
            self._invalid(key, t("ui.convert.hint_ass"))
            return
        if not Path(input_path).is_file():
            self._invalid(key, t("ui.common.file_not_found", path=input_path))
            return
        if not input_path.lower().endswith(('.ass', '.ssa')):
            self._invalid(key, t("ui.convert.not_ass"))
            return
        output_path = output_path or str(Path(input_path).with_suffix('.srt'))
        if Path(output_path).exists() and not self._confirm_replace(Path(output_path)):
            self._bars[key].finish("cancelled", t("ui.common.kept_existing", name=Path(output_path).name))
            return
        strip_effects = self.ass_strip_effects_var.get()
        bilingual = self.ass_bilingual_var.get()

        def work(cancel):
            from core.ass_converter import ASSToSRTConverter
            converter = ASSToSRTConverter(strip_effects=strip_effects, preserve_bilingual=bilingual)
            return converter.convert_file(Path(input_path), Path(output_path))

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, t("ui.convert.failed"), result)
                return
            out = Path(result) if result else Path(output_path)
            self._bars[key].finish("success", t("ui.common.saved", name=out.name), actions=self._output_actions(out))
            self._set_status("✔ " + t("ui.common.saved", name=out.name), key)

        self._run_task(key, t("ui.convert.running_ass"), work, done)

    def _browse_pgs_output(self):
        path = self._ask_save("output", t("ui.convert.dlg_save_srt"), [(t("ui.ft.srt"), "*.srt"), (t("ui.ft.all"), "*.*")],
                              ".srt", current=self.pgs_output_var.get().strip())
        if path:
            self.pgs_output_var.set(path)

    def _detect_pgs_tracks(self):
        """Detect PGS tracks in the selected file (in the background, one at a time)."""
        key = "convert"
        if self._bars[key].busy:
            return
        if not self._pgsrip_wrapper:
            self._invalid(key, t("ui.convert.pgs_unavailable"))
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, t("ui.convert.hint_pgs"))
            return
        input_file = Path(input_path)
        if not input_file.is_file():
            self._invalid(key, t("ui.common.file_not_found", path=input_path))
            return
        if input_file.suffix.lower() in ('.sup', '.idx', '.sub'):
            label = t("ui.convert.standalone", name=input_file.name)
            self.pgs_track_combo['values'] = [label]
            self.pgs_track_var.set(label)
            self._pgs_detected_tracks = []
            if not self.pgs_output_var.get():
                self.pgs_output_var.set(str(input_file.with_suffix('.srt')))
            self._update_convert_hint()
            return

        def work(cancel):
            return self._pgsrip_wrapper.detect_pgs_tracks(input_file)

        def done(ok, tracks, cancelled):
            bar = self._bars[key]
            if not ok:
                self._fail(key, t("ui.convert.pgs_detect_failed"), tracks)
                return
            self._pgs_detected_tracks = tracks
            if tracks:
                labels = []
                for tr in tracks:
                    title = f" - {tr.title}" if tr.title else ""
                    labels.append(f"{t('ui.merge.track_label', id=tr.track_id)}: {tr.language or '?'}{title} "
                                  f"(OCR: {tr.estimated_language})")
                self.pgs_track_combo['values'] = labels
                self.pgs_track_var.set(labels[0])
                if not self.pgs_output_var.get():
                    self.pgs_output_var.set(str(input_file.with_suffix('.pgs.srt')))
                bar.finish("info", t("ui.convert.pgs_found", n=len(tracks)))
            else:
                self.pgs_track_combo['values'] = [t("ui.convert.pgs_none")]
                self.pgs_track_var.set(t("ui.convert.pgs_none"))
                bar.finish("warning", t("ui.convert.pgs_none"))

        self._run_task(key, t("ui.convert.pgs_detecting"), work, done)

    def _execute_pgs_convert(self):
        """Execute PGS to SRT OCR conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        if not self._pgsrip_wrapper:
            self._invalid(key, t("ui.convert.pgs_unavailable"))
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, t("ui.convert.hint_pgs"))
            return
        input_file = Path(input_path)
        if not input_file.is_file():
            self._invalid(key, t("ui.common.file_not_found", path=input_path))
            return
        output_file = Path(self.pgs_output_var.get().strip() or str(input_file.with_suffix('.pgs.srt')))
        ocr_lang = None if self.pgs_lang_var.get() == 'auto' else self.pgs_lang_var.get()
        standalone = input_file.suffix.lower() in ('.sup', '.idx', '.sub')
        track = None
        if not standalone:
            if not self._pgs_detected_tracks:
                self._invalid(key, t("ui.convert.pgs_detect_first"))
                return
            values = list(self.pgs_track_combo['values'] or [])
            idx = values.index(self.pgs_track_var.get()) if self.pgs_track_var.get() in values else 0
            track = self._pgs_detected_tracks[idx if idx < len(self._pgs_detected_tracks) else 0]
        if output_file.exists() and not self._confirm_replace(output_file):
            self._bars[key].finish("cancelled", t("ui.common.kept_existing", name=output_file.name))
            return

        def work(cancel):
            if standalone:
                return self._pgsrip_wrapper.convert_subtitle_file(input_file, output_file, ocr_lang or 'eng')
            return self._pgsrip_wrapper.convert_pgs_track(input_file, track, output_file, ocr_lang)

        def done(ok, result, cancelled):
            if not ok or not result:
                self._fail(key, t("ui.convert.pgs_failed"), result if not ok else None)
                return
            self._bars[key].finish("success", t("ui.common.saved", name=output_file.name),
                                   actions=self._output_actions(output_file))
            self._set_status("✔ " + t("ui.common.saved", name=output_file.name), key)

        self._run_task(key, t("ui.convert.pgs_running"), work, done)

    def _browse_convert_file(self):
        """Browse for file to convert (subtitle, video, or SUP depending on mode)."""
        mode = self.convert_type_var.get()
        if mode == 'pgs_ocr':
            filetypes = [(t("ui.ft.video_sup"), "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.sup"),
                         (t("ui.ft.sup"), "*.sup"), (t("ui.ft.videos"), "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"),
                         (t("ui.ft.vobsub"), "*.idx *.sub"), (t("ui.ft.all"), "*.*")]
            title, kind = t("ui.convert.dlg_video_or_sup"), "video"
        elif mode == 'sync':
            filetypes = [(t("ui.ft.srt"), "*.srt"), (t("ui.ft.subtitles"), "*.srt *.ass *.ssa *.vtt"),
                         (t("ui.ft.all"), "*.*")]
            title, kind = t("ui.convert.dlg_sync_sub"), "subtitle"
        elif mode == 'ass_to_srt':
            filetypes = [(t("ui.ft.ass_ssa"), "*.ass *.ssa"), (t("ui.ft.all"), "*.*")]
            title, kind = t("ui.convert.dlg_ass"), "subtitle"
        else:
            filetypes, title, kind = _subtitle_types(), t("ui.dlg.select_subtitle"), "subtitle"
        path = self._ask_open(kind, title, filetypes)
        if path:
            self.convert_file_var.set(path)

    def _browse_sync_video(self, key: str = "convert"):
        path = self._ask_open("video", t("ui.dlg.select_video"), _video_types())
        if path:
            self.sync_video_var.set(path)
            self._load_sync_tracks(key)

    def _on_sync_video_drop(self, key: str, paths: list[str]):
        videos = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
        if not videos:
            if paths:
                self._invalid(key, t("ui.drop.need_video", name=Path(paths[0]).name))
            return
        self.sync_video_var.set(videos[0])
        self._load_sync_tracks(key)

    def _load_sync_tracks(self, key: str = "convert"):
        """Load subtitle tracks from the video for the reference-track choice."""
        if self._bars[key].busy:
            return
        video_path = self.sync_video_var.get().strip()
        if not video_path or not Path(video_path).is_file():
            self._invalid(key, t("ui.sync.need_valid_video"))
            return
        if missing_tools("ffmpeg"):
            self._invalid(key, t("ui.sync.need_ffmpeg") + " " + install_hint("ffmpeg"))
            return
        self.sync_result_var.set(t("ui.sync.loading"))

        def work(cancel):
            from processors.subtitle_sync import SubtitleSync
            tracks = SubtitleSync().list_subtitle_tracks(Path(video_path))
            return [tr for tr in tracks if tr['is_text']]

        def done(ok, text_tracks, cancelled):
            bar = self._bars[key]
            if not ok:
                self.sync_result_var.set(t("ui.sync.load_failed", error=text_tracks))
                self._fail(key, t("ui.sync.load_failed_title"), text_tracks, dialog=False)
                return
            labels = [t("ui.sync.auto_track")] + [
                f"s:{tr['rel_index']} {tr['lang']} {tr['title']} ({tr['codec']})".strip() for tr in text_tracks]
            self._sync_tracks_data = text_tracks
            self._update_sync_track_combo(labels)
            self.sync_result_var.set(t("ui.sync.found", n=len(text_tracks)))
            bar.reset()
            if key == "shift":
                self._validate_shift()
            else:
                self._update_convert_hint()

        self._run_task(key, t("ui.sync.loading"), work, done)

    def _update_sync_track_combo(self, labels):
        for combo in (getattr(self, "sync_track_combo", None), getattr(self, "shift_sync_track_combo", None)):
            if combo is not None:
                combo['values'] = labels
        if labels:
            self.sync_track_var.set(labels[0])

    def _sync_inputs(self, key: str = "convert"):
        sub_var = self.shift_file_var if key == "shift" else self.convert_file_var
        sub_path = sub_var.get().strip()
        video_path = self.sync_video_var.get().strip()
        if not sub_path or not Path(sub_path).is_file():
            self._invalid(key, t("ui.sync.need_sub"))
            return None
        if not video_path or not Path(video_path).is_file():
            self._invalid(key, t("ui.sync.need_video"))
            return None
        if missing_tools("ffmpeg"):
            self._invalid(key, t("ui.sync.need_ffmpeg") + " " + install_hint("ffmpeg"))
            return None
        track_index = None
        selection = self.sync_track_var.get()
        if selection.startswith("s:"):
            try:
                track_index = int(selection.split()[0].split(':')[1])
            except (ValueError, IndexError):
                pass
        return Path(sub_path), Path(video_path), track_index

    def _detect_sync_offset(self, key: str = "convert"):
        """Measure the timing offset without changing the file."""
        if self._bars[key].busy:
            return
        inputs = self._sync_inputs(key)
        if not inputs:
            return
        sub_path, video_path, track_index = inputs
        self.sync_result_var.set(t("ui.sync.detecting"))

        def work(cancel):
            from processors.subtitle_sync import SubtitleSync
            return SubtitleSync().sync_file(video_path=video_path, srt_path=sub_path,
                                            track_index=track_index, dry_run=True)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            button = t("ui.shift.button_sync") if key == "shift" else t("ui.convert.button_sync")
            if not ok:
                self.sync_result_var.set(t("ui.sync.error", error=result))
                self._fail(key, t("ui.sync.detect_failed"), result, dialog=False)
            elif result.success:
                self.sync_result_var.set(t("ui.sync.measured", ms=f"{result.offset_ms:+d}", matches=result.match_count,
                                           total=result.total_compared, track=result.track_used))
                bar.finish("info", t("ui.sync.off_by", s=f"{result.offset_ms / 1000:+.2f}", button=button))
            else:
                self.sync_result_var.set(t("ui.sync.error", error=result.message))
                self._fail(key, t("ui.sync.detect_failed"), result.message, dialog=False)

        self._run_task(key, t("ui.sync.comparing"), work, done)

    def _execute_sync(self, key: str = "convert", output_path: Path | None = None, backup: bool = True):
        """Detect the offset and apply it.

        Convert > Sync fixes the file in place (a backup is kept). Shift Timing >
        Match a video can write a new file instead. In that case the offset is
        detected on the untouched original first and the target is written only
        once detection has succeeded, so a failed sync never leaves an unshifted
        copy (or replaces a good earlier result) under the output name.
        """
        if self._bars[key].busy:
            return
        inputs = self._sync_inputs(key)
        if not inputs:
            return
        sub_path, video_path, track_index = inputs
        target = Path(output_path) if output_path else sub_path

        def work(cancel):
            from processors.subtitle_sync import SubtitleSync
            if target == sub_path:
                return SubtitleSync().sync_file(video_path=video_path, srt_path=target, track_index=track_index,
                                                backup=backup, dry_run=False)
            return _sync_to_new_file(SubtitleSync(), video_path, sub_path, target, track_index)

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, t("ui.sync.failed"), result)
            elif result.success:
                self.sync_result_var.set(t("ui.sync.applied", ms=f"{result.shift_applied_ms:+d}",
                                           matches=result.match_count, total=result.total_compared))
                note = t("ui.common.backup_kept") if target == sub_path and backup else ""
                text = t("ui.sync.done", name=target.name, s=f"{result.shift_applied_ms / 1000:+.2f}") + note
                self._bars[key].finish("success", text, actions=self._output_actions(target))
                self._set_status("✔ " + text, key)
            else:
                self.sync_result_var.set(t("ui.sync.error", error=result.message))
                self._fail(key, t("ui.sync.failed"), result.message)

        self._run_task(key, t("ui.sync.running"), work, done)

    def _execute_convert(self):
        """Execute the encoding conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, t("ui.convert.hint_encoding"))
            return
        if not Path(input_path).is_file():
            self._invalid(key, t("ui.common.file_not_found", path=input_path))
            return
        encoding = self.convert_encoding_var.get().strip() or "utf-8"
        try:
            import codecs
            codecs.lookup(encoding)
        except LookupError:
            self._invalid(key, t("ui.convert.unknown_encoding", enc=encoding))
            return
        create_backup = self.convert_backup_var.get()
        force = self.convert_force_var.get()
        fix_fonts = self.convert_fix_fonts_var.get()

        def work(cancel):
            from processors.converter import EncodingConverter
            return EncodingConverter().convert_file(file_path=Path(input_path), keep_backup=create_backup,
                                                    force_conversion=force, target_encoding=encoding,
                                                    fix_fonts=fix_fonts)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok:
                self._fail(key, t("ui.convert.failed"), result)
                return
            name = Path(input_path).name
            if result.modified:
                text = t("ui.convert.converted", name=name, enc=encoding_name(encoding))
                if result.fonts_fixed:
                    text += t("ui.convert.fonts_fixed", n=len(result.fonts_fixed))
                    for style_name, old_font, new_font in result.fonts_fixed:
                        logger.info(f"  [{style_name}] '{old_font}' -> '{new_font}'")
                if create_backup:
                    text += t("ui.common.backup_kept")
                bar.finish("success", text, actions=self._output_actions(Path(input_path)))
                self._file_info.pop(input_path, None)
                self._on_convert_file_changed(keep_result=True)
                self._set_status("✔ " + text, key)
            else:
                text = t("ui.convert.no_change", name=name, enc=encoding_name(encoding))
                bar.finish("info", text)
                self._set_status(text, key)

        self._run_task(key, t("ui.convert.running_encoding"), work, done)

    def _detect_encoding(self):
        """Refresh the detected encoding for the selected file (runs in the background)."""
        self._file_info.pop(self.convert_file_var.get().strip(), None)
        self._on_convert_file_changed()

    # ======================================================================
    # Batch tab
    # ======================================================================

    def _create_batch_tab(self):
        """Create the Batch Operations tab."""
        _tab, body = self._new_tab("batch", t('gui.tab_batch').strip())
        self._intro(body, 0, t("ui.batch.intro"))

        op_frame = self._section(body, 1, t("ui.batch.op_section"))
        self.batch_op_var = tk.StringVar(value=self.settings.get("batch.op", "convert"))
        ttk.Radiobutton(op_frame, text=t("ui.batch.op_convert"),
                        variable=self.batch_op_var, value="convert",
                        command=self._update_batch_options).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(op_frame, text=t("ui.batch.op_merge"),
                        variable=self.batch_op_var, value="merge",
                        command=self._update_batch_options).grid(row=1, column=0, sticky="w", pady=(2, 0))

        dir_frame = self._section(body, 2, t("ui.batch.folder_section"))
        self.batch_dir_var = tk.StringVar()
        self._path_row(dir_frame, 0, self.batch_dir_var, self._browse_batch_dir,
                       drop=self._drop_folder(self.batch_dir_var))
        self.batch_dir_var.trace_add('write', lambda *a: self._update_batch_hint())
        self.batch_recursive_var = tk.BooleanVar(value=bool(self.settings.get("batch.recursive", True)))
        ttk.Checkbutton(dir_frame, text=t("ui.batch.recursive"),
                        variable=self.batch_recursive_var).grid(row=1, column=0, sticky="w", pady=(PAD_S + 2, 0))

        options = self._section(body, 3, t("ui.merge.options"))
        self.batch_backup_var = tk.BooleanVar(value=bool(self.settings.get("batch.backup", True)))
        self.batch_backup_check = ttk.Checkbutton(options, text=t("ui.batch.backup"),
                                                  variable=self.batch_backup_var)
        self.batch_backup_check.grid(row=0, column=0, sticky="w")
        self.batch_autoconfirm_var = tk.BooleanVar(value=bool(self.settings.get("batch.autoconfirm", False)))
        self.batch_autoconfirm_check = ttk.Checkbutton(
            options, text=t("ui.batch.autoconfirm"), variable=self.batch_autoconfirm_var)
        self.batch_autoconfirm_check.grid(row=1, column=0, sticky="w", pady=(2, 0))

        results = self._section(body, 4, t("ui.batch.results_section"))
        results.rowconfigure(1, weight=1)
        self.batch_progress_var = tk.StringVar(value=t("ui.batch.nothing_yet"))
        ttk.Label(results, textvariable=self.batch_progress_var).grid(row=0, column=0, sticky="w")
        list_frame = ttk.Frame(results)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(PAD_S, 0))
        list_frame.columnconfigure(0, weight=1)
        self.batch_results = tk.Listbox(list_frame, height=6, activestyle="none", relief="flat",
                                        highlightthickness=1, font="BissBody")
        self.batch_results.grid(row=0, column=0, sticky="nsew")
        results_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.batch_results.yview)
        results_scroll.grid(row=0, column=1, sticky="ns")
        self.batch_results.configure(yscrollcommand=results_scroll.set)
        self.batch_progress_bar = None  # the action bar shows progress now

        bar = self._add_action_bar("batch", t("ui.batch.button"), self._execute_batch, t("ui.batch.hint_start"))
        self.batch_btn = bar.button
        self.batch_progress_bar = bar.progressbar
        self._update_batch_options()

    def _update_batch_options(self):
        merge = self.batch_op_var.get() == "merge"
        self.batch_backup_check.state(["disabled"] if merge else ["!disabled"])
        self.batch_autoconfirm_check.configure(
            text=t("ui.batch.autoconfirm_merge") if merge else t("ui.batch.autoconfirm"))
        self._update_batch_hint()

    def _update_batch_hint(self):
        bar = self._bars.get("batch")
        if bar is None:
            return
        folder = self.batch_dir_var.get().strip()
        if not folder:
            bar.set_hint(t("ui.batch.hint_start"))
        elif not Path(folder).is_dir():
            bar.set_hint(t("ui.common.folder_not_found", path=folder), "warning")
        else:
            what = t("ui.batch.what_merge") if self.batch_op_var.get() == "merge" else t("ui.batch.what_convert")
            bar.set_hint(t("ui.batch.ready", what=what, folder=Path(folder).name or folder))

    def _browse_batch_dir(self):
        path = self._ask_dir("folder", t("ui.batch.dlg_folder"))
        if path:
            self.batch_dir_var.set(path)

    def _execute_batch(self):
        """Run a batch operation with per-file progress, results as they happen, and Cancel."""
        key = "batch"
        if self._bars[key].busy:
            return
        directory = self.batch_dir_var.get().strip()
        if not directory:
            self._invalid(key, t("ui.batch.need_folder"))
            return
        if not Path(directory).is_dir():
            self._invalid(key, t("ui.common.folder_not_found", path=directory))
            return
        operation = self.batch_op_var.get()
        if operation == "merge" and missing_tools("ffmpeg") and not messagebox.askyesno(
                t("ui.batch.ffmpeg_title"), t("ui.batch.ffmpeg_body"), icon="warning", parent=self.root):
            self._bars[key].finish("warning", install_hint("ffmpeg"),
                                   actions=[(t("ui.tools.download"), lambda: self._open_download_page("ffmpeg"))])
            return
        recursive = self.batch_recursive_var.get()
        create_backup = self.batch_backup_var.get()
        auto_confirm = self.batch_autoconfirm_var.get()
        bar = self._bars[key]
        self.batch_results.delete(0, tk.END)

        def add_result(line: str, color: str | None = None):
            def add():
                self.batch_results.insert(tk.END, line)
                if color:
                    self.batch_results.itemconfigure(tk.END, foreground=color)
                self.batch_results.see(tk.END)
            self._post(add)

        def work(cancel):
            from processors.batch_processor import BatchProcessor
            from utils.file_operations import FileHandler
            processor = BatchProcessor(auto_confirm=auto_confirm)

            if operation == "convert":
                files = FileHandler.find_subtitle_files(Path(directory), recursive)
                if not files:
                    return {"empty": t("ui.batch.no_subs")}
                if not auto_confirm:
                    note = t("ui.batch.backups_note") if create_backup else ""
                    if not self._call_in_main(lambda: messagebox.askyesno(
                            t("ui.batch.confirm_title"), t("ui.batch.confirm_convert", n=len(files)) + note,
                            parent=self.root), cancel):
                        return {"declined": True}

                def progress(done_n, total, path):
                    self._post(lambda: (bar.progress(t("ui.batch.progress", i=done_n, n=total, name=path.name),
                                                     done_n, total),
                                        self.batch_progress_var.set(t("ui.batch.converting", i=done_n, n=total))))

                def file_done(path, status, error):
                    if status == "converted":
                        add_result(f"✔ {path.name} – {t('ui.batch.r_converted')}", SUCCESS)
                    elif status == "unchanged":
                        add_result(f"· {path.name} – {t('ui.batch.r_unchanged')}", MUTED)
                    else:
                        add_result(f"✖ {path.name} – {error or t('ui.batch.r_failed')}", ERROR)

                results = processor.process_subtitles_batch(subtitle_paths=files, operation="convert",
                                                            parallel=False, progress_callback=progress,
                                                            cancel_event=cancel, file_result_callback=file_done,
                                                            keep_backup=create_backup)
                return {"op": "convert", "results": results}

            videos = FileHandler.find_video_files(Path(directory), recursive)
            if not videos:
                return {"empty": t("ui.batch.no_videos")}

            def confirm(video, index, total):
                answer = self._call_in_main(lambda: messagebox.askyesnocancel(
                    t("ui.batch.process_title"), t("ui.batch.process_body", i=index, n=total, name=video.name),
                    parent=self.root), cancel)
                return 'y' if answer else ('n' if answer is False else 'q')

            def progress(index, total, video):
                self.log_handler.last_error = None
                if video is not None:
                    self._post(lambda: (bar.progress(t("ui.batch.progress", i=index + 1, n=total, name=video.name),
                                                     index, total),
                                        self.batch_progress_var.set(t("ui.batch.merging", i=index + 1, n=total))))

            def video_done(video, status):
                if status == "merged":
                    add_result(f"✔ {video.name} – {t('ui.batch.r_merged')}", SUCCESS)
                elif status == "skipped":
                    add_result(f"· {video.name} – {t('ui.batch.r_skipped')}", MUTED)
                else:
                    reason = self.log_handler.last_error or t("ui.batch.r_failed")
                    add_result(f"✖ {video.name} – {reason}", ERROR)

            results = processor.process_directory_interactive(
                directory=Path(directory), pattern="*", recursive=recursive, video_only=True,
                confirm_callback=None if auto_confirm else confirm, progress_callback=progress,
                cancel_event=cancel, result_callback=video_done)
            return {"op": "merge", "results": results}

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, t("ui.batch.failed"), result)
                self.batch_progress_var.set(t("ui.batch.failed_short"))
                return
            if result.get("empty"):
                bar.finish("warning", result["empty"])
                self.batch_progress_var.set(result["empty"])
                return
            if result.get("declined"):
                bar.finish("cancelled", t("ui.batch.nothing_changed"))
                self.batch_progress_var.set(t("ui.batch.cancelled"))
                return
            summarize = summarize_batch_convert if result["op"] == "convert" else summarize_batch_merge
            all_ok, text = summarize(result["results"])
            text = text[0].upper() + text[1:]
            self.batch_progress_var.set(text + ("." if not text.endswith(".") else ""))
            bar.finish("success" if all_ok else "warning", text,
                       actions=[(t("ui.common.open_folder"), lambda: self._reveal(Path(directory)))]
                       + ([] if all_ok else [(t("ui.common.show_details"), lambda: self._toggle_details(True))]))
            self._set_status(("✔ " if all_ok else "⚠ ") + text, key)

        self._run_task(key, t("ui.batch.starting"), work, done, cancellable=True, determinate=True)

    # ======================================================================
    # Menu actions
    # ======================================================================

    def _open_subtitle(self):
        """File > Open Subtitle: put the file on the right Merge track by language."""
        path = self._ask_open("subtitle", t("ui.dlg.open_subtitle"), _subtitle_types())
        if path:
            self._assign_subtitle(path)
            self._select_tab("merge")

    def _open_video(self):
        path = self._ask_open("video", t("ui.dlg.open_video"), _video_types())
        if path:
            self.merge_video_var.set(path)
            self._select_tab("merge")

    # ======================================================================
    # Drag and drop from Explorer (optional: needs tkinterdnd2)
    # ======================================================================

    def _setup_drop_targets(self):
        """Accept files dropped on each path field and anywhere on each tab."""
        if not self._dnd:
            return
        tab_handlers = {
            "merge": self._on_merge_drop,
            "extract": self._on_extract_drop,
            "split": self._drop_subtitle(self.split_file_var, "split"),
            "shift": self._on_shift_drop,
            "convert": self._on_convert_drop,
            "batch": self._drop_folder(self.batch_dir_var),
        }
        for key, handler in tab_handlers.items():
            self.setup_drag_drop(self._tabs[key], handler)
        zone = self.merge_drop_zone
        self.setup_drag_drop(zone, self._on_merge_drop,
                             on_enter=lambda: zone.configure(style="DropActive.TFrame"),
                             on_leave=lambda: zone.configure(style="Drop.TFrame"))
        for entry, handler in self._drop_rows:
            self.setup_drag_drop(entry, handler)

    def _on_shift_drop(self, paths: list[str]):
        videos = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
        subs = [p for p in paths if Path(p).suffix.lower() in SUBTITLE_EXTENSIONS]
        if subs:
            self.shift_file_var.set(subs[0])
        if videos:
            self.sync_video_var.set(videos[0])
            self.shift_mode_var.set("video")
            self._update_shift_mode()
        if not subs and not videos and paths:
            self._invalid("shift", t("ui.drop.need_subtitle", name=Path(paths[0]).name))

    # ======================================================================
    # Utility methods
    # ======================================================================

    def _set_status(self, message: str, key: str | None = None):
        """Status bar text for a tab (shown while that tab is open). Full paths are shortened to names."""
        key = key or self._current_tab_key()
        self._tab_status[key] = message
        if key == self._current_tab_key():
            self.status_var.set(message)

    def _clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def _copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", tk.END))
        self._set_status(t("ui.common.log_copied"))

    def _show_help(self):
        messagebox.showinfo(t("gui.quick_guide"), t("ui.help.guide"), parent=self.root)

    def _show_shortcuts(self):
        messagebox.showinfo(t("gui.shortcuts"), t("ui.help.shortcuts"), parent=self.root)

    def _show_about(self):
        about_text = t("ui.help.about", app=APP_NAME, version=APP_VERSION, path=str(self.settings.path))
        messagebox.showinfo(t("gui.about"), about_text, parent=self.root)

    def _show_subtitle_preview(self, file_path: str | None = None):
        """Show a preview window (the file is parsed off the UI thread)."""
        if not file_path:
            file_path = self._ask_open("subtitle", t("ui.dlg.preview"), _subtitle_types())
        if not file_path:
            return
        if not Path(file_path).is_file():
            messagebox.showerror(t("ui.common.preview"), t("ui.common.file_not_found", path=file_path),
                                 parent=self.root)
            return
        key = self._current_tab_key()
        self._set_status(t("ui.preview.opening", name=Path(file_path).name), key)

        def work():
            try:
                from core.encoding_detection import EncodingDetector
                from core.subtitle_formats import SubtitleFormatFactory
                encoding = EncodingDetector.detect_encoding(Path(file_path)) or "Unknown"
                sub_file = SubtitleFormatFactory.parse_file(Path(file_path))
                self._post(lambda: self._open_preview_window(file_path, sub_file, encoding))
            except Exception as e:  # noqa: BLE001 - report any failure to the user
                self._post(lambda e=e: messagebox.showerror(t("ui.preview.error_title"),
                                                            t("ui.preview.error", error=e), parent=self.root))
            finally:
                self._post(lambda: self._set_status(t('gui.status_ready'), key))

        threading.Thread(target=work, daemon=True).start()

    def _open_preview_window(self, file_path: str, sub_file, encoding: str):
        win = tk.Toplevel(self.root)
        win.title(t("ui.preview.title", name=Path(file_path).name))
        win.transient(self.root)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        w, h = int(700 * self.scale), int(500 * self.scale)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        win.geometry(f"{min(w, sw - 40)}x{min(h, sh - 80)}")
        win.minsize(int(360 * self.scale), int(240 * self.scale))

        info = ttk.Frame(win, padding=(PAD_L, PAD_L, PAD_L, PAD))
        info.grid(row=0, column=0, sticky="ew")
        ttk.Label(info, text=Path(file_path).name, style="Heading.TLabel").pack(anchor='w')
        ttk.Label(info, text=f"{t('ui.preview.lines', n=len(sub_file.events))} · {encoding_name(encoding)} · "
                             f"{sub_file.format.value.upper()}", style='Caption.TLabel').pack(anchor='w')

        text = scrolledtext.ScrolledText(win, wrap=tk.WORD, font="BissMono", relief="flat",
                                         highlightthickness=1, borderwidth=1)
        text.grid(row=1, column=0, sticky="nsew", padx=PAD_L)
        def ts(sec):
            return f"{int(sec // 3600):02d}:{int((sec % 3600) // 60):02d}:{sec % 60:06.3f}"

        lines = []
        max_events = min(200, len(sub_file.events))
        for i, event in enumerate(sub_file.events[:max_events]):
            lines.append(f"[{i + 1}] {ts(event.start)} --> {ts(event.end)}")
            lines.append(event.text)
            lines.append("")
        if len(sub_file.events) > max_events:
            lines.append(t("ui.preview.more", n=len(sub_file.events) - max_events))
        text.insert(tk.END, "\n".join(lines))
        text.config(state='disabled')

        buttons = ttk.Frame(win, padding=PAD_L)
        buttons.grid(row=2, column=0, sticky="e")
        ttk.Button(buttons, text=t("ui.common.open_folder"), command=lambda: self._reveal(Path(file_path))).pack(
            side=tk.LEFT, padx=(0, PAD))
        close = ttk.Button(buttons, text=t("ui.common.close"), command=win.destroy, default="active")
        close.pack(side=tk.LEFT)
        win.bind("<Escape>", lambda e: win.destroy())
        close.focus_set()

    # ======================================================================
    # Settings and shutdown
    # ======================================================================

    def _restore_state(self):
        last = self.settings.get("last_tab", "merge")
        if last in self._tabs:
            self._select_tab(last)
        if self.settings.get("details_open"):
            self._toggle_details(True)

    def _collect_settings(self):
        s = self.settings
        try:
            if self.root.state() == "zoomed":
                s.set("zoomed", True)
            else:
                s.set("zoomed", False)
                s.set("geometry", self.root.geometry())
        except tk.TclError:
            pass
        s.set("last_tab", self._current_tab_key())
        s.set("details_open", bool(self.details_open.get()))
        s.set("merge.format", self.merge_format_var.get())
        s.set("merge.top", self.merge_top_var.get())
        s.set("merge.autosync", bool(self.merge_autosync_var.get()))
        s.set("merge.autoalign", bool(self.merge_autoalign_var.get()))
        try:
            s.set("merge.threshold", parse_threshold(self.merge_threshold_var.get()))
        except ValueError:
            pass
        s.set("shift.overwrite", bool(self.shift_overwrite_var.get()))
        s.set("shift.backup", bool(self.shift_backup_var.get()))
        s.set("convert.encoding", self.convert_encoding_var.get())
        s.set("convert.backup", bool(self.convert_backup_var.get()))
        s.set("convert.fix_fonts", bool(self.convert_fix_fonts_var.get()))
        s.set("split.format", self.split_format_var.get())
        s.set("split.strip", bool(self.split_strip_var.get()))
        s.set("batch.op", self.batch_op_var.get())
        s.set("batch.recursive", bool(self.batch_recursive_var.get()))
        s.set("batch.backup", bool(self.batch_backup_var.get()))
        s.set("batch.autoconfirm", bool(self.batch_autoconfirm_var.get()))

    def _on_close(self):
        if self._running:
            names = ", ".join(sorted(self._running))
            if not messagebox.askyesno(t("ui.close.title"), t("ui.close.body", names=names),
                                       icon="warning", parent=self.root):
                return
            for ev in self._running.values():
                ev.set()
        self._collect_settings()
        self.settings.save()
        self._stop_pump()
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for GUI."""
    app = BISSGui()
    app.run()


if __name__ == '__main__':
    main()
