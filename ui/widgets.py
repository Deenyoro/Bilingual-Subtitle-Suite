"""
Reusable Tkinter/ttk building blocks for the BISS GUI.

- setup_theme(): native theme, named fonts and the small style palette
- ScrollableFrame: vertically scrolling tab body (the action bar never scrolls)
- ActionBar: fixed bottom bar with progress, result, Cancel and the primary button
- Banner: dismissible inline notice (missing FFmpeg, etc.)
- Collapsible: "Advanced options" style disclosure section
- InfoChip: one-line file facts under a path field
"""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import font as tkfont
from tkinter import ttk
from typing import ClassVar

# Windows 11 accent colours, used sparingly.
ACCENT = "#0067C0"
ACCENT_ACTIVE = "#1975C5"
ACCENT_PRESSED = "#005BA8"
SUCCESS = "#0F7B0F"
ERROR = "#C42B1C"
WARNING = "#9D5D00"
MUTED = "#5F5F5F"

# 8 px spacing grid (logical pixels, scaled by Tk for DPI when given as "Np").
PAD = 8
PAD_S = 4
PAD_L = 12


def _scaled(root: tk.Misc, px: float) -> int:
    """Logical 96-dpi pixels -> physical pixels for the current Tk scaling."""
    return round(px * float(root.winfo_fpixels("1i")) / 96.0)


def setup_theme(root: tk.Tk) -> dict:
    """Apply the native theme, named fonts and BISS styles. Returns palette info."""
    style = ttk.Style(root)
    themes = style.theme_names()
    if sys.platform == "win32" and "vista" in themes:
        theme = "vista"
    elif sys.platform == "darwin" and "aqua" in themes:
        theme = "aqua"
    else:
        theme = "clam" if "clam" in themes else style.theme_use()
    style.theme_use(theme)

    # ---- named fonts -------------------------------------------------------
    default = tkfont.nametofont("TkDefaultFont")
    if sys.platform == "win32":
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkTooltipFont", "TkIconFont", "TkSmallCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=9)
            except tk.TclError:
                pass
    family = default.actual("family")
    size = abs(int(default.actual("size"))) or 9

    def named(name, **kw):
        try:
            f = tkfont.nametofont(name)
            f.configure(**kw)
        except tk.TclError:
            f = tkfont.Font(root=root, name=name, exists=False, **kw)
        return f

    semibold = "Segoe UI Semibold" if sys.platform == "win32" else family
    weight = "normal" if sys.platform == "win32" else "bold"
    named("BissBody", family=family, size=size)
    named("BissBold", family=family, size=size, weight="bold")
    named("BissHeading", family=semibold, size=size + 1, weight=weight)
    named("BissTitle", family=semibold, size=size + 4, weight=weight)
    named("BissCaption", family=family, size=size)
    mono = "Consolas" if sys.platform == "win32" else tkfont.nametofont("TkFixedFont").actual("family")
    named("BissMono", family=mono, size=size)

    # ---- palette -----------------------------------------------------------
    native = theme in ("vista", "xpnative", "winnative", "aqua")
    if not native:
        bg = "#F3F3F3"
        field = "#FFFFFF"
        style.configure(".", background=bg, font="BissBody")
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg)
        style.configure("TLabelframe", background=bg, bordercolor="#D0D0D0")
        style.configure("TLabelframe.Label", background=bg)
        style.configure("TCheckbutton", background=bg)
        style.configure("TRadiobutton", background=bg)
        for cls in ("TCheckbutton", "TRadiobutton"):
            style.map(cls, background=[("disabled", bg), ("active", "#EAEAEA")])
        style.configure("TNotebook", background=bg, bordercolor="#D0D0D0")
        style.configure("TNotebook.Tab", background="#E6E6E6", bordercolor="#D0D0D0")
        style.map("TNotebook.Tab", background=[("selected", bg)])
        style.configure("TEntry", fieldbackground=field)
        style.configure("TCombobox", fieldbackground=field)
        style.map("TCombobox", fieldbackground=[("readonly", field)])
        style.configure("TSpinbox", fieldbackground=field)
        style.configure("Treeview", fieldbackground=field, background=field)
        style.configure("TButton", padding=(10, 3))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        bordercolor=ACCENT_PRESSED, lightcolor=ACCENT, darkcolor=ACCENT_PRESSED,
                        focuscolor="white", font="BissBold", padding=(16, 5))
        style.map("Accent.TButton",
                  background=[("disabled", "#B8C9DB"), ("pressed", ACCENT_PRESSED), ("active", ACCENT_ACTIVE)],
                  foreground=[("disabled", "#F3F3F3")],
                  lightcolor=[("pressed", ACCENT_PRESSED)])
    else:
        bg = style.lookup("TFrame", "background") or "SystemButtonFace"
        style.configure("Accent.TButton", font="BissBold", padding=(16, 4))

    style.configure("TNotebook.Tab", padding=(12, 4))
    style.configure("TLabelframe.Label", font="BissHeading")
    style.configure("Caption.TLabel", font="BissCaption", foreground=MUTED)
    style.configure("Heading.TLabel", font="BissHeading")
    style.configure("Title.TLabel", font="BissTitle")
    style.configure("Success.TLabel", foreground=SUCCESS)
    style.configure("Error.TLabel", foreground=ERROR)
    style.configure("Warning.TLabel", foreground=WARNING)
    style.configure("Link.TButton", padding=(6, 1))
    style.configure("Banner.TFrame", background="#FFF4CE")
    style.configure("Banner.TLabel", background="#FFF4CE", foreground="#4D3A00")
    style.configure("Toolbutton", padding=(6, 2))
    style.configure("Status.TFrame", background=bg)
    return {"theme": theme, "background": bg, "native": native}


