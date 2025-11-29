"""
Cross-platform GUI for the Bilingual Subtitle Suite.

This module provides a complete graphical interface with full feature parity
to the CLI, using Tkinter for cross-platform compatibility.

Features:
- Logo and branding
- Drag and drop support
- Subtitle preview and info
- Progress indicators
- All CLI operations
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import sys
import os
from pathlib import Path
from typing import Optional, List, Callable, Tuple
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.constants import APP_NAME, APP_VERSION, VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Try to import PIL for logo display
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class LogHandler(logging.Handler):
    """Custom logging handler that sends logs to a queue for GUI display."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(msg)


class DragDropMixin:
    """Mixin to add drag-and-drop support."""

    def setup_drag_drop(self, widget, callback):
        """Set up drag and drop for a widget."""
        try:
            # Try to use tkinterdnd2 if available
            widget.drop_target_register('DND_Files')
            widget.dnd_bind('<<Drop>>', callback)
        except (AttributeError, tk.TclError, Exception):
            # tkinterdnd2 not available - drag-drop disabled but app still works
            pass


class SubtitleInfoPanel(ttk.LabelFrame):
    """Panel showing subtitle file information."""

    def __init__(self, parent, title="Subtitle Info"):
        super().__init__(parent, text=title, padding="5")

        self.info_labels = {}

        # Create info rows
        info_items = [
            ("file", "File:"),
            ("events", "Events:"),
            ("duration", "Duration:"),
            ("language", "Language:"),
            ("encoding", "Encoding:"),
        ]

        for i, (key, label) in enumerate(info_items):
            ttk.Label(self, text=label, font=('TkDefaultFont', 9, 'bold')).grid(
                row=i, column=0, sticky='w', padx=(0, 10))
            self.info_labels[key] = ttk.Label(self, text="-", font=('TkDefaultFont', 9))
            self.info_labels[key].grid(row=i, column=1, sticky='w')

    def update_info(self, file_path: Optional[Path] = None):
        """Update info display for a subtitle file."""
        if not file_path or not file_path.exists():
            for label in self.info_labels.values():
                label.config(text="-")
            return

        try:
            from core.subtitle_formats import SubtitleFormatFactory
            from core.language_detection import LanguageDetector
            from core.encoding_detection import EncodingDetector

            # Get file info
            self.info_labels["file"].config(text=file_path.name[:40] + "..." if len(file_path.name) > 40 else file_path.name)

            # Detect encoding
            try:
                encoding = EncodingDetector.detect_encoding(file_path)
                if encoding:
                    self.info_labels["encoding"].config(text=encoding.upper())
                else:
                    self.info_labels["encoding"].config(text="Unknown")
            except (IOError, OSError, ValueError, TypeError):
                self.info_labels["encoding"].config(text="Unknown")

            # Detect language
            lang = LanguageDetector.detect_language_from_filename(str(file_path))
            if lang == 'unknown':
                lang = LanguageDetector.detect_subtitle_language(file_path)
            lang_display = {'zh': 'Chinese', 'en': 'English', 'ja': 'Japanese', 'ko': 'Korean'}.get(lang, lang.upper())
            self.info_labels["language"].config(text=lang_display)

            # Parse subtitle
            try:
                sub_file = SubtitleFormatFactory.parse_file(file_path)
                self.info_labels["events"].config(text=str(len(sub_file.events)))

                if sub_file.events:
                    duration_sec = sub_file.events[-1].end
                    hours = int(duration_sec // 3600)
                    minutes = int((duration_sec % 3600) // 60)
                    seconds = int(duration_sec % 60)
                    self.info_labels["duration"].config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                else:
                    self.info_labels["duration"].config(text="-")
            except (IOError, OSError, ValueError, UnicodeDecodeError):
                self.info_labels["events"].config(text="Error")
                self.info_labels["duration"].config(text="-")

        except Exception as e:
            logger.debug(f"Error getting subtitle info: {e}")


class BISSGui:
    """Main GUI application class."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("950x750")
        self.root.minsize(850, 650)

        # Configure style
        self.style = ttk.Style()
        self._configure_styles()

        # Log queue for thread-safe logging
        self.log_queue = queue.Queue()

        # Configure logging to GUI
        self._setup_logging()

        # Build the interface
        self._create_header()
        self._create_menu()
        self._create_main_interface()
        self._create_status_bar()

        # Start log polling
        self._poll_log_queue()

        # Center window
        self._center_window()

    def _configure_styles(self):
        """Configure ttk styles for better appearance."""
        self.style.configure('Header.TLabel', font=('Segoe UI', 11))
        self.style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'))
        self.style.configure('Subtitle.TLabel', font=('Segoe UI', 9), foreground='gray')
        self.style.configure('Action.TButton', font=('Segoe UI', 10, 'bold'), padding=(20, 10))
        self.style.configure('Big.TButton', font=('Segoe UI', 11), padding=(30, 15))

    def _setup_logging(self):
        """Set up logging to display in GUI."""
        self.log_handler = LogHandler(self.log_queue)
        self.log_handler.setFormatter(logging.Formatter('%(message)s'))

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)

    def _center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _create_header(self):
        """Create header with logo."""
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Try to load and display logo
        self.logo_image = None
        logo_path = Path(__file__).parent.parent / "images" / "biss-logo.png"

        if logo_path.exists() and HAS_PIL:
            try:
                # Load and resize logo
                img = Image.open(logo_path)
                # Calculate new size maintaining aspect ratio
                max_height = 60
                ratio = max_height / img.height
                new_width = int(img.width * ratio)
                img = img.resize((new_width, max_height), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(img)

                logo_label = ttk.Label(header_frame, image=self.logo_image)
                logo_label.pack(side=tk.LEFT, padx=(0, 20))
            except Exception as e:
                logger.debug(f"Could not load logo: {e}")
                self._create_text_header(header_frame)
        else:
            self._create_text_header(header_frame)

        # Version and info on right
        info_frame = ttk.Frame(header_frame)
        info_frame.pack(side=tk.RIGHT)

        ttk.Label(info_frame, text=f"v{APP_VERSION}", style='Subtitle.TLabel').pack(anchor='e')
        ttk.Label(info_frame, text="Create bilingual subtitles easily",
                 style='Subtitle.TLabel').pack(anchor='e')

    def _create_text_header(self, parent):
        """Create text-based header when logo unavailable."""
        title_frame = ttk.Frame(parent)
        title_frame.pack(side=tk.LEFT)

        ttk.Label(title_frame, text="BISS", style='Title.TLabel',
                 foreground='#1E90FF').pack(anchor='w')
        ttk.Label(title_frame, text="Bilingual Subtitle Suite",
                 style='Subtitle.TLabel').pack(anchor='w')

    def _create_menu(self):
        """Create the menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Subtitle...", command=self._open_subtitle, accelerator="Ctrl+O")
        file_menu.add_command(label="Open Video...", command=self._open_video)
        file_menu.add_separator()
        file_menu.add_command(label="Preview Subtitle...", command=lambda: self._show_subtitle_preview(), accelerator="Ctrl+P")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Alt+F4")

        # Bind keyboard shortcuts
        self.root.bind('<Control-o>', lambda e: self._open_subtitle())
        self.root.bind('<Control-p>', lambda e: self._show_subtitle_preview())

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Merge Subtitles", command=lambda: self.notebook.select(0))
        tools_menu.add_command(label="Shift Timing", command=lambda: self.notebook.select(1))
        tools_menu.add_command(label="Convert Encoding", command=lambda: self.notebook.select(2))
        tools_menu.add_separator()
        tools_menu.add_command(label="Batch Operations", command=lambda: self.notebook.select(3))

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Quick Guide", command=self._show_help)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_interface(self):
        """Create the main tabbed interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs (Merge first as primary function)
        self._create_merge_tab()
        self._create_shift_tab()
        self._create_convert_tab()
        self._create_batch_tab()

        # Log output area
        log_frame = ttk.LabelFrame(main_frame, text="Output Log", padding="5")
        log_frame.pack(fill=tk.X, pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state='disabled',
                                                   font=('Consolas', 9), wrap=tk.WORD)
        self.log_text.pack(fill=tk.X, expand=True)

        # Log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(log_controls, text="Clear", command=self._clear_log, width=8).pack(side=tk.RIGHT)

    def _create_merge_tab(self):
        """Create the Merge Subtitles tab - Primary function."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Merge Subtitles  ")

        # Store reference
        self.merge_tab = tab

        # Quick intro
        intro_frame = ttk.Frame(tab)
        intro_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(intro_frame, text="Combine two subtitle files into one bilingual subtitle",
                 style='Subtitle.TLabel').pack(anchor='w')

        # === Input Mode Selection ===
        self.merge_mode_frame = ttk.LabelFrame(tab, text="Input Mode", padding="10")
        self.merge_mode_frame.pack(fill=tk.X, pady=(0, 10))

        mode_inner = ttk.Frame(self.merge_mode_frame)
        mode_inner.pack(fill=tk.X)

        self.merge_mode_var = tk.StringVar(value="files")
        ttk.Radiobutton(mode_inner, text="Two subtitle files (auto-detect languages)",
                       variable=self.merge_mode_var,
                       value="files", command=self._update_merge_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_inner, text="Extract from video file",
                       variable=self.merge_mode_var,
                       value="video", command=self._update_merge_mode).pack(side=tk.LEFT, padx=(30, 0))

        # === Two Files Input Frame ===
        self.merge_files_frame = ttk.LabelFrame(tab, text="Subtitle Files", padding="10")
        self.merge_files_frame.pack(fill=tk.X, pady=(0, 10))

        # File 1 with info panel
        f1_container = ttk.Frame(self.merge_files_frame)
        f1_container.pack(fill=tk.X, pady=(0, 10))

        f1_input = ttk.Frame(f1_container)
        f1_input.pack(fill=tk.X)
        ttk.Label(f1_input, text="File 1:", width=8).pack(side=tk.LEFT)
        self.merge_file1_var = tk.StringVar()
        self.merge_file1_var.trace('w', lambda *args: self._on_file1_changed())
        f1_entry = ttk.Entry(f1_input, textvariable=self.merge_file1_var, width=55)
        f1_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f1_input, text="Browse...", command=lambda: self._browse_merge_file(1)).pack(side=tk.LEFT, padx=(5, 0))

        self.file1_lang_label = ttk.Label(f1_input, text="", foreground='#1E90FF', font=('TkDefaultFont', 9, 'bold'))
        self.file1_lang_label.pack(side=tk.LEFT, padx=(10, 0))

        # File 2 with info panel
        f2_container = ttk.Frame(self.merge_files_frame)
        f2_container.pack(fill=tk.X)

        f2_input = ttk.Frame(f2_container)
        f2_input.pack(fill=tk.X)
        ttk.Label(f2_input, text="File 2:", width=8).pack(side=tk.LEFT)
        self.merge_file2_var = tk.StringVar()
        self.merge_file2_var.trace('w', lambda *args: self._on_file2_changed())
        f2_entry = ttk.Entry(f2_input, textvariable=self.merge_file2_var, width=55)
        f2_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f2_input, text="Browse...", command=lambda: self._browse_merge_file(2)).pack(side=tk.LEFT, padx=(5, 0))

        self.file2_lang_label = ttk.Label(f2_input, text="", foreground='#1E90FF', font=('TkDefaultFont', 9, 'bold'))
        self.file2_lang_label.pack(side=tk.LEFT, padx=(10, 0))

        # Swap button
        swap_frame = ttk.Frame(self.merge_files_frame)
        swap_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(swap_frame, text="Swap Files", command=self._swap_merge_files, width=12).pack(side=tk.LEFT)
        ttk.Label(swap_frame, text="Language detection is automatic - file order doesn't matter",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(15, 0))

        # === Video Input Frame (hidden by default) ===
        self.merge_video_frame = ttk.LabelFrame(tab, text="Video File", padding="10")

        v_frame = ttk.Frame(self.merge_video_frame)
        v_frame.pack(fill=tk.X)
        self.merge_video_var = tk.StringVar()
        ttk.Entry(v_frame, textvariable=self.merge_video_var, width=65).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(v_frame, text="Browse...", command=self._browse_merge_video).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(v_frame, text="List Tracks", command=self._list_tracks).pack(side=tk.LEFT, padx=(5, 0))

        # === Options Frame ===
        options_frame = ttk.LabelFrame(tab, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Alignment options
        row1 = ttk.Frame(options_frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        self.merge_autoalign_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Auto-align (fix timing mismatches)",
                       variable=self.merge_autoalign_var).pack(side=tk.LEFT)

        self.merge_translation_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Use translation API for matching",
                       variable=self.merge_translation_var).pack(side=tk.LEFT, padx=(20, 0))

        # Row 2: Format and threshold
        row2 = ttk.Frame(options_frame)
        row2.pack(fill=tk.X)

        ttk.Label(row2, text="Output format:").pack(side=tk.LEFT)
        self.merge_format_var = tk.StringVar(value="srt")
        ttk.Combobox(row2, textvariable=self.merge_format_var, values=['srt', 'ass'],
                    width=6, state='readonly').pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(row2, text="Alignment threshold:").pack(side=tk.LEFT)
        self.merge_threshold_var = tk.StringVar(value="0.8")
        ttk.Entry(row2, textvariable=self.merge_threshold_var, width=6).pack(side=tk.LEFT, padx=(5, 0))

        # === Output Frame ===
        output_frame = ttk.LabelFrame(tab, text="Output", padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        out_row = ttk.Frame(output_frame)
        out_row.pack(fill=tk.X)
        ttk.Label(out_row, text="Save as:").pack(side=tk.LEFT)
        self.merge_output_var = tk.StringVar()
        ttk.Entry(out_row, textvariable=self.merge_output_var, width=55).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(out_row, text="Browse...", command=self._browse_merge_output).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(output_frame, text="Leave empty for auto-generated filename (e.g., movie.zh-en.srt)",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(5, 0))

        # === Action Button ===
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.merge_btn = ttk.Button(btn_frame, text="Merge Subtitles",
                                    command=self._execute_merge, style='Big.TButton')
        self.merge_btn.pack(side=tk.RIGHT)

        # Progress indicator
        self.merge_progress = ttk.Progressbar(btn_frame, mode='indeterminate', length=200)

    def _create_shift_tab(self):
        """Create the Shift Timing tab."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Shift Timing  ")

        # Intro
        ttk.Label(tab, text="Adjust subtitle timing by a fixed offset or set the first line to a specific time",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # File selection with info
        file_frame = ttk.LabelFrame(tab, text="Subtitle File", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        self.shift_file_var = tk.StringVar()
        self.shift_file_var.trace('w', lambda *args: self._on_shift_file_changed())
        ttk.Entry(file_row, textvariable=self.shift_file_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="Browse...", command=self._browse_shift_file).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(file_row, text="Preview",
                  command=lambda: self._show_subtitle_preview(self.shift_file_var.get())).pack(side=tk.LEFT, padx=(5, 0))

        # Info panel
        self.shift_info_panel = SubtitleInfoPanel(file_frame, "File Info")
        self.shift_info_panel.pack(fill=tk.X, pady=(10, 0))

        # Shift options
        options_frame = ttk.LabelFrame(tab, text="Shift Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Mode selection
        self.shift_mode_var = tk.StringVar(value="offset")

        mode_frame = ttk.Frame(options_frame)
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Radiobutton(mode_frame, text="Shift by offset", variable=self.shift_mode_var,
                       value="offset", command=self._update_shift_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="Set first line to timestamp", variable=self.shift_mode_var,
                       value="first_line", command=self._update_shift_mode).pack(side=tk.LEFT, padx=(30, 0))

        # Offset input
        self.offset_frame = ttk.Frame(options_frame)
        self.offset_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(self.offset_frame, text="Offset:").pack(side=tk.LEFT)
        self.shift_offset_var = tk.StringVar(value="-2.5s")
        ttk.Entry(self.offset_frame, textvariable=self.shift_offset_var, width=15).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(self.offset_frame, text="Examples: -2.5s, +1500ms, -2470ms",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(15, 0))

        # Quick offset buttons
        quick_frame = ttk.Frame(self.offset_frame)
        quick_frame.pack(side=tk.LEFT, padx=(20, 0))
        for offset in ["-5s", "-1s", "-0.5s", "+0.5s", "+1s", "+5s"]:
            ttk.Button(quick_frame, text=offset, width=5,
                      command=lambda o=offset: self.shift_offset_var.set(o)).pack(side=tk.LEFT, padx=1)

        # First line timestamp input (hidden by default)
        self.firstline_frame = ttk.Frame(options_frame)

        ttk.Label(self.firstline_frame, text="Set first line to:").pack(side=tk.LEFT)
        self.shift_firstline_var = tk.StringVar(value="00:00:50,000")
        ttk.Entry(self.firstline_frame, textvariable=self.shift_firstline_var, width=15).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(self.firstline_frame, text="Format: HH:MM:SS,mmm",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(15, 0))

        # Output options
        output_frame = ttk.LabelFrame(tab, text="Output", padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        self.shift_output_var = tk.StringVar()
        out_row = ttk.Frame(output_frame)
        out_row.pack(fill=tk.X)
        ttk.Label(out_row, text="Save as:").pack(side=tk.LEFT)
        ttk.Entry(out_row, textvariable=self.shift_output_var, width=55).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(out_row, text="Browse...", command=self._browse_shift_output).pack(side=tk.LEFT, padx=(5, 0))

        options_row = ttk.Frame(output_frame)
        options_row.pack(fill=tk.X, pady=(5, 0))

        self.shift_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_row, text="Create backup before modifying",
                       variable=self.shift_backup_var).pack(side=tk.LEFT)

        ttk.Label(options_row, text="(Leave output empty to modify original file)",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(20, 0))

        # Execute button
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Apply Shift", command=self._execute_shift,
                  style='Big.TButton').pack(side=tk.RIGHT)

    def _create_convert_tab(self):
        """Create the Convert Encoding tab."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Convert Encoding  ")

        # Intro
        ttk.Label(tab, text="Fix garbled characters by converting subtitle encoding to UTF-8",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # File selection
        file_frame = ttk.LabelFrame(tab, text="Subtitle File", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        self.convert_file_var = tk.StringVar()
        self.convert_file_var.trace('w', lambda *args: self._on_convert_file_changed())
        ttk.Entry(file_row, textvariable=self.convert_file_var, width=65).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="Browse...", command=self._browse_convert_file).pack(side=tk.LEFT, padx=(5, 0))

        # Info panel
        self.convert_info_panel = SubtitleInfoPanel(file_frame, "File Info")
        self.convert_info_panel.pack(fill=tk.X, pady=(10, 0))

        # Encoding detection display
        detect_frame = ttk.LabelFrame(tab, text="Detected Encoding", padding="10")
        detect_frame.pack(fill=tk.X, pady=(0, 10))

        self.detected_encoding_var = tk.StringVar(value="Select a file to detect encoding")
        self.encoding_label = ttk.Label(detect_frame, textvariable=self.detected_encoding_var,
                                        font=('TkDefaultFont', 11, 'bold'))
        self.encoding_label.pack(anchor='w')

        # Convert options
        options_frame = ttk.LabelFrame(tab, text="Conversion Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        enc_frame = ttk.Frame(options_frame)
        enc_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(enc_frame, text="Target encoding:").pack(side=tk.LEFT)
        self.convert_encoding_var = tk.StringVar(value="utf-8")
        enc_combo = ttk.Combobox(enc_frame, textvariable=self.convert_encoding_var, width=15,
                                values=['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'big5', 'shift-jis'])
        enc_combo.pack(side=tk.LEFT, padx=(5, 0))

        self.convert_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Create backup of original file",
                       variable=self.convert_backup_var).pack(anchor='w')

        self.convert_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Force conversion even if already target encoding",
                       variable=self.convert_force_var).pack(anchor='w')

        # Execute button
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Convert Encoding", command=self._execute_convert,
                  style='Big.TButton').pack(side=tk.RIGHT)

    def _create_batch_tab(self):
        """Create the Batch Operations tab."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Batch Operations  ")

        # Intro
        ttk.Label(tab, text="Process multiple files at once",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # Operation selection
        op_frame = ttk.LabelFrame(tab, text="Operation Type", padding="10")
        op_frame.pack(fill=tk.X, pady=(0, 10))

        self.batch_op_var = tk.StringVar(value="convert")
        ttk.Radiobutton(op_frame, text="Convert encoding (all subtitles to UTF-8)",
                       variable=self.batch_op_var, value="convert").pack(anchor='w')
        ttk.Radiobutton(op_frame, text="Merge from videos (extract and create bilingual)",
                       variable=self.batch_op_var, value="merge").pack(anchor='w')

        # Directory selection
        dir_frame = ttk.LabelFrame(tab, text="Directory", padding="10")
        dir_frame.pack(fill=tk.X, pady=(0, 10))

        d_frame = ttk.Frame(dir_frame)
        d_frame.pack(fill=tk.X)
        self.batch_dir_var = tk.StringVar()
        ttk.Entry(d_frame, textvariable=self.batch_dir_var, width=65).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(d_frame, text="Browse...", command=self._browse_batch_dir).pack(side=tk.LEFT, padx=(5, 0))

        self.batch_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dir_frame, text="Include subdirectories",
                       variable=self.batch_recursive_var).pack(anchor='w', pady=(5, 0))

        # Options
        options_frame = ttk.LabelFrame(tab, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        self.batch_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Create backups",
                       variable=self.batch_backup_var).pack(anchor='w')

        self.batch_autoconfirm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Auto-confirm all operations (no prompts)",
                       variable=self.batch_autoconfirm_var).pack(anchor='w')

        # Progress
        progress_frame = ttk.LabelFrame(tab, text="Progress", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.batch_progress_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.batch_progress_var).pack(anchor='w')

        self.batch_progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.batch_progress_bar.pack(fill=tk.X, pady=(5, 0))

        # Execute button
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Start Batch Processing", command=self._execute_batch,
                  style='Big.TButton').pack(side=tk.RIGHT)

    def _create_status_bar(self):
        """Create the status bar at the bottom."""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN,
                 anchor='w', padding=(5, 2)).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ==================== Event Handlers ====================

    def _on_file1_changed(self):
        """Handle file 1 path change."""
        path = self.merge_file1_var.get().strip()
        if path and Path(path).exists():
            lang = self._detect_file_language(Path(path))
            self.file1_lang_label.config(text=f"[{lang}]" if lang else "")
        else:
            self.file1_lang_label.config(text="")

    def _on_file2_changed(self):
        """Handle file 2 path change."""
        path = self.merge_file2_var.get().strip()
        if path and Path(path).exists():
            lang = self._detect_file_language(Path(path))
            self.file2_lang_label.config(text=f"[{lang}]" if lang else "")
        else:
            self.file2_lang_label.config(text="")

    def _on_shift_file_changed(self):
        """Handle shift file path change."""
        path = self.shift_file_var.get().strip()
        if path and Path(path).exists():
            self.shift_info_panel.update_info(Path(path))
        else:
            self.shift_info_panel.update_info(None)

    def _on_convert_file_changed(self):
        """Handle convert file path change."""
        path = self.convert_file_var.get().strip()
        if path and Path(path).exists():
            self.convert_info_panel.update_info(Path(path))
            self._detect_encoding()
        else:
            self.convert_info_panel.update_info(None)
            self.detected_encoding_var.set("Select a file to detect encoding")

    def _detect_file_language(self, path: Path) -> str:
        """Detect language of a subtitle file."""
        try:
            from core.language_detection import LanguageDetector
            lang = LanguageDetector.detect_language_from_filename(str(path))
            if lang == 'unknown':
                lang = LanguageDetector.detect_subtitle_language(path)
            return {'zh': 'Chinese', 'en': 'English', 'ja': 'Japanese', 'ko': 'Korean'}.get(lang, lang.upper())
        except (IOError, OSError, ValueError, UnicodeDecodeError):
            return ""

    def _swap_merge_files(self):
        """Swap the two merge input files."""
        file1 = self.merge_file1_var.get()
        file2 = self.merge_file2_var.get()
        self.merge_file1_var.set(file2)
        self.merge_file2_var.set(file1)

    def _update_shift_mode(self):
        """Update UI based on shift mode selection."""
        if self.shift_mode_var.get() == "offset":
            self.firstline_frame.pack_forget()
            self.offset_frame.pack(fill=tk.X, pady=(0, 5))
        else:
            self.offset_frame.pack_forget()
            self.firstline_frame.pack(fill=tk.X, pady=(0, 5))

    def _update_merge_mode(self):
        """Update UI based on merge mode selection."""
        if self.merge_mode_var.get() == "files":
            self.merge_video_frame.pack_forget()
            self.merge_files_frame.pack(fill=tk.X, pady=(0, 10), after=self.merge_mode_frame)
        else:
            self.merge_files_frame.pack_forget()
            self.merge_video_frame.pack(fill=tk.X, pady=(0, 10), after=self.merge_mode_frame)

    def _list_tracks(self):
        """List tracks in selected video."""
        video_path = self.merge_video_var.get().strip()
        if not video_path:
            messagebox.showerror("Error", "Please select a video file first")
            return

        def do_list():
            try:
                from core.video_containers import VideoContainerHandler
                handler = VideoContainerHandler()
                tracks = handler.list_subtitle_tracks(Path(video_path))

                if not tracks:
                    self.root.after(0, lambda: messagebox.showinfo("Tracks", "No subtitle tracks found in this video"))
                    return

                track_info = "Subtitle tracks found:\n\n"
                for t in tracks:
                    track_info += f"Track {t.track_id}: {t.language or 'Unknown'}"
                    if t.title:
                        track_info += f" - {t.title}"
                    track_info += f" ({t.codec})\n"

                self.root.after(0, lambda: messagebox.showinfo("Tracks", track_info))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to list tracks: {e}"))

        threading.Thread(target=do_list, daemon=True).start()

    # ==================== File Browsers ====================

    def _browse_shift_file(self):
        """Browse for subtitle file to shift."""
        filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Select Subtitle File", filetypes=filetypes)
        if path:
            self.shift_file_var.set(path)

    def _browse_shift_output(self):
        """Browse for shift output file."""
        filetypes = [("SRT files", "*.srt"), ("ASS files", "*.ass"), ("All files", "*.*")]
        path = filedialog.asksaveasfilename(title="Save As", filetypes=filetypes, defaultextension=".srt")
        if path:
            self.shift_output_var.set(path)

    def _browse_convert_file(self):
        """Browse for subtitle file to convert."""
        filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Select Subtitle File", filetypes=filetypes)
        if path:
            self.convert_file_var.set(path)

    def _browse_merge_file(self, file_num: int):
        """Browse for merge input file."""
        filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title=f"Select Subtitle File {file_num}", filetypes=filetypes)
        if path:
            if file_num == 1:
                self.merge_file1_var.set(path)
            else:
                self.merge_file2_var.set(path)

    def _browse_merge_video(self):
        """Browse for video file."""
        filetypes = [("Video files", "*.mkv *.mp4 *.avi *.mov *.webm *.ts"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Select Video File", filetypes=filetypes)
        if path:
            self.merge_video_var.set(path)

    def _browse_merge_output(self):
        """Browse for merge output file."""
        filetypes = [("SRT files", "*.srt"), ("ASS files", "*.ass"), ("All files", "*.*")]
        path = filedialog.asksaveasfilename(title="Save As", filetypes=filetypes, defaultextension=".srt")
        if path:
            self.merge_output_var.set(path)

    def _browse_batch_dir(self):
        """Browse for batch directory."""
        path = filedialog.askdirectory(title="Select Directory")
        if path:
            self.batch_dir_var.set(path)

    def _open_subtitle(self):
        """Open subtitle file from menu."""
        filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Open Subtitle File", filetypes=filetypes)
        if path:
            self.merge_file1_var.set(path)
            self.notebook.select(0)

    def _open_video(self):
        """Open video file from menu."""
        filetypes = [("Video files", "*.mkv *.mp4 *.avi *.mov *.webm"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Open Video File", filetypes=filetypes)
        if path:
            self.merge_video_var.set(path)
            self.merge_mode_var.set("video")
            self._update_merge_mode()
            self.notebook.select(0)

    # ==================== Operations ====================

    def _execute_shift(self):
        """Execute the shift operation."""
        input_path = self.shift_file_var.get().strip()
        if not input_path:
            messagebox.showerror("Error", "Please select a subtitle file")
            return

        if not Path(input_path).exists():
            messagebox.showerror("Error", f"File not found: {input_path}")
            return

        output_path = self.shift_output_var.get().strip() or None
        create_backup = self.shift_backup_var.get()

        def run_shift():
            try:
                from processors.timing_adjuster import TimingAdjuster
                adjuster = TimingAdjuster(create_backup=create_backup)

                if self.shift_mode_var.get() == "offset":
                    offset_str = self.shift_offset_var.get().strip()
                    offset_ms = adjuster.parse_offset_string(offset_str)
                    success = adjuster.adjust_by_offset(
                        Path(input_path), offset_ms,
                        Path(output_path) if output_path else None
                    )
                else:
                    timestamp = self.shift_firstline_var.get().strip()
                    success = adjuster.adjust_first_line_to(
                        Path(input_path), timestamp,
                        Path(output_path) if output_path else None
                    )

                if success:
                    self.root.after(0, lambda: messagebox.showinfo("Success", "Timing shift applied successfully!"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Failed to shift timing"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Shift failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))

        self._set_status("Shifting timing...")
        threading.Thread(target=run_shift, daemon=True).start()

    def _execute_convert(self):
        """Execute the encoding conversion."""
        input_path = self.convert_file_var.get().strip()
        if not input_path:
            messagebox.showerror("Error", "Please select a subtitle file")
            return

        if not Path(input_path).exists():
            messagebox.showerror("Error", f"File not found: {input_path}")
            return

        encoding = self.convert_encoding_var.get()
        create_backup = self.convert_backup_var.get()
        force = self.convert_force_var.get()

        def run_convert():
            try:
                from processors.converter import EncodingConverter
                converter = EncodingConverter()

                success = converter.convert_file(
                    file_path=Path(input_path),
                    keep_backup=create_backup,
                    force_conversion=force,
                    target_encoding=encoding
                )

                if success:
                    self.root.after(0, lambda: messagebox.showinfo("Success", "Encoding converted successfully!"))
                else:
                    self.root.after(0, lambda: messagebox.showinfo("Info", "No conversion needed (already correct encoding)"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Conversion failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))

        self._set_status("Converting encoding...")
        threading.Thread(target=run_convert, daemon=True).start()

    def _execute_merge(self):
        """Execute the merge operation."""
        mode = self.merge_mode_var.get()

        if mode == "files":
            file1 = self.merge_file1_var.get().strip()
            file2 = self.merge_file2_var.get().strip()

            if not file1 or not file2:
                messagebox.showerror("Error", "Please select both subtitle files")
                return

            if not Path(file1).exists():
                messagebox.showerror("Error", f"File not found: {file1}")
                return
            if not Path(file2).exists():
                messagebox.showerror("Error", f"File not found: {file2}")
                return
        else:
            video = self.merge_video_var.get().strip()
            if not video:
                messagebox.showerror("Error", "Please select a video file")
                return
            if not Path(video).exists():
                messagebox.showerror("Error", f"File not found: {video}")
                return

        output_path = self.merge_output_var.get().strip() or None
        auto_align = self.merge_autoalign_var.get()
        use_translation = self.merge_translation_var.get()
        threshold = float(self.merge_threshold_var.get() or 0.8)
        output_format = self.merge_format_var.get()

        def run_merge():
            try:
                from processors.merger import BilingualMerger
                from core.language_detection import LanguageDetector

                merger = BilingualMerger(
                    auto_align=auto_align,
                    use_translation=use_translation,
                    alignment_threshold=threshold
                )

                if mode == "files":
                    file1 = self.merge_file1_var.get().strip()
                    file2 = self.merge_file2_var.get().strip()

                    # Auto-detect languages
                    lang1 = LanguageDetector.detect_language_from_filename(file1)
                    if lang1 == 'unknown':
                        lang1 = LanguageDetector.detect_subtitle_language(Path(file1))

                    lang2 = LanguageDetector.detect_language_from_filename(file2)
                    if lang2 == 'unknown':
                        lang2 = LanguageDetector.detect_subtitle_language(Path(file2))

                    # Assign based on detection
                    if lang1 in ['zh', 'ja', 'ko']:
                        chinese_path, english_path = Path(file1), Path(file2)
                    elif lang2 in ['zh', 'ja', 'ko']:
                        chinese_path, english_path = Path(file2), Path(file1)
                    elif lang1 == 'en':
                        chinese_path, english_path = Path(file2), Path(file1)
                    else:
                        chinese_path, english_path = Path(file1), Path(file2)

                    success = merger.merge_subtitle_files(
                        chinese_path=chinese_path,
                        english_path=english_path,
                        output_path=Path(output_path) if output_path else None,
                        output_format=output_format
                    )
                else:
                    video = self.merge_video_var.get().strip()
                    success = merger.process_video(
                        video_path=Path(video),
                        output_format=output_format,
                        output_path=Path(output_path) if output_path else None
                    )

                if success:
                    self.root.after(0, lambda: messagebox.showinfo("Success", "Subtitles merged successfully!"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Merge failed - check log for details"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Merge failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))

        self._set_status("Merging subtitles...")
        threading.Thread(target=run_merge, daemon=True).start()

    def _execute_batch(self):
        """Execute batch operation."""
        directory = self.batch_dir_var.get().strip()
        if not directory:
            messagebox.showerror("Error", "Please select a directory")
            return

        if not Path(directory).exists():
            messagebox.showerror("Error", f"Directory not found: {directory}")
            return

        operation = self.batch_op_var.get()
        recursive = self.batch_recursive_var.get()
        create_backup = self.batch_backup_var.get()
        auto_confirm = self.batch_autoconfirm_var.get()

        def run_batch():
            try:
                from processors.batch_processor import BatchProcessor
                from utils.file_operations import FileHandler

                batch_processor = BatchProcessor(auto_confirm=auto_confirm)

                if operation == "convert":
                    files = FileHandler.find_subtitle_files(Path(directory), recursive)
                    total = len(files)

                    if total == 0:
                        self.root.after(0, lambda: messagebox.showinfo("Info", "No subtitle files found"))
                        return

                    if not auto_confirm:
                        if not messagebox.askyesno("Confirm", f"Convert {total} files to UTF-8?"):
                            return

                    self.root.after(0, lambda: self.batch_progress_var.set(f"Processing {total} files..."))

                    results = batch_processor.process_subtitles_batch(
                        subtitle_paths=files,
                        operation="convert",
                        keep_backup=create_backup
                    )

                    msg = f"Completed!\nProcessed: {results['processed']}\nFailed: {results['failed']}"
                    self.root.after(0, lambda: messagebox.showinfo("Complete", msg))

                else:  # merge
                    files = FileHandler.find_video_files(Path(directory), recursive)
                    total = len(files)

                    if total == 0:
                        self.root.after(0, lambda: messagebox.showinfo("Info", "No video files found"))
                        return

                    if not auto_confirm:
                        if not messagebox.askyesno("Confirm", f"Process {total} video files?"):
                            return

                    self.root.after(0, lambda: self.batch_progress_var.set(f"Processing {total} videos..."))

                    results = batch_processor.process_directory_interactive(
                        directory=Path(directory),
                        pattern="*"
                    )

                    msg = f"Completed!\nSuccessful: {results['successful']}\nFailed: {results['failed']}\nSkipped: {results['skipped']}"
                    self.root.after(0, lambda: messagebox.showinfo("Complete", msg))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Batch operation failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))
                self.root.after(0, lambda: self.batch_progress_var.set("Ready"))

        self._set_status("Running batch operation...")
        self.batch_progress_var.set("Starting...")
        threading.Thread(target=run_batch, daemon=True).start()

    def _detect_encoding(self):
        """Detect encoding of the selected file."""
        input_path = self.convert_file_var.get().strip()
        if not input_path or not Path(input_path).exists():
            self.detected_encoding_var.set("Select a valid file")
            return

        try:
            from core.encoding_detection import EncodingDetector
            encoding = EncodingDetector.detect_encoding(Path(input_path))

            if encoding:
                # Encoding detected successfully - show in green
                self.encoding_label.config(foreground='green')
                self.detected_encoding_var.set(f"{encoding.upper()}")
            else:
                # Detection failed
                self.encoding_label.config(foreground='red')
                self.detected_encoding_var.set("Could not detect encoding")
        except Exception as e:
            self.detected_encoding_var.set(f"Detection failed: {str(e)}")

    # ==================== Utility Methods ====================

    def _set_status(self, message: str):
        """Update status bar."""
        self.status_var.set(message)

    def _clear_log(self):
        """Clear the log text area."""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def _poll_log_queue(self):
        """Poll the log queue and update the text widget."""
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, msg + '\n')
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
            except queue.Empty:
                break

        self.root.after(100, self._poll_log_queue)

    def _show_help(self):
        """Show help dialog."""
        help_text = """BISS - Bilingual Subtitle Suite
Quick Guide

MERGE SUBTITLES (Main Feature)
1. Select two subtitle files using Browse buttons
2. Languages are detected automatically
3. Click "Merge Subtitles"
4. Output: filename.zh-en.srt

SHIFT TIMING
- Offset: Shift all subtitles by time (e.g., -2.5s)
- First Line: Set exact start time for first subtitle

CONVERT ENCODING
- Fix garbled characters by converting to UTF-8
- Encoding is auto-detected

TIPS
- File order doesn't matter - languages are auto-detected
- Use "Auto-align" for timing mismatches
- Use "Swap Files" button if needed
"""
        messagebox.showinfo("Quick Guide", help_text)

    def _show_shortcuts(self):
        """Show keyboard shortcuts."""
        shortcuts = """Keyboard Shortcuts

Ctrl+O    Open subtitle file
Ctrl+P    Preview subtitle file
Alt+F4    Exit application

Tab navigation works in all dialogs.
"""
        messagebox.showinfo("Keyboard Shortcuts", shortcuts)

    def _show_about(self):
        """Show about dialog."""
        about_text = f"""{APP_NAME}
Version {APP_VERSION}

A comprehensive tool for creating bilingual subtitles.

Features:
- Merge subtitles (Chinese/Japanese/Korean + English)
- Shift subtitle timing
- Convert subtitle encoding
- Batch processing

Supports: SRT, ASS, VTT formats
Cross-platform: Windows, macOS, Linux
"""
        messagebox.showinfo("About", about_text)

    def _show_subtitle_preview(self, file_path: Optional[str] = None):
        """
        Show a preview window with subtitle content.

        Args:
            file_path: Path to subtitle file, or None to prompt for file
        """
        if not file_path:
            filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
            file_path = filedialog.askopenfilename(title="Select Subtitle to Preview", filetypes=filetypes)

        if not file_path or not Path(file_path).exists():
            return

        try:
            from core.subtitle_formats import SubtitleFormatFactory
            from core.encoding_detection import EncodingDetector

            # Detect encoding and parse file
            encoding = EncodingDetector.detect_encoding(Path(file_path)) or "Unknown"
            sub_file = SubtitleFormatFactory.parse_file(Path(file_path))

            # Create preview window
            preview_win = tk.Toplevel(self.root)
            preview_win.title(f"Preview: {Path(file_path).name}")
            preview_win.geometry("700x500")
            preview_win.transient(self.root)

            # Info header
            info_frame = ttk.Frame(preview_win, padding="10")
            info_frame.pack(fill=tk.X)

            ttk.Label(info_frame, text=f"File: {Path(file_path).name}",
                     font=('TkDefaultFont', 10, 'bold')).pack(anchor='w')
            ttk.Label(info_frame, text=f"Events: {len(sub_file.events)} | "
                     f"Encoding: {encoding.upper()} | "
                     f"Format: {sub_file.format.value.upper()}",
                     style='Subtitle.TLabel').pack(anchor='w')

            # Separator
            ttk.Separator(preview_win, orient='horizontal').pack(fill=tk.X, pady=5)

            # Preview text area
            text_frame = ttk.Frame(preview_win, padding="10")
            text_frame.pack(fill=tk.BOTH, expand=True)

            preview_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD,
                                                     font=('Consolas', 10))
            preview_text.pack(fill=tk.BOTH, expand=True)

            # Display subtitle content (first 50 events for performance)
            preview_content = []
            max_events = min(50, len(sub_file.events))

            for i, event in enumerate(sub_file.events[:max_events]):
                # Format timestamp
                start_h = int(event.start // 3600)
                start_m = int((event.start % 3600) // 60)
                start_s = event.start % 60
                end_h = int(event.end // 3600)
                end_m = int((event.end % 3600) // 60)
                end_s = event.end % 60

                timestamp = f"{start_h:02d}:{start_m:02d}:{start_s:06.3f} --> {end_h:02d}:{end_m:02d}:{end_s:06.3f}"
                preview_content.append(f"[{i+1}] {timestamp}")
                preview_content.append(event.text)
                preview_content.append("")

            if len(sub_file.events) > max_events:
                preview_content.append(f"... ({len(sub_file.events) - max_events} more events not shown)")

            preview_text.insert(tk.END, "\n".join(preview_content))
            preview_text.config(state='disabled')

            # Close button
            ttk.Button(preview_win, text="Close",
                      command=preview_win.destroy).pack(pady=10)

        except Exception as e:
            messagebox.showerror("Preview Error", f"Could not preview file:\n{e}")

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for GUI."""
    app = BISSGui()
    app.run()


if __name__ == '__main__':
    main()
