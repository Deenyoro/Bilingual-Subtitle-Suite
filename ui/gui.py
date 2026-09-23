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
    PAD,
    PAD_L,
    PAD_S,
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

TAB_KEYS = ["merge", "extract", "split", "shift", "convert", "batch"]


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
    """Mixin to add drag-and-drop support (active only when tkinterdnd2 is present)."""

    def setup_drag_drop(self, widget, callback):
        """Set up drag and drop for a widget."""
        try:
            widget.drop_target_register('DND_Files')
            widget.dnd_bind('<<Drop>>', callback)
        except (AttributeError, tk.TclError) as e:
            logger.debug(f"Drag and drop unavailable: {e}")


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
        self.chip.show("Reading file…", "busy")
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


class BISSGui:
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
        self._setup_logging()

        # Build the interface
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._create_header()
        self._create_main_interface()
        self._create_details_pane()
        self._create_status_bar()
        self._create_menu()
        self._bind_shortcuts()
        self._restore_state()

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

    # ======================================================================
    # Shell: header, tabs, details, status bar, menus
    # ======================================================================

    def _create_header(self):
        """Compact header: logo mark, product name, tagline."""
        header = ttk.Frame(self.root, padding=(PAD_L, PAD, PAD_L, PAD_S))
        header.grid(row=0, column=0, sticky="ew")
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
        ttk.Button(top, text="Copy", command=self._copy_log, style="Link.TButton").grid(row=0, column=1, padx=(PAD_S, 0))
        ttk.Button(top, text=t('gui.clear'), command=self._clear_log, style="Link.TButton").grid(row=0, column=2, padx=(PAD_S, 0))
        self.log_text = scrolledtext.ScrolledText(self.details_frame, height=8, state='disabled',
                                                  font="BissMono", wrap=tk.WORD, relief="flat",
                                                  borderwidth=1, highlightthickness=1)
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(PAD_S, 0))
        self.details_open = tk.BooleanVar(value=False)

    def _create_status_bar(self):
        """Status text on the left, Details toggle and size grip on the right."""
        status_frame = ttk.Frame(self.root, padding=(PAD, 2, 0, 2))
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
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
        self.details_btn.configure(text=f"Details {arrow}")

    def _create_menu(self):
        """Create the menu bar (generated from the tab registry)."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.file_menu'), menu=file_menu, underline=0)
        file_menu.add_command(label=t('gui.open_subtitle'), command=self._open_subtitle,
                              accelerator="Ctrl+O", underline=0)
        file_menu.add_command(label=t('gui.open_video'), command=self._open_video, underline=5)
        file_menu.add_separator()
        file_menu.add_command(label=t('gui.preview'), command=lambda: self._show_subtitle_preview(),
                              accelerator="Ctrl+P", underline=0)
        file_menu.add_separator()
        file_menu.add_command(label=t('gui.exit'), command=self._on_close, accelerator="Alt+F4", underline=1)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.tools_menu'), menu=tools_menu, underline=0)
        labels = {
            "merge": t('gui.merge_subtitles'), "extract": t('gui.extract_tracks'),
            "split": t('gui.split_bilingual'), "shift": t('gui.shift_timing'),
            "convert": t('gui.convert_encoding'), "batch": t('gui.batch_operations'),
        }
        for i, key in enumerate(TAB_KEYS, start=1):
            if key == "batch":
                tools_menu.add_separator()
            tools_menu.add_command(label=labels[key], accelerator=f"Ctrl+{i}",
                                   command=lambda k=key: self._select_tab(k))

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t('gui.view_menu'), menu=view_menu, underline=0)
        view_menu.add_checkbutton(label=t('gui.show_details'), variable=self.details_open,
                                  command=lambda: self._toggle_details(self.details_open.get()),
                                  accelerator="Ctrl+L", underline=5)
        lang_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label=t('gui.language'), menu=lang_menu, underline=0)
        self._locale_var = tk.StringVar(value=get_locale())
        for code, name in (("en", "English"), ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어")):
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
        code = self._locale_var.get()
        self.settings.set("locale", code)
        self.settings.save()
        messagebox.showinfo("Language", "The new language will be used the next time you start "
                                        f"{APP_NAME}.", parent=self.root)

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
        self._set_status(status or start_text)

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
                        bar.finish("info", "Finished.")

            self._post(finish)

        threading.Thread(target=runner, daemon=True, name=f"biss-{key}").start()

    def _fail(self, key: str, what: str, error: Any, dialog: bool = True):
        """Show a failure inline (and in a dialog): what failed, why, where to look."""
        reason = str(error) if error else (self.log_handler.last_error or "")
        reason = reason.strip() or "No details were reported."
        text = f"{what}: {reason}"
        self._bars[key].finish("error", text, actions=[("Show details", lambda: self._toggle_details(True))])
        self._set_status(f"✖ {what}")
        if dialog:
            messagebox.showerror(what, f"{reason}\n\nThe Details pane (View → Show Details) has the full log.",
                                 parent=self.root)

    def _invalid(self, key: str, message: str, focus: tk.Widget | None = None):
        """Inline validation error in the tab's action bar (no modal dialog)."""
        self._bars[key].finish("error", message)
        self._set_status(message)
        self.root.bell()
        if focus is not None:
            try:
                focus.focus_set()
            except tk.TclError:
                pass

    def _output_actions(self, path: Path | None, preview: bool = True):
        actions = []
        if path:
            actions.append(("Open folder", lambda p=Path(path): self._reveal(p)))
            if preview and Path(path).suffix.lower() in (".srt", ".ass", ".ssa", ".vtt"):
                actions.append(("Preview", lambda p=str(path): self._show_subtitle_preview(p)))
        return actions

    def _reveal(self, path: Path):
        try:
            reveal_in_file_manager(path)
        except Exception as e:  # noqa: BLE001 - report any failure to the user
            messagebox.showerror("Couldn't open folder", str(e), parent=self.root)

    def _report_callback_exception(self, exc, val, tb):
        """Friendly dialog instead of a traceback in the (hidden) console."""
        details = "".join(traceback.format_exception(exc, val, tb))
        logger.error(f"Unexpected error: {val}")
        logging.getLogger(__name__).debug(details)
        try:
            self._show_error_details("Something went wrong",
                                     f"{val}\n\nYour files were not changed by this error. "
                                     "You can copy the details below if you want to report it.",
                                     details)
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

        ttk.Button(buttons, text="Copy details", command=copy).pack(side="left", padx=(0, PAD))
        close = ttk.Button(buttons, text="Close", command=win.destroy, default="active")
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
        self._translation_key_available = key
        if key:
            self._translation_check.state(["!disabled"])
            self._translation_hint.configure(text="")
        else:
            self.merge_translation_var.set(False)
            self._translation_check.state(["disabled"])
            self._translation_hint.configure(
                text="Needs a Google Cloud Translation API key (GOOGLE_TRANSLATE_API_KEY in a .env file).")
        self._refresh_tool_banners()

    def _refresh_tool_banners(self):
        missing = getattr(self, "_missing", {"ffmpeg": [], "mkvtoolnix": []})
        if missing["mkvtoolnix"]:
            self.extract_banner.show(
                "Extracting tracks needs MKVToolNix, which was not found on this computer. "
                + install_hint("mkvtoolnix"),
                self._tool_banner_actions("mkvtoolnix"))
            self._bars["extract"].set_hint("Install MKVToolNix to extract tracks (see the note above).", "warning")
        else:
            self.extract_banner.hide()
            self._bars["extract"].set_hint(self._extract_hint)
        video = self.merge_video_var.get().strip()
        if missing["ffmpeg"] and video:
            self.merge_banner.show(
                "Reading subtitles inside a video needs FFmpeg, which was not found. "
                "Merging two subtitle files works without it. " + install_hint("ffmpeg"),
                self._tool_banner_actions("ffmpeg"))
        else:
            self.merge_banner.hide()

    def _tool_banner_actions(self, group: str):
        return [("Check again", self._recheck_tools),
                ("Locate folder…", lambda g=group: self._locate_tool_folder(g)),
                ("Download page", lambda g=group: self._open_download_page(g))]

    def _recheck_tools(self):
        self._missing = {"ffmpeg": missing_tools("ffmpeg"), "mkvtoolnix": missing_tools("mkvtoolnix")}
        self._refresh_tool_banners()
        found = [g for g, m in self._missing.items() if not m]
        self._set_status("Found: " + ", ".join(found) if found else "Tools still not found")
        if not self._missing["ffmpeg"] and self.merge_video_var.get().strip():
            self._scan_video_tracks(quiet=True)

    def _locate_tool_folder(self, group: str):
        exe = "ffmpeg.exe" if group == "ffmpeg" else "mkvextract.exe"
        folder = filedialog.askdirectory(title=f"Choose the folder that contains {exe}",
                                         initialdir=self.settings.last_dir("tools"), parent=self.root)
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not folder_has_tools(folder, group):
            bin_dir = os.path.join(folder, "bin")
            if folder_has_tools(bin_dir, group):
                folder = bin_dir
            else:
                messagebox.showerror("Not found", f"{exe} was not found in:\n{folder}", parent=self.root)
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
            chip.show("Reading file…", "busy")
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
                  label: str | None = None, preview: bool = False, extra=()):
        """label | entry (stretches) | Browse... | [Preview] | extras"""
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
        ttk.Button(frame, text="Browse...", command=browse).grid(row=0, column=col, padx=(PAD_S + 2, 0))
        col += 1
        if preview:
            ttk.Button(frame, text="Preview", command=lambda: self._show_subtitle_preview(var.get())).grid(
                row=0, column=col, padx=(PAD_S, 0))
            col += 1
        for text, cmd in extra:
            ttk.Button(frame, text=text, command=cmd).grid(row=0, column=col, padx=(PAD_S, 0))
            col += 1
        return frame, entry

    def _section(self, parent, row: int, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=(PAD_L, PAD_S + 2, PAD_L, PAD_L - 2))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD))
        frame.columnconfigure(0, weight=1)
        return frame

    @staticmethod
    def _caption(parent, text: str = "", width: int = 300, **kw) -> ttk.Label:
        """Grey helper text that re-wraps to the width it is given (put it in a weighted column)."""
        label = ttk.Label(parent, text=text, style="Caption.TLabel", justify="left", wraplength=width, **kw)
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
        self.language_options = ['Any', 'Chinese', 'Japanese', 'Korean', 'English', 'Spanish', 'French', 'German', 'Other']

        self._intro(body, 0, "Show two languages at once: add two subtitle files (any order) or a video "
                             "that contains subtitles, check which line goes on top, then click Merge.")

        # --- quick start --------------------------------------------------
        quick = ttk.Frame(body)
        quick.grid(row=1, column=0, sticky="ew", pady=(0, PAD))
        quick.columnconfigure(1, weight=1)
        ttk.Button(quick, text="Add subtitle files…", command=self._add_subtitle_files).grid(
            row=0, column=0, sticky="w")
        self._caption(quick, "Pick both files at once – each one goes to the right track by language.").grid(
            row=0, column=1, sticky="ew", padx=(PAD, 0))

        # --- video ----------------------------------------------------------
        video_frame = self._section(body, 2, "Video (optional – to use subtitles inside the video)")
        self.merge_video_frame = video_frame
        self.merge_video_var = tk.StringVar()
        self.merge_video_var.trace_add('write', lambda *a: self._on_video_changed())
        self._path_row(video_frame, 0, self.merge_video_var, self._browse_merge_video,
                       extra=[("Scan Tracks", self._scan_video_tracks)])
        self.tracks_frame = ttk.Frame(video_frame)
        self.tracks_frame.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))
        self.tracks_label = ttk.Label(self.tracks_frame, text="No video selected", style='Caption.TLabel',
                                      wraplength=560, justify="left")
        self.tracks_label.pack(anchor='w', fill=tk.X)
        self.tracks_label.bind("<Configure>", lambda e: self.tracks_label.configure(wraplength=max(200, e.width)))
        self.merge_banner = Banner(video_frame, row=2, column=0, sticky="ew", pady=(PAD, 0))

        # --- tracks ---------------------------------------------------------
        self._create_track_section(body, 3, "chinese", "Track 1 (Top Subtitle)", "Chinese")
        self._create_track_section(body, 4, "english", "Track 2 (Bottom Subtitle)", "English")

        # --- options --------------------------------------------------------
        options = self._section(body, 5, "Options")
        row0 = ttk.Frame(options)
        row0.grid(row=0, column=0, sticky="ew")
        ttk.Label(row0, text="Output format:").pack(side=tk.LEFT)
        self.merge_format_var = tk.StringVar(value=self.settings.get("merge.format", "srt"))
        fmt = ttk.Combobox(row0, textvariable=self.merge_format_var, values=['srt', 'ass'],
                           width=5, state='readonly')
        fmt.pack(side=tk.LEFT, padx=(PAD_S, PAD_L + PAD))
        self.merge_format_var.trace_add('write', lambda *a: self._update_merge_hint())
        ttk.Label(row0, text="On top:").pack(side=tk.LEFT)
        self.merge_top_var = tk.StringVar(value=self.settings.get("merge.top", "first"))
        ttk.Radiobutton(row0, text="Track 1", variable=self.merge_top_var,
                        value="first").pack(side=tk.LEFT, padx=(PAD_S, 0))
        ttk.Radiobutton(row0, text="Track 2", variable=self.merge_top_var,
                        value="second").pack(side=tk.LEFT, padx=(PAD, 0))
        ttk.Button(row0, text="⇅ Swap Tracks", command=self._swap_merge_files).pack(
            side=tk.LEFT, padx=(PAD_L, 0))

        self.merge_autosync_var = tk.BooleanVar(value=bool(self.settings.get("merge.autosync", True)))
        ttk.Checkbutton(options, text="Fix timing automatically before merging (recommended)",
                        variable=self.merge_autosync_var).grid(row=1, column=0, sticky="w", pady=(PAD, 0))

        adv = Collapsible(options, "Advanced options", opened=bool(self.settings.get("merge.advanced_open")),
                          on_toggle=lambda o: self.settings.set("merge.advanced_open", o))
        adv.grid(row=2, column=0, sticky="ew", pady=(PAD_S, 0))
        self.merge_advanced = adv
        self.merge_autoalign_var = tk.BooleanVar(value=bool(self.settings.get("merge.autoalign", False)))
        ttk.Checkbutton(adv.body, text="Match lines by meaning (names, numbers, similar text) – slower",
                        variable=self.merge_autoalign_var).grid(row=0, column=0, columnspan=3, sticky="w")
        self.merge_translation_var = tk.BooleanVar(value=False)
        self._translation_check = ttk.Checkbutton(adv.body, text="Use Google Translate to help matching",
                                                  variable=self.merge_translation_var)
        self._translation_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(PAD_S, 0))
        self._translation_hint = self._caption(adv.body)
        self._translation_hint.grid(row=2, column=0, columnspan=3, sticky="ew", padx=(PAD_L + PAD, 0))
        ttk.Label(adv.body, text="Match strictness:").grid(row=3, column=0, sticky="w", pady=(PAD_S, 0))
        self.merge_threshold_var = tk.StringVar(value=f"{float(self.settings.get('merge.threshold', 0.8)):g}")
        ttk.Spinbox(adv.body, textvariable=self.merge_threshold_var, from_=THRESHOLD_MIN, to=THRESHOLD_MAX,
                    increment=0.05, width=6, format="%.2f").grid(row=3, column=1, sticky="w",
                                                                  padx=(PAD_S, 0), pady=(PAD_S, 0))
        adv.body.columnconfigure(2, weight=1)
        self._caption(adv.body, f"{THRESHOLD_MIN}–{THRESHOLD_MAX}; higher accepts only confident matches",
                      width=200).grid(row=3, column=2, sticky="ew", padx=(PAD, 0), pady=(PAD_S, 0))

        # --- output ---------------------------------------------------------
        output = self._section(body, 6, "Output")
        self.merge_output_var = tk.StringVar()
        self.merge_output_var.trace_add('write', lambda *a: self._update_merge_hint())
        self._path_row(output, 0, self.merge_output_var, self._browse_merge_output, label="Save as:")
        self.merge_output_hint = self._caption(output, width=500)
        self.merge_output_hint.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        bar = self._add_action_bar("merge", "Merge Subtitles", self._execute_merge,
                                   "Add two subtitle files or choose a video to begin.")
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
        for i, (text, value) in enumerate((("Auto-detect", "auto"), ("Embedded track", "embedded"),
                                           ("External file", "external"))):
            ttk.Radiobutton(radios, text=text, variable=source_var, value=value, command=update).pack(
                side=tk.LEFT, padx=(0 if i == 0 else PAD_L + PAD, 0))

        auto_frame = ttk.Frame(frame)
        auto_frame.columnconfigure(2, weight=1)
        ttk.Label(auto_frame, text="Language:").grid(row=0, column=0, sticky="w")
        auto_lang_var = tk.StringVar(value=default_lang)
        ttk.Combobox(auto_frame, textvariable=auto_lang_var, values=self.language_options,
                     width=12, state='readonly').grid(row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self._caption(auto_frame, "Uses a matching track in the video or a matching file next to it").grid(
            row=0, column=2, sticky="ew", padx=(PAD, 0))

        track_frame = ttk.Frame(frame)
        track_frame.columnconfigure(1, weight=1)
        ttk.Label(track_frame, text="Track:").grid(row=0, column=0, sticky="w")
        track_var = tk.StringVar()
        combo = ttk.Combobox(track_frame, textvariable=track_var, width=45, state='readonly')
        combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(track_frame, text="Preview",
                   command=lambda: self._preview_embedded_track(slot)).grid(row=0, column=2, padx=(PAD_S, 0))

        file_var = tk.StringVar()
        file_frame, _ = self._path_row(frame, 1, file_var, lambda: self._browse_sub_file(slot),
                                       label="File:", preview=True)
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
                extra = "  ⚠ already bilingual"
            self._render_chip(chip, info, extra)
            self._update_merge_hint()

        self._analyze_later(f"merge-{slot}", path, render)
        self._update_merge_hint()

    # Kept for compatibility
    def _on_chinese_file_changed(self):
        self._on_track_file_changed("chinese")

    def _on_english_file_changed(self):
        self._on_track_file_changed("english")

    def _update_merge_hint(self):
        """Explain where the result will be saved and whether Merge is ready."""
        if not hasattr(self, "merge_output_hint") or "merge" not in self._bars:
            return
        video = self.merge_video_var.get().strip()
        s1, s2 = self.chinese_source_var.get(), self.english_source_var.get()
        f1 = self.chinese_file_var.get().strip() if s1 == "external" else ""
        f2 = self.english_file_var.get().strip() if s2 == "external" else ""
        custom = self.merge_output_var.get().strip()
        fmt = self.merge_format_var.get() or "srt"

        predicted = None
        if not custom and f1 and f2 and not video:
            i1, i2 = self._cached_info(f1), self._cached_info(f2)
            if i1 and i2 and not i1.get("error") and not i2.get("error"):
                try:
                    from core.language_detection import LanguageDetector
                    predicted = LanguageDetector.generate_bilingual_filename(
                        Path(f1), i1.get("language", "unknown"), i2.get("language", "unknown"), fmt)
                except Exception:  # noqa: BLE001 - report any failure to the user
                    predicted = None

        if custom:
            self.merge_output_hint.configure(text="")
        elif predicted:
            self.merge_output_hint.configure(
                text=f"Leave empty to save as {predicted.name} in {predicted.parent}")
        elif video:
            self.merge_output_hint.configure(text="Leave empty to save next to the video (e.g. Movie.zh-en.srt).")
        else:
            self.merge_output_hint.configure(text="Leave empty to save next to Track 1 (e.g. Movie.zh-en.srt).")

        bar = self._bars["merge"]
        if bar.busy:
            return
        if (s1 == "external" and not f1) or (s2 == "external" and not f2):
            bar.set_hint("Choose the subtitle file for each track set to “External file”.")
        elif not video and not f1 and not f2:
            bar.set_hint("Add two subtitle files or choose a video to begin.")
        else:
            target = Path(custom).name if custom else (predicted.name if predicted else "")
            bar.set_hint(f"Ready. Will save {target}." if target else "Ready to merge.")

    def _add_subtitle_files(self):
        """Pick one or two subtitle files; assign each to a track by detected language."""
        paths = self._ask_open("subtitle", "Choose subtitle files (you can select two)", SUBTITLE_TYPES,
                               multiple=True)
        if not paths:
            return
        paths = paths[:2]
        if len(paths) == 1:
            self._assign_subtitle(paths[0])
            return
        langs = [self._detect_file_language(Path(p)) for p in paths]
        cjk = {'Chinese', 'Japanese', 'Korean'}
        # Put the CJK file on Track 1 (top) when exactly one of them is CJK.
        if langs[1] in cjk and langs[0] not in cjk:
            paths.reverse()
        for slot, path in zip(("chinese", "english"), paths):
            getattr(self, f"{slot}_source_var").set("external")
            getattr(self, f"{slot}_file_var").set(path)
        self._update_chinese_source()
        self._update_english_source()
        self._bars["merge"].reset()

    def _assign_subtitle(self, path: str):
        lang = self._detect_file_language(Path(path))
        slot = "chinese" if lang in ('Chinese', 'Japanese', 'Korean') else "english"
        # Fill an empty external slot first so a second pick does not overwrite the first.
        other = "english" if slot == "chinese" else "chinese"
        if (getattr(self, f"{slot}_source_var").get() == "external" and getattr(self, f"{slot}_file_var").get()
                and not (getattr(self, f"{other}_source_var").get() == "external"
                         and getattr(self, f"{other}_file_var").get())):
            slot = other
        getattr(self, f"{slot}_file_var").set(path)
        getattr(self, f"{slot}_source_var").set("external")
        self._update_chinese_source()
        self._update_english_source()

    def _swap_merge_files(self):
        """Swap all settings between Track 1 and Track 2."""
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
            self.tracks_label.config(text="No video selected")
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
                self._invalid("merge", "Choose a video file first.")
            return
        if not Path(video_path).is_file():
            self.tracks_label.config(text="Video file not found.")
            if not quiet:
                self._invalid("merge", f"Video file not found: {video_path}")
            return

        self._missing = getattr(self, "_missing", {"ffmpeg": [], "mkvtoolnix": []})
        self._missing["ffmpeg"] = missing_tools("ffmpeg")
        ffmpeg_missing = bool(self._missing["ffmpeg"])
        self._refresh_tool_banners()
        self.tracks_label.config(text="Looking for subtitles…")
        self._set_status("Scanning video tracks...")
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
            lang = tr.language or 'Unknown'
            title = f" - {tr.title}" if tr.title else ""
            label = f"Track {tr.track_id}: {lang}{title} ({tr.codec})"
            labels.append(label)
            lang_lower = lang.lower()
            if any(c in lang_lower for c in ['chi', 'zh', 'cn', 'jpn', 'ja', 'kor', 'ko']):
                chinese_tracks.append(label)
            elif any(c in lang_lower for c in ['eng', 'en']):
                english_tracks.append(label)
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
            parts.append("Can't look inside the video: FFmpeg is not installed")
        elif error:
            parts.append(f"Couldn't read the video's tracks ({error})")
        elif tracks:
            parts.append(f"Found {len(tracks)} subtitle track(s) inside the video")
        else:
            parts.append("No subtitle tracks inside the video")
        if external:
            names = ", ".join(f.name for f in external[:3])
            more = f" (+{len(external) - 3} more)" if len(external) > 3 else ""
            parts.append(f"{len(external)} subtitle file(s) next to it: {names}{more}")
        self.tracks_label.config(text=" · ".join(parts))
        self._set_status(t('gui.status_ready'))
        self._update_merge_hint()

    def _preview_embedded_track(self, track_type: str):
        """Preview an embedded subtitle track by extracting it to a temp file."""
        video_path = self.merge_video_var.get().strip()
        if not video_path or not Path(video_path).exists():
            self._invalid("merge", "Choose a video file first.")
            return
        track_label = getattr(self, f"{track_type}_track_var").get()
        if not track_label:
            self._invalid("merge", "Choose a track first (click Scan Tracks).")
            return
        track_id = track_label.split(":")[0].replace("Track", "").strip()
        self._set_status(f"Extracting track {track_id} for preview...")

        def do_extract():
            try:
                import tempfile

                from core.video_containers import VideoContainerHandler
                handler = VideoContainerHandler()
                tracks = handler.list_subtitle_tracks(Path(video_path))
                track = next((tr for tr in tracks if str(tr.track_id) == track_id), None)
                if track is None:
                    raise RuntimeError(f"Track {track_id} was not found in the video")
                suffix = '.ass' if (track.codec or '').lower() in ('ass', 'ssa') else '.srt'
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                result = handler.extract_subtitle_track(Path(video_path), track, tmp_path)
                if result and Path(result).exists():
                    self._post(lambda: self._show_subtitle_preview(str(result)))
                else:
                    self._post(lambda: messagebox.showerror("Preview", "Couldn't extract that track.",
                                                            parent=self.root))
            except Exception as e:  # noqa: BLE001 - report any failure to the user
                self._post(lambda e=e: messagebox.showerror("Preview failed", str(e), parent=self.root))
            finally:
                self._post(lambda: self._set_status(t('gui.status_ready')))

        threading.Thread(target=do_extract, daemon=True).start()

    def _browse_merge_video(self):
        path = self._ask_open("video", "Select Video File", VIDEO_TYPES)
        if path:
            self.merge_video_var.set(path)

    def _browse_merge_output(self):
        fmt = self.merge_format_var.get() or "srt"
        types = [("SRT files", "*.srt"), ("ASS files", "*.ass"), ("All files", "*.*")]
        if fmt == "ass":
            types = [types[1], types[0], types[2]]
        path = self._ask_save("output", "Save merged subtitle as", types, f".{fmt}",
                              current=self.merge_output_var.get().strip())
        if path:
            self.merge_output_var.set(path)
            ext = Path(path).suffix.lower().lstrip(".")
            if ext in ("srt", "ass"):
                self.merge_format_var.set(ext)

    def _browse_sub_file(self, lang_type: str):
        """Browse for the Track 1 ('chinese') or Track 2 ('english') subtitle file."""
        title = "Select Track 1 (top) subtitle" if lang_type == 'chinese' else "Select Track 2 (bottom) subtitle"
        path = self._ask_open("subtitle", title, SUBTITLE_TYPES)
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

        def track_id(label: str) -> str | None:
            return label.split(":")[0].replace("Track", "").strip() if label else None

        paths: dict[str, Path | None] = {}
        tracks: dict[str, str | None] = {}
        for slot, name, source in (("chinese", "Track 1", chinese_source), ("english", "Track 2", english_source)):
            paths[slot] = None
            tracks[slot] = None
            if source == "external":
                p = getattr(self, f"{slot}_file_var").get().strip()
                if not p:
                    self._invalid(key, f"Choose a subtitle file for {name}, or switch it to Auto-detect.")
                    return
                if not Path(p).is_file():
                    self._invalid(key, f"{name} file not found: {p}")
                    return
                paths[slot] = Path(p)
            elif source == "embedded":
                if not video_path:
                    self._invalid(key, f"{name} uses an embedded track: choose a video file first.")
                    return
                tracks[slot] = track_id(getattr(self, f"{slot}_track_var").get())

        if chinese_source == "auto" and english_source == "auto" and not video_path:
            self._invalid(key, "Add two subtitle files or choose a video to begin.")
            return
        if video_path and not Path(video_path).is_file():
            self._invalid(key, f"Video file not found: {video_path}")
            return
        if (paths["chinese"] or paths["english"]) and not (paths["chinese"] and paths["english"]) and not video_path:
            self._invalid(key, "Only one subtitle file is set. Add the second file or choose a video.")
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
        options = {
            "auto_align": self.merge_autoalign_var.get(),
            "use_translation": self.merge_translation_var.get() and self._translation_key_available,
            "alignment_threshold": threshold,
            "enable_mixed_realignment": self.merge_autosync_var.get(),
            "top_language": self.merge_top_var.get(),
        }
        auto_langs = {"chinese": self.chinese_auto_lang_var.get() if chinese_source == "auto" else None,
                      "english": self.english_auto_lang_var.get() if english_source == "auto" else None}
        bar = self._bars[key]
        friendly = {"Finding Chinese subtitle": "Finding the Track 1 subtitle",
                    "Finding English subtitle": "Finding the Track 2 subtitle"}

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
                        "Bilingual Subtitle Detected",
                        f"'{p.name}' already contains two languages ({r:.0%} of lines).\n\n"
                        "Merging it may show some text twice. To only fix its timing, use "
                        "Convert → Sync instead.\n\nMerge anyway?", parent=self.root), cancel)
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

            logger.info(f"Starting merge operation for: {video_path or 'external files'}")
            merger = BilingualMerger(progress_callback=progress, **options)
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
            except MergeCancelled:
                return {"cancelled": True}
            return {"success": ok, "output": merger.last_output_path if ok else None}

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, "Merge failed", result)
            elif result.get("declined"):
                bar.finish("cancelled", "Merge cancelled.")
                self._set_status(t('gui.status_ready'))
            elif result.get("cancelled"):
                bar.finish("cancelled", "Merge cancelled. No file was written.")
                self._set_status("Merge cancelled")
            elif result.get("success"):
                out = result.get("output")
                name = out.name if out else "the merged subtitle"
                bar.finish("success", f"Saved {name}", actions=self._output_actions(out))
                self._set_status(f"✔ Saved {out or name}")
            else:
                self._fail(key, "Merge failed", None)

        self._run_task(key, "Merging: Starting…", work, done, cancellable=True, determinate=True,
                       status="Merging subtitles...")

    # ======================================================================
    # Extract tab
    # ======================================================================

    def _create_extract_tab(self):
        """Create the Extract Tracks tab (mkvextract)."""
        _tab, body = self._new_tab("extract", t('gui.tab_extract').strip())
        self._intro(body, 0, "Save the subtitle tracks stored inside a video (MKV works best) as separate files.")
        self.extract_banner = Banner(body, row=1, column=0, sticky="ew", pady=(0, PAD))

        file_frame = self._section(body, 2, "Video File")
        self.extract_file_var = tk.StringVar()
        self._path_row(file_frame, 0, self.extract_file_var, self._browse_extract_file,
                       extra=[("Load Tracks", self._load_extract_tracks)])

        tracks_frame = self._section(body, 3, "Subtitle Tracks")
        tracks_frame.rowconfigure(0, weight=1)
        columns = ('id', 'language', 'codec', 'name')
        self.extract_tree = ttk.Treeview(tracks_frame, columns=columns, show='headings', height=7,
                                         selectmode='extended')
        from tkinter import font as tkfont
        heading_font = tkfont.nametofont("TkHeadingFont")
        body_font = tkfont.nametofont("TkDefaultFont")
        for col, text, sample, anchor in (('id', 'ID', '000', 'center'), ('language', 'Language', 'zh-Hans', 'center'),
                                          ('codec', 'Codec', 'S_TEXT/UTF8', 'w'),
                                          ('name', 'Name', 'Simplified Chinese (Signs)', 'w')):
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
        ttk.Button(sel, text="Select All", command=self._extract_select_all).pack(side=tk.LEFT)
        ttk.Button(sel, text="Select None", command=self._extract_select_none).pack(side=tk.LEFT, padx=(PAD_S, 0))
        self.extract_tree.bind("<<TreeviewSelect>>", lambda e: self._update_extract_hint())

        output_frame = self._section(body, 4, "Output")
        self.extract_output_var = tk.StringVar()
        self._path_row(output_frame, 0, self.extract_output_var, self._browse_extract_output, label="Folder:")
        ttk.Label(output_frame, text="Leave empty to save next to the video.", style='Caption.TLabel').grid(
            row=1, column=0, sticky="w", pady=(PAD_S, 0))
        self.extract_ocr_var = tk.BooleanVar(value=self._pgs_available)
        if self._is_lite:
            ocr_text = "Convert PGS/image tracks to SRT after extraction (requires biss-full.exe)"
        elif not self._pgs_available:
            ocr_text = "Convert PGS/image tracks to SRT after extraction (install PGSRip first)"
        else:
            ocr_text = "Convert PGS/image tracks to SRT after extraction"
        self._extract_ocr_check = ttk.Checkbutton(output_frame, text=ocr_text, variable=self.extract_ocr_var,
                                                  state='normal' if self._pgs_available else 'disabled')
        self._extract_ocr_check.grid(row=2, column=0, sticky="w", pady=(PAD_S, 0))

        self._extract_hint = "Choose a video, then select the tracks to save."
        bar = self._add_action_bar("extract", "Extract Selected", self._execute_extract, self._extract_hint)
        self.extract_btn = bar.button
        self.extract_progress = bar.progressbar
        self.extract_progress_label = bar.message
        self._extract_tracks = []

    def _update_extract_hint(self):
        if getattr(self, "_missing", {}).get("mkvtoolnix"):
            return
        n = len(self.extract_tree.selection())
        total = len(self.extract_tree.get_children())
        if total:
            self._extract_hint = f"{n} of {total} track(s) selected."
        self._bars["extract"].set_hint(self._extract_hint)

    def _browse_extract_file(self):
        filename = self._ask_open("video", "Select Video File",
                                  [("Video files", "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"),
                                   ("MKV files", "*.mkv"), ("All files", "*.*")])
        if filename:
            self.extract_file_var.set(filename)
            self._load_extract_tracks()

    def _browse_extract_output(self):
        dirname = self._ask_dir("output", "Select Output Folder")
        if dirname:
            self.extract_output_var.set(dirname)

    def _check_mkvtoolnix_available(self) -> tuple:
        """(available, missing_tools) for MKVToolNix (PATH lookup, no subprocess)."""
        missing = missing_tools("mkvtoolnix")
        return (len(missing) == 0, missing)

    def _show_mkvtoolnix_missing_dialog(self):
        """Explain how to get MKVToolNix for this platform."""
        messagebox.showerror("MKVToolNix Not Found",
                             "MKVToolNix is required for the Extract Tracks feature.\n\n"
                             + install_hint("mkvtoolnix"), parent=self.root)

    def _mkvtoolnix_ready(self) -> bool:
        available, missing = self._check_mkvtoolnix_available()
        self._missing = getattr(self, "_missing", {"ffmpeg": [], "mkvtoolnix": []})
        self._missing["mkvtoolnix"] = missing
        self._refresh_tool_banners()
        if not available:
            self._bars["extract"].finish("error", "MKVToolNix is not installed – see the note at the top.")
            self._scrollers["extract"].scroll_to_top()
        return available

    def _load_extract_tracks(self):
        """Load tracks from an MKV file using mkvinfo (in the background)."""
        video_path = self.extract_file_var.get().strip()
        if not video_path:
            self._invalid("extract", "Choose a video file first.")
            return
        if not self._mkvtoolnix_ready():
            return
        if not Path(video_path).is_file():
            self._invalid("extract", f"Video file not found: {video_path}")
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
                    result = "mkvinfo timed out – the file may be very large or damaged"
                self._fail("extract", "Couldn't read the video's tracks", result)
                return
            subs = [tr for tr in result if tr['type'] == 'subtitles']
            self._extract_tracks = subs
            for tr in subs:
                self.extract_tree.insert('', 'end', values=(tr['id'], tr['language'], tr['codec'], tr['name']))
            self._extract_select_all()
            bar.finish("info" if subs else "warning",
                       f"Found {len(subs)} subtitle track(s). All are selected." if subs
                       else "This video has no subtitle tracks.")
            self._set_status(f"Loaded {len(subs)} subtitle tracks")

        self._run_task("extract", "Reading tracks…", work, done, status="Loading tracks...")

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
            self._invalid(key, "Choose a video file first.")
            return
        if not self._mkvtoolnix_ready():
            return
        selected = self.extract_tree.selection()
        if not selected:
            self._invalid(key, "Select at least one track (or click Select All).")
            return
        output_dir = self.extract_output_var.get().strip() or str(Path(video_path).parent)
        if not Path(output_dir).is_dir():
            self._invalid(key, f"Output folder not found: {output_dir}")
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
                    self._post(lambda n=out_path.name: self._bars[key].progress(f"Reading text from {n} (OCR)…"))
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
                self._fail(key, "Extraction failed", result)
            elif result.get("cancelled") and not result.get("outputs"):
                bar.finish("cancelled", "Extraction cancelled.")
            else:
                outputs = result["outputs"]
                failed_ocr = [r for r in result.get("ocr", []) if "failed" in r or "error" in r]
                text = f"Saved {len(outputs)} track(s) to {Path(output_dir).name or output_dir}"
                if failed_ocr:
                    text += f" – {len(failed_ocr)} OCR problem(s), see Details"
                bar.finish("warning" if failed_ocr else "success", text,
                           actions=self._output_actions(outputs[0] if outputs else Path(output_dir), preview=False))
                self._set_status(f"✔ Extracted {len(outputs)} track(s)")

        self._run_task(key, f"Extracting {len(extract_args)} track(s)…", work, done, cancellable=True,
                       status="Extracting tracks...")

    # ======================================================================
    # Split tab
    # ======================================================================

    def _create_split_tab(self):
        """Create the Split Bilingual Subtitles tab."""
        _tab, body = self._new_tab("split", t('gui.tab_split').strip())
        self._intro(body, 0, "Turn one bilingual subtitle file into two files, one per language.")

        file_frame = self._section(body, 1, "Bilingual Subtitle File")
        self.split_file_var = tk.StringVar()
        self.split_file_var.trace_add('write', lambda *a: self._on_split_file_changed())
        self._path_row(file_frame, 0, self.split_file_var, self._browse_split_file, preview=True)
        self.split_chip = InfoChip(file_frame)
        self.split_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))
        self.split_status_var = tk.StringVar(value="Select a bilingual subtitle file")

        options = self._section(body, 2, "Split Options")
        lang_row = ttk.Frame(options)
        lang_row.grid(row=0, column=0, sticky="w")
        ttk.Label(lang_row, text="Name the Chinese/Japanese/Korean file:").pack(side=tk.LEFT)
        self.split_lang1_var = tk.StringVar(value="zh")
        ttk.Combobox(lang_row, textvariable=self.split_lang1_var, width=6,
                     values=['zh', 'ja', 'ko', 'chi', 'jpn', 'kor']).pack(side=tk.LEFT, padx=(PAD_S, PAD_L + PAD))
        ttk.Label(lang_row, text="the other file:").pack(side=tk.LEFT)
        self.split_lang2_var = tk.StringVar(value="en")
        ttk.Combobox(lang_row, textvariable=self.split_lang2_var, width=6,
                     values=['en', 'eng', 'fr', 'de', 'es']).pack(side=tk.LEFT, padx=(PAD_S, 0))
        ttk.Label(options, text="These codes go into the file names, e.g. Movie.zh.ass and Movie.en.srt.",
                  style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(PAD_S, 0))

        fmt_row = ttk.Frame(options)
        fmt_row.grid(row=2, column=0, sticky="w", pady=(PAD, 0))
        ttk.Label(fmt_row, text="Chinese/Japanese/Korean file format:").pack(side=tk.LEFT)
        self.split_format_var = tk.StringVar(value=self.settings.get("split.format", "ass"))
        ttk.Radiobutton(fmt_row, text="ASS (recommended – includes a CJK font)",
                        variable=self.split_format_var, value="ass").pack(side=tk.LEFT, padx=(PAD, PAD))
        ttk.Radiobutton(fmt_row, text="SRT (plain text)",
                        variable=self.split_format_var, value="srt").pack(side=tk.LEFT)
        self.split_strip_var = tk.BooleanVar(value=bool(self.settings.get("split.strip", True)))
        ttk.Checkbutton(options, text="Remove formatting tags like <i> and <b>",
                        variable=self.split_strip_var).grid(row=3, column=0, sticky="w", pady=(PAD, 0))

        out_frame = self._section(body, 3, "Output")
        self.split_output_dir_var = tk.StringVar()
        self._path_row(out_frame, 0, self.split_output_dir_var, self._browse_split_output_dir, label="Folder:")
        ttk.Label(out_frame, text="Leave empty to save next to the original file.",
                  style="Caption.TLabel").grid(row=1, column=0, sticky="w", pady=(PAD_S, 0))

        bar = self._add_action_bar("split", "Split Subtitle", self._execute_split,
                                   "Choose a bilingual subtitle file to split.")
        self.split_btn = bar.button

    def _browse_split_file(self):
        file_path = self._ask_open("subtitle", "Select Bilingual Subtitle",
                                   [("Subtitle Files", "*.srt *.ass *.ssa *.vtt"), ("SRT Files", "*.srt"),
                                    ("ASS/SSA Files", "*.ass *.ssa"), ("All Files", "*.*")])
        if file_path:
            self.split_file_var.set(file_path)

    def _browse_split_output_dir(self):
        dir_path = self._ask_dir("output", "Select Output Folder")
        if dir_path:
            self.split_output_dir_var.set(dir_path)

    def _on_split_file_changed(self):
        """Show language/lines and whether the file looks bilingual (analysed off-thread)."""
        path = self.split_file_var.get().strip()

        def render(info):
            bar = self._bars["split"]
            if info is None:
                self.split_chip.clear()
                self.split_status_var.set("Select a bilingual subtitle file")
                bar.set_hint("Choose a bilingual subtitle file to split." if not path
                             else "File not found.")
                return
            if info.get("busy") or info.get("error"):
                self._render_chip(self.split_chip, info)
                return
            base = describe_subtitle(dict(info, language=None)).split(" · ", 1)[-1]
            if info.get("split_bilingual"):
                self.split_status_var.set("Bilingual content detected - ready to split")
                self.split_chip.show(f"Bilingual content detected · {base}", "ok")
                bar.set_hint("Ready to split.")
            else:
                self.split_status_var.set("Warning: File does not appear to be bilingual")
                self.split_chip.show(f"This file doesn't look bilingual · {base}", "warning")
                bar.set_hint("This file doesn't look bilingual; splitting may produce one empty file.", "warning")

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
            self._invalid(key, "Choose a subtitle file to split.")
            return
        input_path = Path(file_path)
        if not input_path.is_file():
            self._invalid(key, f"File not found: {file_path}")
            return
        output_dir = Path(self.split_output_dir_var.get().strip()) if self.split_output_dir_var.get().strip() else None
        if output_dir and not output_dir.is_dir():
            self._invalid(key, f"Output folder not found: {output_dir}")
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
                self._fail(key, "Split failed", result)
                return
            outputs = [p for p in result if p]
            if not outputs:
                bar.finish("warning", "No bilingual content found to split. Nothing was saved.")
                return
            names = " and ".join(p.name for p in outputs)
            bar.finish("success", f"Saved {names}", actions=self._output_actions(outputs[0]))
            self._set_status(f"✔ Split into {names}")

        self._run_task(key, "Splitting…", work, done, status="Splitting subtitle...")

    # ======================================================================
    # Shift tab
    # ======================================================================

    def _create_shift_tab(self):
        """Create the Shift Timing tab."""
        _tab, body = self._new_tab("shift", t('gui.tab_shift').strip())
        self._intro(body, 0, "Make subtitles appear earlier or later, by a fixed amount or so the first line "
                             "starts at a given time.")

        file_frame = self._section(body, 1, "Subtitle File")
        self.shift_file_var = tk.StringVar()
        self.shift_file_var.trace_add('write', lambda *a: self._on_shift_file_changed())
        self._path_row(file_frame, 0, self.shift_file_var, self._browse_shift_file, preview=True)
        self.shift_chip = InfoChip(file_frame)
        self.shift_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        options = self._section(body, 2, "Shift Options")
        self.shift_mode_var = tk.StringVar(value="offset")
        mode_frame = ttk.Frame(options)
        mode_frame.grid(row=0, column=0, sticky="w", pady=(0, PAD))
        ttk.Radiobutton(mode_frame, text="Shift by offset", variable=self.shift_mode_var,
                        value="offset", command=self._update_shift_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="Set first line to timestamp", variable=self.shift_mode_var,
                        value="first_line", command=self._update_shift_mode).pack(side=tk.LEFT, padx=(PAD_L + PAD, 0))

        self.offset_frame = ttk.Frame(options)
        ttk.Label(self.offset_frame, text="Offset:").grid(row=0, column=0, sticky="w")
        self.shift_offset_var = tk.StringVar(value="")
        self.shift_offset_entry = ttk.Entry(self.offset_frame, textvariable=self.shift_offset_var, width=12)
        self.shift_offset_entry.grid(row=0, column=1, sticky="w", padx=(PAD_S, PAD))
        quick_frame = ttk.Frame(self.offset_frame)
        quick_frame.grid(row=0, column=2, sticky="w")
        for offset in ["-5s", "-1s", "-0.5s", "+0.5s", "+1s", "+5s"]:
            ttk.Button(quick_frame, text=offset, width=5,
                       command=lambda o=offset: self._nudge_offset(o)).pack(side=tk.LEFT, padx=(0, 2))
        self.shift_offset_hint = ttk.Label(self.offset_frame, style="Caption.TLabel",
                                           text="Negative = earlier, positive = later. E.g. -2.5s, +1500ms")
        self.shift_offset_hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(PAD_S, 0))

        self.firstline_frame = ttk.Frame(options)
        ttk.Label(self.firstline_frame, text="Set first line to:").grid(row=0, column=0, sticky="w")
        self.shift_firstline_var = tk.StringVar(value="00:00:50,000")
        ttk.Entry(self.firstline_frame, textvariable=self.shift_firstline_var, width=14).grid(
            row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self.shift_firstline_hint = ttk.Label(self.firstline_frame, text="Format: HH:MM:SS,mmm",
                                              style='Caption.TLabel')
        self.shift_firstline_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S, 0))

        output = self._section(body, 3, "Output")
        self.shift_overwrite_var = tk.BooleanVar(value=bool(self.settings.get("shift.overwrite", False)))
        ttk.Radiobutton(output, text="Save as a new file", variable=self.shift_overwrite_var, value=False,
                        command=self._update_shift_output).grid(row=0, column=0, sticky="w")
        self.shift_output_var = tk.StringVar()
        self._shift_output_auto = ""
        self.shift_output_row, self.shift_output_entry = self._path_row(
            output, 1, self.shift_output_var, self._browse_shift_output, label="Save as:")
        self.shift_output_row.grid_configure(padx=(PAD_L + PAD, 0), pady=(PAD_S, PAD_S))
        ttk.Radiobutton(output, text="Overwrite the original file", variable=self.shift_overwrite_var,
                        value=True, command=self._update_shift_output).grid(row=2, column=0, sticky="w")
        self.shift_backup_var = tk.BooleanVar(value=bool(self.settings.get("shift.backup", True)))
        self.shift_backup_check = ttk.Checkbutton(output, text="Keep a backup of the original",
                                                  variable=self.shift_backup_var)
        self.shift_backup_check.grid(row=3, column=0, sticky="w", padx=(PAD_L + PAD, 0), pady=(PAD_S, 0))

        bar = self._add_action_bar("shift", "Apply Shift", self._execute_shift, "Choose a subtitle file.")
        self.shift_btn = bar.button
        for var in (self.shift_offset_var, self.shift_firstline_var, self.shift_output_var):
            var.trace_add('write', lambda *a: self._validate_shift())
        self._update_shift_mode()
        self._update_shift_output()

    def _nudge_offset(self, delta: str):
        """Quick buttons add to the current offset (-1s then -0.5s = -1.5s)."""
        try:
            current = parse_offset(self.shift_offset_var.get())
        except ValueError:
            current = 0
        self.shift_offset_var.set(format_offset(current + parse_offset(delta)))

    def _update_shift_mode(self):
        if self.shift_mode_var.get() == "offset":
            self.firstline_frame.grid_remove()
            self.offset_frame.grid(row=1, column=0, sticky="ew")
        else:
            self.offset_frame.grid_remove()
            self.firstline_frame.grid(row=1, column=0, sticky="ew")
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
        if self.shift_mode_var.get() == "offset":
            text = self.shift_offset_var.get()
            try:
                ms = parse_offset(text)
                direction = "later" if ms > 0 else "earlier"
                self.shift_offset_hint.configure(
                    text=f"Subtitles will appear {abs(ms) / 1000:g} s {direction}." if ms
                    else "Negative = earlier, positive = later. E.g. -2.5s, +1500ms",
                    style="Caption.TLabel")
                if ms == 0:
                    problem = "Enter an offset or use the quick buttons."
            except ValueError as e:
                if text.strip():
                    self.shift_offset_hint.configure(text=str(e), style="Error.TLabel")
                    problem = f"Offset: {e}"
                else:
                    self.shift_offset_hint.configure(
                        text="Negative = earlier, positive = later. E.g. -2.5s, +1500ms", style="Caption.TLabel")
                    problem = "Enter an offset or use the quick buttons."
        else:
            try:
                parse_timestamp(self.shift_firstline_var.get())
                self.shift_firstline_hint.configure(text="Format: HH:MM:SS,mmm", style="Caption.TLabel")
            except ValueError as e:
                self.shift_firstline_hint.configure(text=str(e), style="Error.TLabel")
                problem = str(e)
        if not path:
            problem = "Choose a subtitle file."
        elif not Path(path).is_file():
            problem = "File not found."
        elif not self.shift_overwrite_var.get() and not self.shift_output_var.get().strip():
            problem = "Enter a name for the new file, or choose Overwrite."
        bar = self._bars["shift"]
        if not bar.busy:
            bar.button.state(["disabled"] if problem else ["!disabled"])
            bar.set_hint(problem or "Ready to apply.")
        return problem

    def _on_convert_file_changed(self):
        """Convert tab file changed: analyse subtitles, suggest output names."""
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
                    self.detected_encoding_var.set(encoding_name(enc) if enc else "Could not detect encoding")
                    self.encoding_label.configure(style="Success.TLabel" if enc else "Error.TLabel")
            self._analyze_later("convert", path, render)
        else:
            self._analyze_later("convert", "", lambda info: None)
            self.convert_chip.clear()
            self.detected_encoding_var.set("Select a file")
            self.encoding_label.configure(style="TLabel")

    def _browse_shift_file(self):
        path = self._ask_open("subtitle", "Select Subtitle File", SUBTITLE_TYPES)
        if path:
            self.shift_file_var.set(path)

    def _browse_shift_output(self):
        current = self.shift_output_var.get().strip()
        ext = Path(current).suffix if current else ".srt"
        path = self._ask_save("output", "Save shifted subtitle as",
                              [("SRT files", "*.srt"), ("ASS files", "*.ass"), ("All files", "*.*")],
                              ext or ".srt", current=current)
        if path:
            self.shift_output_var.set(path)

    def _execute_shift(self):
        """Apply the timing shift (validated on the UI thread first)."""
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
        create_backup = self.shift_backup_var.get() if overwrite else False
        mode = self.shift_mode_var.get()
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
                self._fail(key, "Shift failed", result if not ok else None)
                return
            target = output_path or input_path
            how = (f"{abs(offset_ms) / 1000:g} s {'later' if offset_ms > 0 else 'earlier'}"
                   if mode == "offset" else f"first line at {timestamp}")
            note = " (backup kept)" if overwrite and create_backup else ""
            bar.finish("success", f"Saved {target.name}: {how}{note}", actions=self._output_actions(target))
            self._set_status(f"✔ Shifted {target}")

        self._run_task(key, "Shifting timing…", work, done, status="Shifting timing...")

    # ======================================================================
    # Convert tab
    # ======================================================================

    def _create_convert_tab(self):
        """Create the Convert tab (encoding, ASS->SRT, PGS OCR, sync to video)."""
        _tab, body = self._new_tab("convert", t('gui.tab_convert').strip())
        self._intro(body, 0, "Fix garbled characters, change the subtitle format, read image subtitles (OCR) "
                             "or line up a subtitle with a video.")

        type_frame = self._section(body, 1, "Conversion Type")
        self.convert_type_var = tk.StringVar(value="encoding")
        ttk.Radiobutton(type_frame, text="Encoding conversion (fix garbled characters)",
                        variable=self.convert_type_var, value="encoding",
                        command=self._update_convert_type).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(type_frame, text="ASS/SSA to SRT (convert format, preserve bilingual)",
                        variable=self.convert_type_var, value="ass_to_srt",
                        command=self._update_convert_type).grid(row=1, column=0, sticky="w", pady=(2, 0))
        if self._is_lite:
            pgs_label, pgs_state = "PGS/Image Subtitle to SRT (OCR) — requires biss-full.exe", 'disabled'
        elif not self._pgs_available:
            pgs_label, pgs_state = ("PGS/Image Subtitle to SRT (OCR) — install PGSRip: biss setup-pgsrip install",
                                    'disabled')
        else:
            pgs_label, pgs_state = "PGS/Image Subtitle to SRT (OCR)", 'normal'
        self._pgs_radio = ttk.Radiobutton(type_frame, text=pgs_label, variable=self.convert_type_var,
                                          value="pgs_ocr", command=self._update_convert_type, state=pgs_state)
        self._pgs_radio.grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Radiobutton(type_frame, text="Sync external subtitle to video (auto-detect timing offset)",
                        variable=self.convert_type_var, value="sync",
                        command=self._update_convert_type).grid(row=3, column=0, sticky="w", pady=(2, 0))

        self.convert_file_frame = self._section(body, 2, "Subtitle File")
        self.convert_file_var = tk.StringVar()
        self.convert_file_var.trace_add('write', lambda *a: self._on_convert_file_changed())
        self._path_row(self.convert_file_frame, 0, self.convert_file_var, self._browse_convert_file, preview=True)
        self.convert_chip = InfoChip(self.convert_file_frame)
        self.convert_chip.grid(row=1, column=0, sticky="ew", pady=(PAD_S, 0))

        # Options live in a fixed slot so switching modes never reorders the page.
        host = ttk.Frame(body)
        host.grid(row=3, column=0, sticky="ew")
        host.columnconfigure(0, weight=1)
        self.convert_options_host = host

        # Encoding
        self.encoding_options_frame = self._section(host, 0, "Encoding Options")
        detect_row = ttk.Frame(self.encoding_options_frame)
        detect_row.grid(row=0, column=0, sticky="w")
        ttk.Label(detect_row, text="Detected encoding:").pack(side=tk.LEFT)
        self.detected_encoding_var = tk.StringVar(value="Select a file")
        self.encoding_label = ttk.Label(detect_row, textvariable=self.detected_encoding_var, font="BissBold")
        self.encoding_label.pack(side=tk.LEFT, padx=(PAD_S, 0))
        enc_row = ttk.Frame(self.encoding_options_frame)
        enc_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        enc_row.columnconfigure(2, weight=1)
        ttk.Label(enc_row, text="Convert to:").grid(row=0, column=0, sticky="w")
        self.convert_encoding_var = tk.StringVar(value=self.settings.get("convert.encoding", "utf-8"))
        ttk.Combobox(enc_row, textvariable=self.convert_encoding_var, width=12,
                     values=['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'big5', 'shift-jis']).grid(
            row=0, column=1, sticky="w", padx=(PAD_S, PAD))
        self._caption(enc_row, "UTF-8 works in almost every player.").grid(row=0, column=2, sticky="ew")
        self.convert_backup_var = tk.BooleanVar(value=bool(self.settings.get("convert.backup", True)))
        ttk.Checkbutton(self.encoding_options_frame, text="Keep a backup of the original file",
                        variable=self.convert_backup_var).grid(row=2, column=0, sticky="w", pady=(PAD_S + 2, 0))
        self.convert_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.encoding_options_frame, text="Convert even if the file already uses this encoding",
                        variable=self.convert_force_var).grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.convert_fix_fonts_var = tk.BooleanVar(value=bool(self.settings.get("convert.fix_fonts", True)))
        ttk.Checkbutton(self.encoding_options_frame,
                        text="Fix missing fonts in ASS/SSA files (use fonts installed on this computer)",
                        variable=self.convert_fix_fonts_var).grid(row=4, column=0, sticky="w", pady=(2, 0))

        # ASS -> SRT
        self.ass_options_frame = self._section(host, 0, "ASS to SRT Options")
        self.ass_bilingual_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text="Keep both languages (CJK on top, English below)",
                        variable=self.ass_bilingual_var).grid(row=0, column=0, sticky="w")
        self.ass_strip_effects_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text="Remove ASS effects and styling",
                        variable=self.ass_strip_effects_var).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.ass_output_var = tk.StringVar()
        row, _ = self._path_row(self.ass_options_frame, 2, self.ass_output_var, self._browse_ass_output,
                                label="Save as:")
        row.grid_configure(pady=(PAD, 0))

        # PGS OCR
        self.pgs_options_frame = self._section(host, 0, "PGS OCR Options")
        pgs_track_row = ttk.Frame(self.pgs_options_frame)
        pgs_track_row.grid(row=0, column=0, sticky="ew")
        pgs_track_row.columnconfigure(1, weight=1)
        ttk.Label(pgs_track_row, text="PGS Track:").grid(row=0, column=0, sticky="w")
        self.pgs_track_var = tk.StringVar()
        self.pgs_track_combo = ttk.Combobox(pgs_track_row, textvariable=self.pgs_track_var, width=50,
                                            state='readonly')
        self.pgs_track_combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(pgs_track_row, text="Detect Tracks", command=self._detect_pgs_tracks).grid(
            row=0, column=2, padx=(PAD_S, 0))
        pgs_lang_row = ttk.Frame(self.pgs_options_frame)
        pgs_lang_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        pgs_lang_row.columnconfigure(2, weight=1)
        ttk.Label(pgs_lang_row, text="OCR Language:").grid(row=0, column=0, sticky="w")
        self.pgs_lang_var = tk.StringVar(value="auto")
        self.pgs_lang_combo = ttk.Combobox(pgs_lang_row, textvariable=self.pgs_lang_var, width=10,
                                           state='readonly', values=['auto', 'eng', 'chi_sim', 'chi_tra', 'jpn', 'kor'])
        self.pgs_lang_combo.grid(row=0, column=1, sticky="w", padx=(PAD_S, 0))
        self._caption(pgs_lang_row, "auto = use the track's language tag").grid(
            row=0, column=2, sticky="ew", padx=(PAD, 0))
        self.pgs_output_var = tk.StringVar()
        row, _ = self._path_row(self.pgs_options_frame, 2, self.pgs_output_var, self._browse_pgs_output,
                                label="Save as:")
        row.grid_configure(pady=(PAD, 0))
        self._pgs_detected_tracks = []

        # Sync
        self.sync_options_frame = self._section(host, 0, "Sync Options")
        self.sync_video_var = tk.StringVar()
        self._path_row(self.sync_options_frame, 0, self.sync_video_var, self._browse_sync_video, label="Video file:")
        sync_track_row = ttk.Frame(self.sync_options_frame)
        sync_track_row.grid(row=1, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        sync_track_row.columnconfigure(1, weight=1)
        ttk.Label(sync_track_row, text="Reference track:").grid(row=0, column=0, sticky="w")
        self.sync_track_var = tk.StringVar()
        self.sync_track_combo = ttk.Combobox(sync_track_row, textvariable=self.sync_track_var, width=50,
                                             state='readonly')
        self.sync_track_combo.grid(row=0, column=1, sticky="ew", padx=(PAD_S, 0))
        ttk.Button(sync_track_row, text="Load Tracks", command=self._load_sync_tracks).grid(
            row=0, column=2, padx=(PAD_S, 0))
        sync_btn_row = ttk.Frame(self.sync_options_frame)
        sync_btn_row.grid(row=2, column=0, sticky="ew", pady=(PAD_S + 2, 0))
        sync_btn_row.columnconfigure(1, weight=1)
        ttk.Button(sync_btn_row, text="Detect Offset", command=self._detect_sync_offset).grid(
            row=0, column=0, sticky="nw")
        self.sync_result_var = tk.StringVar(value="Detect Offset only measures; Sync Subtitle also fixes the file "
                                                  "(a backup is kept).")
        self._caption(sync_btn_row, textvariable=self.sync_result_var).grid(
            row=0, column=1, sticky="ew", padx=(PAD, 0))
        self._sync_tracks_data = []

        bar = self._add_action_bar("convert", "Convert Encoding", self._execute_convert,
                                   "Choose a subtitle file to convert.")
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
            "encoding": ("Convert Encoding", self._execute_convert, "Subtitle File",
                         "Choose a subtitle file to convert."),
            "ass_to_srt": ("Convert ASS to SRT", self._execute_ass_convert, "ASS/SSA File",
                           "Choose an .ass or .ssa file."),
            "pgs_ocr": ("Convert PGS to SRT", self._execute_pgs_convert, "Video or SUP File",
                        "Choose a video or .sup file, then pick the track."),
            "sync": ("Sync Subtitle", self._execute_sync, "Subtitle File (to fix)",
                     "Choose the subtitle to fix and the video to match."),
        }
        text, command, file_title, hint = labels.get(conv_type, labels["encoding"])
        self.convert_btn.config(text=text, command=command)
        self.convert_file_frame.configure(text=file_title)
        if "convert" in self._bars:
            self._bars["convert"].set_hint(hint)

    def _browse_ass_output(self):
        path = self._ask_save("output", "Save SRT file as", [("SRT files", "*.srt"), ("All files", "*.*")],
                              ".srt", current=self.ass_output_var.get().strip())
        if path:
            self.ass_output_var.set(path)

    def _execute_ass_convert(self):
        """Execute ASS to SRT conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        input_path = self.convert_file_var.get().strip()
        output_path = self.ass_output_var.get().strip()
        if not input_path:
            self._invalid(key, "Choose an ASS/SSA file to convert.")
            return
        if not Path(input_path).is_file():
            self._invalid(key, f"File not found: {input_path}")
            return
        if not input_path.lower().endswith(('.ass', '.ssa')):
            self._invalid(key, "The selected file is not an ASS/SSA file.")
            return
        output_path = output_path or str(Path(input_path).with_suffix('.srt'))
        strip_effects = self.ass_strip_effects_var.get()
        bilingual = self.ass_bilingual_var.get()

        def work(cancel):
            from core.ass_converter import ASSToSRTConverter
            converter = ASSToSRTConverter(strip_effects=strip_effects, preserve_bilingual=bilingual)
            return converter.convert_file(Path(input_path), Path(output_path))

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, "Conversion failed", result)
                return
            out = Path(result) if result else Path(output_path)
            self._bars[key].finish("success", f"Saved {out.name}", actions=self._output_actions(out))
            self._set_status(f"✔ Saved {out.name}")

        self._run_task(key, "Converting ASS to SRT…", work, done)

    def _browse_pgs_output(self):
        path = self._ask_save("output", "Save SRT file as", [("SRT files", "*.srt"), ("All files", "*.*")],
                              ".srt", current=self.pgs_output_var.get().strip())
        if path:
            self.pgs_output_var.set(path)

    def _detect_pgs_tracks(self):
        """Detect PGS tracks in the selected file."""
        key = "convert"
        if not self._pgsrip_wrapper:
            self._invalid(key, "PGSRip is not available.")
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, "Choose a video or SUP file first.")
            return
        input_file = Path(input_path)
        if not input_file.is_file():
            self._invalid(key, f"File not found: {input_path}")
            return
        if input_file.suffix.lower() in ('.sup', '.idx', '.sub'):
            label = f"Standalone file: {input_file.name}"
            self.pgs_track_combo['values'] = [label]
            self.pgs_track_var.set(label)
            self._pgs_detected_tracks = []
            if not self.pgs_output_var.get():
                self.pgs_output_var.set(str(input_file.with_suffix('.srt')))
            return
        self._set_status("Detecting PGS tracks...")

        def do_detect():
            try:
                tracks = self._pgsrip_wrapper.detect_pgs_tracks(input_file)
                error = None
            except Exception as e:  # noqa: BLE001 - report any failure to the user
                tracks, error = [], e

            def update_ui():
                self._set_status(t('gui.status_ready'))
                if error:
                    self._fail(key, "Track detection failed", error)
                    return
                self._pgs_detected_tracks = tracks
                if tracks:
                    labels = []
                    for tr in tracks:
                        title = f" - {tr.title}" if tr.title else ""
                        labels.append(f"Track {tr.track_id}: {tr.language or 'unknown'}{title} "
                                      f"(OCR: {tr.estimated_language})")
                    self.pgs_track_combo['values'] = labels
                    self.pgs_track_var.set(labels[0])
                    if not self.pgs_output_var.get():
                        self.pgs_output_var.set(str(input_file.with_suffix('.pgs.srt')))
                else:
                    self.pgs_track_combo['values'] = ['No PGS tracks found']
                    self.pgs_track_var.set('No PGS tracks found')

            self._post(update_ui)

        threading.Thread(target=do_detect, daemon=True).start()

    def _execute_pgs_convert(self):
        """Execute PGS to SRT OCR conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        if not self._pgsrip_wrapper:
            self._invalid(key, "PGSRip is not available.")
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, "Choose a video or SUP file.")
            return
        input_file = Path(input_path)
        if not input_file.is_file():
            self._invalid(key, f"File not found: {input_path}")
            return
        output_file = Path(self.pgs_output_var.get().strip() or str(input_file.with_suffix('.pgs.srt')))
        ocr_lang = None if self.pgs_lang_var.get() == 'auto' else self.pgs_lang_var.get()
        standalone = input_file.suffix.lower() in ('.sup', '.idx', '.sub')
        track = None
        if not standalone:
            if not self._pgs_detected_tracks:
                self._invalid(key, "No PGS tracks detected yet. Click Detect Tracks first.")
                return
            values = list(self.pgs_track_combo['values'] or [])
            idx = values.index(self.pgs_track_var.get()) if self.pgs_track_var.get() in values else 0
            track = self._pgs_detected_tracks[idx if idx < len(self._pgs_detected_tracks) else 0]

        def work(cancel):
            if standalone:
                return self._pgsrip_wrapper.convert_subtitle_file(input_file, output_file, ocr_lang or 'eng')
            return self._pgsrip_wrapper.convert_pgs_track(input_file, track, output_file, ocr_lang)

        def done(ok, result, cancelled):
            if not ok or not result:
                self._fail(key, "PGS conversion failed", result if not ok else None)
                return
            self._bars[key].finish("success", f"Saved {output_file.name}", actions=self._output_actions(output_file))
            self._set_status(f"✔ Saved {output_file.name}")

        self._run_task(key, "Reading text from images (OCR) – this can take a few minutes…", work, done,
                       status="Converting PGS to SRT (OCR)...")

    def _browse_convert_file(self):
        """Browse for file to convert (subtitle, video, or SUP depending on mode)."""
        mode = self.convert_type_var.get()
        if mode == 'pgs_ocr':
            filetypes = [("Video & SUP files", "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.sup"),
                         ("SUP files", "*.sup"), ("Video files", "*.mkv *.mp4 *.m4v *.mov *.avi *.ts *.webm"),
                         ("VobSub files", "*.idx *.sub"), ("All files", "*.*")]
            title, kind = "Select Video or Subtitle File", "video"
        elif mode == 'sync':
            filetypes = [("SRT files", "*.srt"), ("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
            title, kind = "Select External Subtitle File", "subtitle"
        elif mode == 'ass_to_srt':
            filetypes = [("ASS/SSA files", "*.ass *.ssa"), ("All files", "*.*")]
            title, kind = "Select ASS/SSA File", "subtitle"
        else:
            filetypes, title, kind = SUBTITLE_TYPES, "Select Subtitle File", "subtitle"
        path = self._ask_open(kind, title, filetypes)
        if path:
            self.convert_file_var.set(path)

    def _browse_sync_video(self):
        path = self._ask_open("video", "Select Video File", VIDEO_TYPES)
        if path:
            self.sync_video_var.set(path)
            self._load_sync_tracks()

    def _load_sync_tracks(self):
        """Load subtitle tracks from video for sync track selection."""
        video_path = self.sync_video_var.get().strip()
        if not video_path or not Path(video_path).is_file():
            self._invalid("convert", "Choose a valid video file first.")
            return
        if missing_tools("ffmpeg"):
            self._invalid("convert", "Syncing to a video needs FFmpeg, which was not found. "
                          + install_hint("ffmpeg"))
            return
        self.sync_result_var.set("Loading tracks…")

        def do_load():
            try:
                from processors.subtitle_sync import SubtitleSync
                tracks = SubtitleSync().list_subtitle_tracks(Path(video_path))
                text_tracks = [tr for tr in tracks if tr['is_text']]
                labels = ["(auto-detect)"] + [
                    f"s:{tr['rel_index']} {tr['lang']} {tr['title']} ({tr['codec']})".strip() for tr in text_tracks]

                def apply():
                    self._sync_tracks_data = text_tracks
                    self._update_sync_track_combo(labels)
                    self.sync_result_var.set(f"{len(text_tracks)} text track(s) found.")
                self._post(apply)
            except Exception as e:  # noqa: BLE001 - report any failure to the user
                self._post(lambda e=e: self.sync_result_var.set(f"Couldn't load tracks: {e}"))

        threading.Thread(target=do_load, daemon=True).start()

    def _update_sync_track_combo(self, labels):
        self.sync_track_combo['values'] = labels
        if labels:
            self.sync_track_combo.current(0)

    def _sync_inputs(self):
        sub_path = self.convert_file_var.get().strip()
        video_path = self.sync_video_var.get().strip()
        if not sub_path or not Path(sub_path).is_file():
            self._invalid("convert", "Choose the subtitle file to fix.")
            return None
        if not video_path or not Path(video_path).is_file():
            self._invalid("convert", "Choose the video file to match.")
            return None
        if missing_tools("ffmpeg"):
            self._invalid("convert", "Syncing to a video needs FFmpeg, which was not found. "
                          + install_hint("ffmpeg"))
            return None
        track_index = None
        selection = self.sync_track_var.get()
        if selection and not selection.startswith("(auto"):
            try:
                track_index = int(selection.split()[0].split(':')[1])
            except (ValueError, IndexError):
                pass
        return Path(sub_path), Path(video_path), track_index

    def _detect_sync_offset(self):
        """Measure the timing offset without changing the file."""
        key = "convert"
        if self._bars[key].busy:
            return
        inputs = self._sync_inputs()
        if not inputs:
            return
        sub_path, video_path, track_index = inputs
        self.sync_result_var.set("Detecting…")

        def work(cancel):
            from processors.subtitle_sync import SubtitleSync
            return SubtitleSync().sync_file(video_path=video_path, srt_path=sub_path,
                                            track_index=track_index, dry_run=True)

        def done(ok, result, cancelled):
            bar = self._bars[key]
            if not ok:
                self.sync_result_var.set(f"Error: {result}")
                self._fail(key, "Offset detection failed", result, dialog=False)
            elif result.success:
                msg = (f"Offset: {result.offset_ms:+d}ms | Matches: {result.match_count}/{result.total_compared} | "
                       f"Track: {result.track_used}")
                self.sync_result_var.set(msg)
                bar.finish("info", f"The subtitle is off by {result.offset_ms / 1000:+.2f} s. "
                                   "Click Sync Subtitle to fix it.")
            else:
                self.sync_result_var.set(f"Failed: {result.message}")
                self._fail(key, "Offset detection failed", result.message, dialog=False)

        self._run_task(key, "Comparing with the video…", work, done, status="Detecting offset...")

    def _execute_sync(self):
        """Detect the offset and apply it (a backup is kept)."""
        key = "convert"
        if self._bars[key].busy:
            return
        inputs = self._sync_inputs()
        if not inputs:
            return
        sub_path, video_path, track_index = inputs

        def work(cancel):
            from processors.subtitle_sync import SubtitleSync
            return SubtitleSync().sync_file(video_path=video_path, srt_path=sub_path, track_index=track_index,
                                            backup=True, dry_run=False)

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, "Sync failed", result)
            elif result.success:
                self.sync_result_var.set(f"Applied: {result.shift_applied_ms:+d}ms "
                                         f"(matches {result.match_count}/{result.total_compared})")
                self._bars[key].finish("success", f"Synced {sub_path.name}: moved {result.shift_applied_ms / 1000:+.2f} s "
                                                  "(backup kept)", actions=self._output_actions(sub_path))
                self._set_status(f"✔ Synced {sub_path.name}")
            else:
                self.sync_result_var.set(f"Failed: {result.message}")
                self._fail(key, "Sync failed", result.message)

        self._run_task(key, "Syncing subtitle…", work, done, status="Syncing subtitle...")

    def _execute_convert(self):
        """Execute the encoding conversion."""
        key = "convert"
        if self._bars[key].busy:
            return
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            self._invalid(key, "Choose a subtitle file to convert.")
            return
        if not Path(input_path).is_file():
            self._invalid(key, f"File not found: {input_path}")
            return
        encoding = self.convert_encoding_var.get().strip() or "utf-8"
        try:
            import codecs
            codecs.lookup(encoding)
        except LookupError:
            self._invalid(key, f"Unknown encoding: {encoding}")
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
                self._fail(key, "Conversion failed", result)
                return
            name = Path(input_path).name
            if result.modified:
                text = f"Converted {name} to {encoding_name(encoding)}"
                if result.fonts_fixed:
                    text += f", replaced {len(result.fonts_fixed)} missing font(s)"
                    for style_name, old_font, new_font in result.fonts_fixed:
                        logger.info(f"  [{style_name}] '{old_font}' -> '{new_font}'")
                if create_backup:
                    text += " (backup kept)"
                bar.finish("success", text, actions=self._output_actions(Path(input_path)))
                self._set_status(f"✔ Converted {name}")
                self._file_info.pop(input_path, None)
                self._on_convert_file_changed()
            else:
                bar.finish("info", f"No change needed: {name} already uses {encoding_name(encoding)}.")
                self._set_status("No conversion needed")

        self._run_task(key, "Converting encoding…", work, done, status="Converting encoding...")

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
        self._intro(body, 0, "Process a whole folder at once.")

        op_frame = self._section(body, 1, "Operation Type")
        self.batch_op_var = tk.StringVar(value=self.settings.get("batch.op", "convert"))
        ttk.Radiobutton(op_frame, text="Convert encoding (all subtitles to UTF-8)",
                        variable=self.batch_op_var, value="convert",
                        command=self._update_batch_options).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(op_frame, text="Merge from videos (extract and create bilingual)",
                        variable=self.batch_op_var, value="merge",
                        command=self._update_batch_options).grid(row=1, column=0, sticky="w", pady=(2, 0))

        dir_frame = self._section(body, 2, "Folder")
        self.batch_dir_var = tk.StringVar()
        self._path_row(dir_frame, 0, self.batch_dir_var, self._browse_batch_dir)
        self.batch_recursive_var = tk.BooleanVar(value=bool(self.settings.get("batch.recursive", True)))
        ttk.Checkbutton(dir_frame, text="Include subfolders",
                        variable=self.batch_recursive_var).grid(row=1, column=0, sticky="w", pady=(PAD_S + 2, 0))

        options = self._section(body, 3, "Options")
        self.batch_backup_var = tk.BooleanVar(value=bool(self.settings.get("batch.backup", True)))
        self.batch_backup_check = ttk.Checkbutton(options, text="Keep backups of converted files",
                                                  variable=self.batch_backup_var)
        self.batch_backup_check.grid(row=0, column=0, sticky="w")
        self.batch_autoconfirm_var = tk.BooleanVar(value=bool(self.settings.get("batch.autoconfirm", False)))
        self.batch_autoconfirm_check = ttk.Checkbutton(
            options, text="Don't ask before each file (auto-confirm)", variable=self.batch_autoconfirm_var)
        self.batch_autoconfirm_check.grid(row=1, column=0, sticky="w", pady=(2, 0))

        results = self._section(body, 4, "Results")
        results.rowconfigure(1, weight=1)
        self.batch_progress_var = tk.StringVar(value="Nothing processed yet.")
        ttk.Label(results, textvariable=self.batch_progress_var).grid(row=0, column=0, sticky="w")
        self.batch_results = tk.Listbox(results, height=5, activestyle="none", relief="flat",
                                        highlightthickness=1, font="BissBody")
        self.batch_results.grid(row=1, column=0, sticky="nsew", pady=(PAD_S, 0))
        self.batch_progress_bar = None  # the action bar shows progress now

        bar = self._add_action_bar("batch", "Start Batch Processing", self._execute_batch,
                                   "Choose a folder to process.")
        self.batch_btn = bar.button
        self.batch_progress_bar = bar.progressbar
        self._update_batch_options()

    def _update_batch_options(self):
        merge = self.batch_op_var.get() == "merge"
        self.batch_backup_check.state(["disabled"] if merge else ["!disabled"])
        self.batch_autoconfirm_check.configure(
            text="Don't ask before each video (auto-confirm)" if merge
            else "Don't ask for confirmation before converting")

    def _browse_batch_dir(self):
        path = self._ask_dir("folder", "Select Folder")
        if path:
            self.batch_dir_var.set(path)
            self._bars["batch"].set_hint("Ready. Click Start to process the folder.")

    def _execute_batch(self):
        """Run a batch operation with per-file progress, results and Cancel."""
        key = "batch"
        if self._bars[key].busy:
            return
        directory = self.batch_dir_var.get().strip()
        if not directory:
            self._invalid(key, "Choose a folder first.")
            return
        if not Path(directory).is_dir():
            self._invalid(key, f"Folder not found: {directory}")
            return
        operation = self.batch_op_var.get()
        if operation == "merge" and missing_tools("ffmpeg") and not messagebox.askyesno(
                "FFmpeg not found",
                "FFmpeg was not found, so subtitles inside the videos can't be read. Only subtitle files "
                "saved next to each video (e.g. Movie.zh.srt and Movie.en.srt) will be used.\n\n"
                "Continue anyway?", icon="warning", parent=self.root):
            self._bars[key].finish("warning", install_hint("ffmpeg"),
                                   actions=[("Download page", lambda: self._open_download_page("ffmpeg"))])
            return
        recursive = self.batch_recursive_var.get()
        create_backup = self.batch_backup_var.get()
        auto_confirm = self.batch_autoconfirm_var.get()
        bar = self._bars[key]
        self.batch_results.delete(0, tk.END)

        def add_result(line: str):
            self._post(lambda: (self.batch_results.insert(tk.END, line), self.batch_results.see(tk.END)))

        def work(cancel):
            from processors.batch_processor import BatchProcessor
            from utils.file_operations import FileHandler
            processor = BatchProcessor(auto_confirm=auto_confirm)

            if operation == "convert":
                files = FileHandler.find_subtitle_files(Path(directory), recursive)
                if not files:
                    return {"empty": "No subtitle files found in this folder."}
                if not auto_confirm:
                    note = " Originals are kept as backups." if create_backup else ""
                    if not self._call_in_main(lambda: messagebox.askyesno(
                            "Confirm", f"Convert {len(files)} subtitle file(s) to UTF-8?{note}",
                            parent=self.root), cancel):
                        return {"declined": True}

                def progress(done_n, total, path):
                    self._post(lambda: (bar.progress(f"{done_n} of {total} – {path.name}", done_n, total),
                                        self.batch_progress_var.set(f"Converting… {done_n} of {total}")))

                results = processor.process_subtitles_batch(subtitle_paths=files, operation="convert",
                                                            parallel=False, progress_callback=progress,
                                                            cancel_event=cancel, keep_backup=create_backup)
                for f in results.get("processed_files", []):
                    add_result(f"✔ {Path(f).name}")
                for err in results.get("errors", []):
                    add_result(f"✖ {err}")
                return {"op": "convert", "results": results}

            videos = FileHandler.find_video_files(Path(directory), recursive)
            if not videos:
                return {"empty": "No video files found in this folder."}

            def confirm(video, index, total):
                answer = self._call_in_main(lambda: messagebox.askyesnocancel(
                    "Process video?", f"File {index} of {total}:\n{video.name}\n\n"
                    "Yes = merge this video, No = skip it, Cancel = stop the batch.", parent=self.root), cancel)
                return 'y' if answer else ('n' if answer is False else 'q')

            def progress(index, total, video):
                if video is not None:
                    self._post(lambda: (bar.progress(f"{index + 1} of {total} – {video.name}", index, total),
                                        self.batch_progress_var.set(f"Merging… {index + 1} of {total}")))

            results = processor.process_directory_interactive(
                directory=Path(directory), pattern="*", recursive=recursive, video_only=True,
                confirm_callback=None if auto_confirm else confirm, progress_callback=progress,
                cancel_event=cancel)
            for f in results.get("processed_files", []):
                add_result(f"✔ {Path(f).name}")
            for err in results.get("errors", []):
                add_result(f"✖ {err}")
            return {"op": "merge", "results": results}

        def done(ok, result, cancelled):
            if not ok:
                self._fail(key, "Batch operation failed", result)
                self.batch_progress_var.set("Failed.")
                return
            if result.get("empty"):
                bar.finish("warning", result["empty"])
                self.batch_progress_var.set(result["empty"])
                return
            if result.get("declined"):
                bar.finish("cancelled", "Nothing was changed.")
                self.batch_progress_var.set("Cancelled.")
                return
            summarize = summarize_batch_convert if result["op"] == "convert" else summarize_batch_merge
            all_ok, text = summarize(result["results"])
            self.batch_progress_var.set(text[0].upper() + text[1:] + ".")
            bar.finish("success" if all_ok else "warning", text[0].upper() + text[1:],
                       actions=[("Open folder", lambda: self._reveal(Path(directory)))]
                       + ([] if all_ok else [("Show details", lambda: self._toggle_details(True))]))
            self._set_status("✔ Batch finished" if all_ok else "⚠ Batch finished with problems")

        self._run_task(key, "Starting…", work, done, cancellable=True, determinate=True,
                       status="Running batch operation...")

    # ======================================================================
    # Menu actions
    # ======================================================================

    def _open_subtitle(self):
        """File > Open Subtitle: put the file on the right Merge track by language."""
        path = self._ask_open("subtitle", "Open Subtitle File", SUBTITLE_TYPES)
        if path:
            self._assign_subtitle(path)
            self._select_tab("merge")

    def _open_video(self):
        path = self._ask_open("video", "Open Video File", VIDEO_TYPES)
        if path:
            self.merge_video_var.set(path)
            self._select_tab("merge")

    # ======================================================================
    # Utility methods
    # ======================================================================

    def _set_status(self, message: str):
        self.status_var.set(message)

    def _clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def _copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", tk.END))
        self._set_status("Log copied to the clipboard")

    def _show_help(self):
        help_text = """MERGE SUBTITLES (main feature)
1. Click "Add subtitle files…" and select both files
   (or choose a video that has subtitles inside).
2. Check which track goes on top; use Swap Tracks if needed.
3. Click "Merge Subtitles" (or press Ctrl+Enter).
4. Click "Open folder" to find the result, e.g. Movie.zh-en.srt.

SHIFT TIMING
- Subtitles too early or late? Enter an offset (e.g. -2.5s)
  or use the quick buttons, then Apply. A new file is saved
  unless you choose to overwrite the original.

CONVERT
- Garbled characters: Encoding conversion (to UTF-8).
- ASS → SRT, image subtitles (OCR), or Sync to a video.

TIPS
- Video features need FFmpeg; Extract needs MKVToolNix.
- View → Show Details shows the full log."""
        messagebox.showinfo("Quick Guide", help_text, parent=self.root)

    def _show_shortcuts(self):
        shortcuts = """Ctrl+Enter      Run the current tab's main action
Ctrl+1 … Ctrl+6  Go to a tab
Ctrl+Tab        Next tab
Ctrl+O          Open subtitle file
Ctrl+P          Preview subtitle file
Ctrl+L          Show or hide Details (log)
F1              Quick Guide
Esc             Close preview windows
Alt+F4          Exit"""
        messagebox.showinfo("Keyboard Shortcuts", shortcuts, parent=self.root)

    def _show_about(self):
        about_text = f"""{APP_NAME}
Version {APP_VERSION}

Create bilingual subtitles: merge, split, shift, convert
and batch-process SRT, ASS and VTT files.

Settings are stored in:
{self.settings.path}"""
        messagebox.showinfo("About", about_text, parent=self.root)

    def _show_subtitle_preview(self, file_path: str | None = None):
        """Show a preview window (the file is parsed off the UI thread)."""
        if not file_path:
            file_path = self._ask_open("subtitle", "Select Subtitle to Preview", SUBTITLE_TYPES)
        if not file_path:
            return
        if not Path(file_path).is_file():
            messagebox.showerror("Preview", f"File not found:\n{file_path}", parent=self.root)
            return
        self._set_status(f"Opening {Path(file_path).name}…")

        def work():
            try:
                from core.encoding_detection import EncodingDetector
                from core.subtitle_formats import SubtitleFormatFactory
                encoding = EncodingDetector.detect_encoding(Path(file_path)) or "Unknown"
                sub_file = SubtitleFormatFactory.parse_file(Path(file_path))
                self._post(lambda: self._open_preview_window(file_path, sub_file, encoding))
            except Exception as e:  # noqa: BLE001 - report any failure to the user
                self._post(lambda e=e: messagebox.showerror("Preview Error", f"Could not preview file:\n{e}",
                                                            parent=self.root))
            finally:
                self._post(lambda: self._set_status(t('gui.status_ready')))

        threading.Thread(target=work, daemon=True).start()

    def _open_preview_window(self, file_path: str, sub_file, encoding: str):
        win = tk.Toplevel(self.root)
        win.title(f"Preview: {Path(file_path).name}")
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
        ttk.Label(info, text=f"{len(sub_file.events)} lines · {encoding_name(encoding)} · "
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
            lines.append(f"... ({len(sub_file.events) - max_events} more lines not shown)")
        text.insert(tk.END, "\n".join(lines))
        text.config(state='disabled')

        buttons = ttk.Frame(win, padding=PAD_L)
        buttons.grid(row=2, column=0, sticky="e")
        ttk.Button(buttons, text="Open folder", command=lambda: self._reveal(Path(file_path))).pack(
            side=tk.LEFT, padx=(0, PAD))
        close = ttk.Button(buttons, text="Close", command=win.destroy, default="active")
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
            if not messagebox.askyesno(
                    "A job is still running",
                    f"A {names} job is still running. Quit anyway?\n\n"
                    "The job will be stopped and the file it is writing may be incomplete.",
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