# --------------------------------------------------------------------------
class ScrollableFrame(ttk.Frame):
    """A frame whose `.body` scrolls vertically when it is taller than the viewport."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        bg = ttk.Style(self).lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=bg)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll_set)
        self.body = ttk.Frame(self.canvas, padding=(PAD_L, PAD, PAD_L, PAD))
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        ScrollableFrame._instances[str(self.canvas)] = self
        ScrollableFrame._install_wheel(self)

    _instances: ClassVar[dict[str, ScrollableFrame]] = {}
    _wheel_installed = False

    def _on_scroll_set(self, first, last):
        self.vbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.vbar.grid_remove()
        else:
            self.vbar.grid()

    def _on_body_configure(self, _event=None):
        w, h = self.body.winfo_reqwidth(), self.body.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, w, h))
        # Request the natural size so the window's natural size is known;
        # grid shrinks the canvas (and the scrollbar appears) when space is short.
        if int(self.canvas.cget("height")) != h or int(self.canvas.cget("width")) != w:
            self.canvas.configure(width=w, height=h)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._on_body_configure()

    @classmethod
    def _install_wheel(cls, widget):
        """One global wheel handler that scrolls the ScrollableFrame under the pointer."""
        if cls._wheel_installed:
            return
        cls._wheel_installed = True
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind_all(seq, cls._on_wheel, add="+")

    @classmethod
    def _on_wheel(cls, event):
        w = event.widget
        if isinstance(w, str) or not hasattr(w, "winfo_class"):
            return
        # Lists and text boxes scroll themselves.
        if w.winfo_class() in ("Treeview", "Text", "Listbox", "TCombobox", "TSpinbox"):
            return
        target = None
        path = str(w)
        while path:
            if path in cls._instances:
                target = cls._instances[path]
                break
            path = path.rpartition(".")[0]
        if target is None or not target.winfo_ismapped():
            return
        if target.canvas.yview() == (0.0, 1.0):
            return
        num = getattr(event, "num", None)
        if num == 4:
            delta = -1
        elif num == 5:
            delta = 1
        elif sys.platform == "darwin":
            delta = -event.delta
        else:
            delta = (-1 if event.delta > 0 else 1) * max(1, abs(event.delta) // 120)
        target.canvas.yview_scroll(delta * 3, "units")

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)


# --------------------------------------------------------------------------
class ActionBar(ttk.Frame):
    """Bottom bar of a tab: [status / progress / result actions] ... [Cancel] [Primary].

    All methods must be called on the Tk main thread.
    """

    def __init__(self, parent, text: str, command: Callable, hint: str = ""):
        super().__init__(parent, padding=(PAD_L, PAD, PAD_L, PAD))
        self.columnconfigure(0, weight=1)
        self._idle_hint = hint
        self._on_cancel: Callable | None = None
        self.busy = False

        self.status = ttk.Frame(self)
        self.status.grid(row=0, column=0, sticky="ew")
        self.status.columnconfigure(1, weight=1)
        self.icon = ttk.Label(self.status, text="", width=2, anchor="center", font="BissBold")
        self.message = ttk.Label(self.status, text=hint, style="Caption.TLabel", anchor="w", wraplength=360)
        self.icon.grid(row=0, column=0, sticky="w")
        self.message.grid(row=0, column=1, sticky="ew")
        self.message.bind("<Configure>", lambda e: self.message.configure(wraplength=max(120, e.width)))
        self.progressbar = ttk.Progressbar(self.status, mode="indeterminate", length=180)
        self.links = ttk.Frame(self.status)

        self.cancel_btn = ttk.Button(self, text="Cancel", command=self._cancel)
        self.button = ttk.Button(self, text=text, command=command, style="Accent.TButton",
                                 default="active")
        self.button.grid(row=0, column=2, sticky="e", padx=(PAD, 0))

    # -- states ---------------------------------------------------------------
    def set_hint(self, text: str, kind: str = "hint"):
        """Idle guidance text; replaces any previous result."""
        self._idle_hint = text
        if not self.busy:
            self._clear_links()
            self._show(kind if kind != "hint" else None, text)

    def start(self, text: str, cancellable: bool = False, on_cancel: Callable | None = None,
              determinate: bool = False):
        self.busy = True
        self._on_cancel = on_cancel
        self.button.state(["disabled"])
        self._clear_links()
        self._show(None, text, caption=False)
        self.progressbar.configure(mode="determinate" if determinate else "indeterminate",
                                   value=0, maximum=100)
        self.progressbar.grid(row=0, column=2, sticky="e", padx=(PAD, 0))
        if not determinate:
            self.progressbar.start(12)
        if cancellable:
            self.cancel_btn.state(["!disabled"])
            self.cancel_btn.configure(text="Cancel")
            self.cancel_btn.grid(row=0, column=1, sticky="e", padx=(PAD, 0))

    def progress(self, text: str | None = None, value: float | None = None,
                 maximum: float | None = None):
        if text is not None:
            self.message.configure(text=text)
        if maximum is not None:
            self.progressbar.stop()
            self.progressbar.configure(mode="determinate", maximum=maximum)
        if value is not None:
            if str(self.progressbar.cget("mode")) != "determinate":
                self.progressbar.stop()
                self.progressbar.configure(mode="determinate")
            self.progressbar.configure(value=value)

    def finish(self, kind: str, text: str, actions: Sequence[tuple[str, Callable]] = ()):
        """kind: 'success' | 'error' | 'warning' | 'cancelled' | 'info'."""
        self.busy = False
        self._on_cancel = None
        self.progressbar.stop()
        self.progressbar.grid_remove()
        self.cancel_btn.grid_remove()
        self.button.state(["!disabled"])
        self._show(kind, text, caption=False)
        self._set_links(actions)

    def reset(self):
        if not self.busy:
            self._clear_links()
            self._show(None, self._idle_hint)

    # -- internals ------------------------------------------------------------
    def _show(self, kind: str | None, text: str, caption: bool = True):
        icons = {"success": ("✔", "Success.TLabel"), "error": ("✖", "Error.TLabel"),
                 "warning": ("⚠", "Warning.TLabel"), "cancelled": ("–", "Caption.TLabel"),
                 "info": ("ℹ", "TLabel")}
        icon, style = icons.get(kind, ("", "TLabel"))
        self.icon.configure(text=icon, style=style)
        if kind in ("success", "error", "warning"):
            self.message.configure(text=text, style=style)
        else:
            self.message.configure(text=text, style="Caption.TLabel" if caption and not kind else "TLabel")

    def _clear_links(self):
        for child in self.links.winfo_children():
            child.destroy()
        self.links.grid_remove()

    def _set_links(self, actions):
        self._clear_links()
        for label, cb in actions:
            ttk.Button(self.links, text=label, command=cb, style="Link.TButton").pack(side="left", padx=(PAD_S, 0))
        if actions:
            self.links.grid(row=0, column=2, sticky="e", padx=(PAD, 0))

    def _cancel(self):
        if self._on_cancel:
            self.cancel_btn.state(["disabled"])
            self.cancel_btn.configure(text="Cancelling…")
            self.message.configure(text="Cancelling… the current step will finish first.")
            self._on_cancel()


# --------------------------------------------------------------------------
class Banner(ttk.Frame):
    """Inline notice with optional action buttons. Hidden until show() is called."""

    def __init__(self, parent, **grid_kw):
        super().__init__(parent, style="Banner.TFrame", padding=(PAD, PAD_S + 2))
        self._grid_kw = grid_kw
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="⚠", style="Banner.TLabel", font="BissBold").grid(
            row=0, column=0, sticky="nw", padx=(0, PAD))
        self.text = ttk.Label(self, style="Banner.TLabel", justify="left", wraplength=480)
        self.text.grid(row=0, column=1, sticky="ew")
        self.text.bind("<Configure>", lambda e: self.text.configure(wraplength=max(200, e.width - 4)))
        self.buttons = ttk.Frame(self, style="Banner.TFrame")
        self.buttons.grid(row=1, column=1, sticky="w", pady=(PAD_S, 0))
        self.visible = False

    def show(self, text: str, actions: Iterable[tuple[str, Callable]] = ()):
        self.text.configure(text=text)
        for child in self.buttons.winfo_children():
            child.destroy()
        for label, cb in actions:
            ttk.Button(self.buttons, text=label, command=cb, style="Link.TButton").pack(side="left", padx=(0, PAD_S))
        self.grid(**self._grid_kw)
        self.visible = True

    def hide(self):
        self.grid_remove()
        self.visible = False


# --------------------------------------------------------------------------
class Collapsible(ttk.Frame):
    """A disclosure section: a toggle button and a body frame shown on demand."""

    def __init__(self, parent, title: str, opened: bool = False,
                 on_toggle: Callable[[bool], None] | None = None):
        super().__init__(parent)
        self._title = title
        self._on_toggle = on_toggle
        self.columnconfigure(0, weight=1)
        self.toggle_btn = ttk.Button(self, style="Toolbutton", command=self.toggle)
        self.toggle_btn.grid(row=0, column=0, sticky="w")
        self.body = ttk.Frame(self, padding=(PAD_L + PAD, PAD_S, 0, 0))
        self.opened = not opened
        self.toggle()

    def toggle(self):
        self.opened = not self.opened
        arrow = "▾" if self.opened else "▸"
        self.toggle_btn.configure(text=f"{arrow} {self._title}")
        if self.opened:
            self.body.grid(row=1, column=0, sticky="ew")
        else:
            self.body.grid_remove()
        if self._on_toggle:
            self._on_toggle(self.opened)


# --------------------------------------------------------------------------
class InfoChip(ttk.Label):
    """One-line file facts, e.g. "✔ Chinese · 6 lines · 0:19 · UTF-8"."""

    def __init__(self, parent, **kw):
        super().__init__(parent, style="Caption.TLabel", anchor="w", **kw)

    def show(self, text: str, kind: str = "info"):
        prefix = {"ok": "✔ ", "warning": "⚠ ", "error": "✖ ", "busy": "… "}.get(kind, "")
        style = {"ok": "Caption.TLabel", "warning": "Warning.TLabel", "error": "Error.TLabel"}.get(kind, "Caption.TLabel")
        self.configure(text=prefix + text if text else "", style=style)

    def clear(self):
        self.configure(text="")
