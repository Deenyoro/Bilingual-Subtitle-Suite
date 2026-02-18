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
        tools_menu.add_command(label="Extract Tracks", command=lambda: self.notebook.select(1))
        tools_menu.add_command(label="Shift Timing", command=lambda: self.notebook.select(2))
        tools_menu.add_command(label="Convert Encoding", command=lambda: self.notebook.select(3))
        tools_menu.add_separator()
        tools_menu.add_command(label="Batch Operations", command=lambda: self.notebook.select(4))

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
        self._create_extract_tab()
        self._create_split_tab()
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
        ttk.Label(intro_frame, text="Combine subtitles from video tracks and/or external files",
                 style='Subtitle.TLabel').pack(anchor='w')

        # === Video File (Optional) ===
        video_frame = ttk.LabelFrame(tab, text="Video File (optional - for embedded subtitles)", padding="10")
        video_frame.pack(fill=tk.X, pady=(0, 10))

        v_row = ttk.Frame(video_frame)
        v_row.pack(fill=tk.X)
        self.merge_video_var = tk.StringVar()
        self.merge_video_var.trace('w', lambda *args: self._on_video_changed())
        ttk.Entry(v_row, textvariable=self.merge_video_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(v_row, text="Browse...", command=self._browse_merge_video).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(v_row, text="Scan Tracks", command=self._scan_video_tracks).pack(side=tk.LEFT, padx=(5, 0))

        # Embedded tracks display
        self.tracks_frame = ttk.Frame(video_frame)
        self.tracks_frame.pack(fill=tk.X, pady=(5, 0))
        self.tracks_label = ttk.Label(self.tracks_frame, text="No video selected", style='Subtitle.TLabel')
        self.tracks_label.pack(anchor='w')

        # Store scanned tracks
        self.scanned_tracks = []
        self.external_subs_found = []

        # Languages for auto-detect dropdown
        self.language_options = ['Any', 'Chinese', 'Japanese', 'Korean', 'English', 'Spanish', 'French', 'German', 'Other']

        # === Track 1 (Top Subtitle) ===
        track1_frame = ttk.LabelFrame(tab, text="Track 1 (Top Subtitle)", padding="10")
        track1_frame.pack(fill=tk.X, pady=(0, 10))

        # Source selection row
        t1_source_row = ttk.Frame(track1_frame)
        t1_source_row.pack(fill=tk.X, pady=(0, 5))

        self.chinese_source_var = tk.StringVar(value="auto")
        ttk.Radiobutton(t1_source_row, text="Auto-detect", variable=self.chinese_source_var,
                       value="auto", command=self._update_chinese_source).pack(side=tk.LEFT)
        ttk.Radiobutton(t1_source_row, text="Embedded track", variable=self.chinese_source_var,
                       value="embedded", command=self._update_chinese_source).pack(side=tk.LEFT, padx=(15, 0))
        ttk.Radiobutton(t1_source_row, text="External file", variable=self.chinese_source_var,
                       value="external", command=self._update_chinese_source).pack(side=tk.LEFT, padx=(15, 0))

        # Auto-detect language selector (shown when auto is selected)
        self.chinese_auto_frame = ttk.Frame(track1_frame)
        ttk.Label(self.chinese_auto_frame, text="Look for:").pack(side=tk.LEFT)
        self.chinese_auto_lang_var = tk.StringVar(value="Chinese")
        ttk.Combobox(self.chinese_auto_frame, textvariable=self.chinese_auto_lang_var,
                    values=self.language_options, width=12, state='readonly').pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(self.chinese_auto_frame, text="(will search video tracks and external files)",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(10, 0))

        # Embedded track selector (hidden by default)
        self.chinese_track_frame = ttk.Frame(track1_frame)
        ttk.Label(self.chinese_track_frame, text="Track:").pack(side=tk.LEFT)
        self.chinese_track_var = tk.StringVar()
        self.chinese_track_combo = ttk.Combobox(self.chinese_track_frame, textvariable=self.chinese_track_var,
                                                 width=45, state='readonly')
        self.chinese_track_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(self.chinese_track_frame, text="Preview",
                  command=lambda: self._preview_embedded_track('chinese')).pack(side=tk.LEFT, padx=(5, 0))

        # External file input
        self.chinese_file_frame = ttk.Frame(track1_frame)
        ttk.Label(self.chinese_file_frame, text="File:").pack(side=tk.LEFT)
        self.chinese_file_var = tk.StringVar()
        self.chinese_file_var.trace('w', lambda *args: self._on_chinese_file_changed())
        ttk.Entry(self.chinese_file_frame, textvariable=self.chinese_file_var, width=40).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(self.chinese_file_frame, text="Browse...", command=lambda: self._browse_sub_file('chinese')).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(self.chinese_file_frame, text="Preview",
                  command=lambda: self._show_subtitle_preview(self.chinese_file_var.get())).pack(side=tk.LEFT, padx=(5, 0))
        self.chinese_lang_label = ttk.Label(self.chinese_file_frame, text="", foreground='#1E90FF', font=('TkDefaultFont', 9, 'bold'))
        self.chinese_lang_label.pack(side=tk.LEFT, padx=(5, 0))

        # === Track 2 (Bottom Subtitle) ===
        track2_frame = ttk.LabelFrame(tab, text="Track 2 (Bottom Subtitle)", padding="10")
        track2_frame.pack(fill=tk.X, pady=(0, 10))

        # Source selection row
        t2_source_row = ttk.Frame(track2_frame)
        t2_source_row.pack(fill=tk.X, pady=(0, 5))

        self.english_source_var = tk.StringVar(value="auto")
        ttk.Radiobutton(t2_source_row, text="Auto-detect", variable=self.english_source_var,
                       value="auto", command=self._update_english_source).pack(side=tk.LEFT)
        ttk.Radiobutton(t2_source_row, text="Embedded track", variable=self.english_source_var,
                       value="embedded", command=self._update_english_source).pack(side=tk.LEFT, padx=(15, 0))
        ttk.Radiobutton(t2_source_row, text="External file", variable=self.english_source_var,
                       value="external", command=self._update_english_source).pack(side=tk.LEFT, padx=(15, 0))

        # Auto-detect language selector (shown when auto is selected)
        self.english_auto_frame = ttk.Frame(track2_frame)
        ttk.Label(self.english_auto_frame, text="Look for:").pack(side=tk.LEFT)
        self.english_auto_lang_var = tk.StringVar(value="English")
        ttk.Combobox(self.english_auto_frame, textvariable=self.english_auto_lang_var,
                    values=self.language_options, width=12, state='readonly').pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(self.english_auto_frame, text="(will search video tracks and external files)",
                 style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(10, 0))

        # Embedded track selector (hidden by default)
        self.english_track_frame = ttk.Frame(track2_frame)
        ttk.Label(self.english_track_frame, text="Track:").pack(side=tk.LEFT)
        self.english_track_var = tk.StringVar()
        self.english_track_combo = ttk.Combobox(self.english_track_frame, textvariable=self.english_track_var,
                                                 width=45, state='readonly')
        self.english_track_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(self.english_track_frame, text="Preview",
                  command=lambda: self._preview_embedded_track('english')).pack(side=tk.LEFT, padx=(5, 0))

        # External file input
        self.english_file_frame = ttk.Frame(track2_frame)
        ttk.Label(self.english_file_frame, text="File:").pack(side=tk.LEFT)
        self.english_file_var = tk.StringVar()
        self.english_file_var.trace('w', lambda *args: self._on_english_file_changed())
        ttk.Entry(self.english_file_frame, textvariable=self.english_file_var, width=40).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(self.english_file_frame, text="Browse...", command=lambda: self._browse_sub_file('english')).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(self.english_file_frame, text="Preview",
                  command=lambda: self._show_subtitle_preview(self.english_file_var.get())).pack(side=tk.LEFT, padx=(5, 0))
        self.english_lang_label = ttk.Label(self.english_file_frame, text="", foreground='#1E90FF', font=('TkDefaultFont', 9, 'bold'))
        self.english_lang_label.pack(side=tk.LEFT, padx=(5, 0))

        # === Options Frame ===
        options_frame = ttk.LabelFrame(tab, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 0: Track order
        row0 = ttk.Frame(options_frame)
        row0.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(row0, text="Display order:").pack(side=tk.LEFT)
        self.merge_top_var = tk.StringVar(value="first")
        ttk.Radiobutton(row0, text="Track 1 on top", variable=self.merge_top_var,
                       value="first").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Radiobutton(row0, text="Track 2 on top", variable=self.merge_top_var,
                       value="second").pack(side=tk.LEFT, padx=(10, 0))

        ttk.Button(row0, text="Swap Tracks", command=self._swap_merge_files,
                  width=12).pack(side=tk.LEFT, padx=(20, 0))

        # Row 1: Alignment options
        row1 = ttk.Frame(options_frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        self.merge_autoalign_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Auto-align (names, numbers, similarity)",
                       variable=self.merge_autoalign_var).pack(side=tk.LEFT)

        self.merge_translation_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Use translation API",
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

        # Progress indicator (determinate mode for real progress)
        self.merge_progress = ttk.Progressbar(btn_frame, mode='determinate', length=200, maximum=100)
        self.merge_progress_label = ttk.Label(btn_frame, text="", style='Subtitle.TLabel')

        # Initialize source displays
        self._update_chinese_source()
        self._update_english_source()

    def _create_extract_tab(self):
        """Create the Extract Tracks tab for mkvextract."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Extract Tracks  ")

        # Intro
        ttk.Label(tab, text="Extract subtitle tracks from MKV files using mkvextract (fast)",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # File selection
        file_frame = ttk.LabelFrame(tab, text="MKV Video File", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        self.extract_file_var = tk.StringVar()
        ttk.Entry(file_row, textvariable=self.extract_file_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="Browse...", command=self._browse_extract_file).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(file_row, text="Load Tracks", command=self._load_extract_tracks).pack(side=tk.LEFT, padx=(5, 0))

        # Track list
        tracks_frame = ttk.LabelFrame(tab, text="Subtitle Tracks", padding="10")
        tracks_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Treeview for tracks
        columns = ('id', 'language', 'codec', 'name')
        self.extract_tree = ttk.Treeview(tracks_frame, columns=columns, show='headings', height=8,
                                         selectmode='extended')
        self.extract_tree.heading('id', text='ID')
        self.extract_tree.heading('language', text='Language')
        self.extract_tree.heading('codec', text='Codec')
        self.extract_tree.heading('name', text='Name')

        self.extract_tree.column('id', width=40, anchor='center')
        self.extract_tree.column('language', width=80, anchor='center')
        self.extract_tree.column('codec', width=120, anchor='w')
        self.extract_tree.column('name', width=200, anchor='w')

        # Scrollbar
        scrollbar = ttk.Scrollbar(tracks_frame, orient=tk.VERTICAL, command=self.extract_tree.yview)
        self.extract_tree.configure(yscrollcommand=scrollbar.set)

        self.extract_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Output options
        output_frame = ttk.LabelFrame(tab, text="Output Options", padding="10")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        out_row = ttk.Frame(output_frame)
        out_row.pack(fill=tk.X)
        ttk.Label(out_row, text="Output Directory:").pack(side=tk.LEFT)
        self.extract_output_var = tk.StringVar()
        ttk.Entry(out_row, textvariable=self.extract_output_var, width=45).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(out_row, text="Browse...", command=self._browse_extract_output).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(out_row, text="(empty = same as video)", style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(5, 0))

        # Action buttons
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(btn_frame, text="Select All", command=self._extract_select_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Select None", command=self._extract_select_none).pack(side=tk.LEFT, padx=(0, 5))

        self.extract_btn = ttk.Button(btn_frame, text="Extract Selected",
                                      command=self._execute_extract, style='Big.TButton')
        self.extract_btn.pack(side=tk.RIGHT)

        # Progress indicator
        self.extract_progress = ttk.Progressbar(btn_frame, mode='indeterminate', length=150)
        self.extract_progress_label = ttk.Label(btn_frame, text="", style='Subtitle.TLabel')

        # Store tracks data
        self._extract_tracks = []

    def _browse_extract_file(self):
        """Browse for MKV file to extract from."""
        filename = filedialog.askopenfilename(
            title="Select MKV Video",
            filetypes=[("MKV files", "*.mkv"), ("All files", "*.*")]
        )
        if filename:
            self.extract_file_var.set(filename)
            self._load_extract_tracks()

    def _browse_extract_output(self):
        """Browse for output directory."""
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.extract_output_var.set(dirname)

    def _check_mkvtoolnix_available(self) -> tuple:
        """Check if MKVToolNix tools are available.

        Returns:
            (available, missing_tools) tuple
        """
        import subprocess
        missing = []
        for tool in ['mkvextract', 'mkvinfo']:
            try:
                result = subprocess.run([tool, '--version'],
                                       capture_output=True, timeout=5)
                if result.returncode != 0:
                    missing.append(tool)
            except (subprocess.SubprocessError, FileNotFoundError):
                missing.append(tool)
        return (len(missing) == 0, missing)

    def _show_mkvtoolnix_missing_dialog(self):
        """Show dialog about missing MKVToolNix."""
        msg = """MKVToolNix is required for the Extract Tracks feature.

Please install MKVToolNix:

Windows:
  Download from https://mkvtoolnix.download/downloads.html#windows

macOS:
  brew install mkvtoolnix

Linux (Debian/Ubuntu):
  sudo apt install mkvtoolnix

Linux (Fedora):
  sudo dnf install mkvtoolnix

After installation, restart this application."""

        messagebox.showerror("MKVToolNix Not Found", msg)

    def _load_extract_tracks(self):
        """Load tracks from MKV file using mkvinfo."""
        import subprocess
        import re

        # Check if MKVToolNix is available first
        available, missing = self._check_mkvtoolnix_available()
        if not available:
            self._show_mkvtoolnix_missing_dialog()
            return

        video_path = self.extract_file_var.get().strip()
        if not video_path:
            messagebox.showerror("Error", "Please select an MKV file")
            return

        if not video_path.lower().endswith('.mkv'):
            messagebox.showerror("Error", "Only MKV files are supported for extraction")
            return

        # Clear existing tracks
        for item in self.extract_tree.get_children():
            self.extract_tree.delete(item)
        self._extract_tracks = []

        self._set_status("Loading tracks...")

        def load_tracks():
            try:
                # Run mkvinfo
                result = subprocess.run(['mkvinfo', video_path],
                                       capture_output=True, timeout=60)
                output = result.stdout.decode('utf-8', errors='replace')

                tracks = []
                current_track = None

                for line in output.split('\n'):
                    # Track number line
                    match = re.search(r'Track number: \d+ \(track ID for mkvmerge & mkvextract: (\d+)\)', line)
                    if match:
                        if current_track:
                            tracks.append(current_track)
                        current_track = {
                            'id': int(match.group(1)),
                            'type': 'unknown',
                            'language': '',
                            'codec': '',
                            'name': ''
                        }
                        continue

                    if current_track is None:
                        continue

                    # Track type
                    if 'Track type:' in line:
                        if 'video' in line.lower():
                            current_track['type'] = 'video'
                        elif 'audio' in line.lower():
                            current_track['type'] = 'audio'
                        elif 'subtitle' in line.lower():
                            current_track['type'] = 'subtitles'

                    # Language
                    if 'Language (IETF BCP 47):' in line:
                        match = re.search(r'Language \(IETF BCP 47\): (\S+)', line)
                        if match:
                            current_track['language'] = match.group(1)
                    elif 'Language:' in line and not current_track['language']:
                        match = re.search(r'Language: (\S+)', line)
                        if match:
                            current_track['language'] = match.group(1)

                    # Codec ID
                    if 'Codec ID:' in line:
                        match = re.search(r'Codec ID: (\S+)', line)
                        if match:
                            current_track['codec'] = match.group(1)

                    # Track name
                    if '+ Name:' in line:
                        match = re.search(r'\+ Name: (.+)', line)
                        if match:
                            current_track['name'] = match.group(1).strip()

                if current_track:
                    tracks.append(current_track)

                # Filter to subtitle tracks only
                subtitle_tracks = [t for t in tracks if t['type'] == 'subtitles']

                # Update UI in main thread
                def update_ui():
                    self._extract_tracks = subtitle_tracks
                    for track in subtitle_tracks:
                        self.extract_tree.insert('', 'end', values=(
                            track['id'],
                            track['language'],
                            track['codec'],
                            track['name']
                        ))
                    self._set_status(f"Loaded {len(subtitle_tracks)} subtitle tracks")

                self.root.after(0, update_ui)

            except FileNotFoundError:
                self.root.after(0, self._show_mkvtoolnix_missing_dialog)
                self.root.after(0, lambda: self._set_status("Ready"))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: messagebox.showerror("Error",
                    "mkvinfo timed out - the file may be too large or corrupted"))
                self.root.after(0, lambda: self._set_status("Ready"))
            except Exception as e:
                self.root.after(0, lambda err=str(e): messagebox.showerror("Error",
                    f"Failed to load tracks: {err}"))
                self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=load_tracks, daemon=True).start()

    def _extract_select_all(self):
        """Select all tracks in the tree."""
        for item in self.extract_tree.get_children():
            self.extract_tree.selection_add(item)

    def _extract_select_none(self):
        """Deselect all tracks in the tree."""
        self.extract_tree.selection_remove(*self.extract_tree.get_children())

    def _execute_extract(self):
        """Execute extraction of selected tracks."""
        import subprocess

        # Check if MKVToolNix is available
        available, missing = self._check_mkvtoolnix_available()
        if not available:
            self._show_mkvtoolnix_missing_dialog()
            return

        video_path = self.extract_file_var.get().strip()
        if not video_path:
            messagebox.showerror("Error", "Please select an MKV file")
            return

        selected = self.extract_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select tracks to extract")
            return

        output_dir = self.extract_output_var.get().strip()
        if not output_dir:
            output_dir = str(Path(video_path).parent)

        # Build extraction args
        video_stem = Path(video_path).stem
        extract_args = []

        for item in selected:
            values = self.extract_tree.item(item, 'values')
            track_id = values[0]
            lang = values[1] if values[1] else f"track{track_id}"
            codec = values[2].lower()

            # Determine extension
            ext = '.srt' if 's_text' in codec or 'subrip' in codec else '.ass'
            output_file = Path(output_dir) / f"{video_stem}.{lang}.{track_id}{ext}"

            extract_args.append(f"{track_id}:{output_file}")

        # Show progress
        self._set_status("Extracting tracks...")
        self.extract_btn.config(state='disabled')
        self.extract_progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.extract_progress.pack(side=tk.LEFT, padx=(0, 10))
        self.extract_progress.start(10)

        def run_extract():
            try:
                cmd = ['mkvextract', video_path, 'tracks'] + extract_args
                logger.info(f"Running: mkvextract with {len(extract_args)} tracks")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

                if result.returncode == 0:
                    self.root.after(0, lambda: messagebox.showinfo("Success",
                        f"Extracted {len(extract_args)} track(s) successfully!"))
                    for arg in extract_args:
                        track_id, output = arg.split(':', 1)
                        logger.info(f"  Track {track_id} -> {output}")
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error",
                        f"Extraction failed: {result.stderr}"))

            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: messagebox.showerror("Error", "Extraction timed out"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed: {e}"))
            finally:
                self.root.after(0, lambda: self.extract_btn.config(state='normal'))
                self.root.after(0, lambda: self.extract_progress.stop())
                self.root.after(0, lambda: self.extract_progress.pack_forget())
                self.root.after(0, lambda: self.extract_progress_label.pack_forget())
                self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=run_extract, daemon=True).start()

    def _create_split_tab(self):
        """Create the Split Bilingual Subtitles tab."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Split Bilingual  ")

        # Intro
        ttk.Label(tab, text="Split bilingual subtitles into separate language files",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # File selection
        file_frame = ttk.LabelFrame(tab, text="Bilingual Subtitle File", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        self.split_file_var = tk.StringVar()
        self.split_file_var.trace('w', lambda *args: self._on_split_file_changed())
        ttk.Entry(file_row, textvariable=self.split_file_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="Browse...", command=self._browse_split_file).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(file_row, text="Preview",
                  command=lambda: self._show_subtitle_preview(self.split_file_var.get())).pack(side=tk.LEFT, padx=(5, 0))

        # Info panel
        self.split_info_panel = SubtitleInfoPanel(file_frame, "File Info")
        self.split_info_panel.pack(fill=tk.X, pady=(10, 0))

        # Bilingual status label
        self.split_status_var = tk.StringVar(value="Select a bilingual subtitle file")
        self.split_status_label = ttk.Label(file_frame, textvariable=self.split_status_var,
                                            font=('TkDefaultFont', 9, 'italic'))
        self.split_status_label.pack(anchor='w', pady=(5, 0))

        # Options
        options_frame = ttk.LabelFrame(tab, text="Split Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Language labels
        lang_row = ttk.Frame(options_frame)
        lang_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(lang_row, text="CJK language label:").pack(side=tk.LEFT)
        self.split_lang1_var = tk.StringVar(value="zh")
        ttk.Combobox(lang_row, textvariable=self.split_lang1_var, width=8,
                     values=['zh', 'ja', 'ko', 'chi', 'jpn', 'kor']).pack(side=tk.LEFT, padx=(5, 15))
        ttk.Label(lang_row, text="Latin language label:").pack(side=tk.LEFT)
        self.split_lang2_var = tk.StringVar(value="en")
        ttk.Combobox(lang_row, textvariable=self.split_lang2_var, width=8,
                     values=['en', 'eng', 'fr', 'de', 'es']).pack(side=tk.LEFT, padx=(5, 0))

        # CJK output format
        fmt_row = ttk.Frame(options_frame)
        fmt_row.pack(fill=tk.X, pady=(5, 5))
        ttk.Label(fmt_row, text="CJK output format:").pack(side=tk.LEFT)
        self.split_format_var = tk.StringVar(value="ass")
        ttk.Radiobutton(fmt_row, text="ASS (recommended - embeds CJK font)",
                       variable=self.split_format_var, value="ass").pack(side=tk.LEFT, padx=(5, 10))
        ttk.Radiobutton(fmt_row, text="SRT (plain text, no font info)",
                       variable=self.split_format_var, value="srt").pack(side=tk.LEFT)

        # Strip formatting
        self.split_strip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Strip HTML formatting tags (<i>, <b>, etc.)",
                       variable=self.split_strip_var).pack(anchor='w')

        # Output directory
        out_frame = ttk.LabelFrame(tab, text="Output Directory (optional)", padding="10")
        out_frame.pack(fill=tk.X, pady=(0, 10))

        out_row = ttk.Frame(out_frame)
        out_row.pack(fill=tk.X)
        self.split_output_dir_var = tk.StringVar()
        ttk.Entry(out_row, textvariable=self.split_output_dir_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(out_row, text="Browse...", command=self._browse_split_output_dir).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(out_frame, text="Leave empty to save alongside input file",
                 font=('TkDefaultFont', 8)).pack(anchor='w', pady=(3, 0))

        # Execute button
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.split_btn = ttk.Button(btn_frame, text="Split Subtitle", command=self._execute_split,
                                     style='Big.TButton')
        self.split_btn.pack(side=tk.RIGHT)

    def _browse_split_file(self):
        """Browse for a subtitle file to split."""
        file_path = filedialog.askopenfilename(
            title="Select Bilingual Subtitle",
            filetypes=[
                ("Subtitle Files", "*.srt *.ass *.ssa *.vtt"),
                ("SRT Files", "*.srt"),
                ("ASS/SSA Files", "*.ass *.ssa"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            self.split_file_var.set(file_path)

    def _browse_split_output_dir(self):
        """Browse for output directory for split files."""
        dir_path = filedialog.askdirectory(title="Select Output Directory")
        if dir_path:
            self.split_output_dir_var.set(dir_path)

    def _on_split_file_changed(self):
        """Handle split file selection change."""
        file_path = self.split_file_var.get()
        if file_path and Path(file_path).exists():
            self.split_info_panel.update_info(Path(file_path))

            # Check if bilingual in background
            def check_bilingual():
                try:
                    from processors.splitter import BilingualSplitter
                    splitter = BilingualSplitter()
                    is_bi = splitter.is_bilingual(Path(file_path))
                    if is_bi:
                        self.split_status_var.set("Bilingual content detected - ready to split")
                    else:
                        self.split_status_var.set("Warning: File does not appear to be bilingual")
                except Exception as e:
                    self.split_status_var.set(f"Could not analyze file: {e}")

            threading.Thread(target=check_bilingual, daemon=True).start()
        else:
            self.split_status_var.set("Select a bilingual subtitle file")

    def _execute_split(self):
        """Execute the split operation."""
        file_path = self.split_file_var.get()
        if not file_path:
            messagebox.showwarning("No File", "Please select a subtitle file to split.")
            return

        input_path = Path(file_path)
        if not input_path.exists():
            messagebox.showerror("File Not Found", f"File not found: {file_path}")
            return

        output_dir = None
        if self.split_output_dir_var.get():
            output_dir = Path(self.split_output_dir_var.get())

        lang1 = self.split_lang1_var.get()
        lang2 = self.split_lang2_var.get()
        strip_formatting = self.split_strip_var.get()
        lang1_format = self.split_format_var.get()

        self.split_btn.config(state='disabled')

        def run_split():
            try:
                from processors.splitter import BilingualSplitter

                splitter = BilingualSplitter(strip_formatting=strip_formatting)
                lang1_path, lang2_path = splitter.split_file(
                    input_path=input_path,
                    output_dir=output_dir,
                    lang1_label=lang1,
                    lang2_label=lang2,
                    lang1_format=lang1_format
                )

                results = []
                if lang1_path:
                    results.append(f"{lang1.upper()}: {lang1_path.name}")
                if lang2_path:
                    results.append(f"{lang2.upper()}: {lang2_path.name}")

                if results:
                    msg = "Split complete!\n\n" + "\n".join(results)
                    self.root.after(0, lambda: messagebox.showinfo("Split Complete", msg))
                else:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "No Output", "No bilingual content found to split."))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Split Failed", str(e)))
            finally:
                self.root.after(0, lambda: self.split_btn.config(state='normal'))

        threading.Thread(target=run_split, daemon=True).start()

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
        """Create the Convert/Format tab."""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="  Convert  ")

        # Intro
        ttk.Label(tab, text="Convert subtitle encoding or format (ASS to SRT)",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(0, 10))

        # Conversion type selection
        type_frame = ttk.LabelFrame(tab, text="Conversion Type", padding="10")
        type_frame.pack(fill=tk.X, pady=(0, 10))

        self.convert_type_var = tk.StringVar(value="encoding")
        ttk.Radiobutton(type_frame, text="Encoding conversion (fix garbled characters)",
                       variable=self.convert_type_var, value="encoding",
                       command=self._update_convert_type).pack(anchor='w')
        ttk.Radiobutton(type_frame, text="ASS/SSA to SRT (convert format, preserve bilingual)",
                       variable=self.convert_type_var, value="ass_to_srt",
                       command=self._update_convert_type).pack(anchor='w')

        # File selection
        file_frame = ttk.LabelFrame(tab, text="Subtitle File", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        self.convert_file_var = tk.StringVar()
        self.convert_file_var.trace('w', lambda *args: self._on_convert_file_changed())
        ttk.Entry(file_row, textvariable=self.convert_file_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(file_row, text="Browse...", command=self._browse_convert_file).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(file_row, text="Preview",
                  command=lambda: self._show_subtitle_preview(self.convert_file_var.get())).pack(side=tk.LEFT, padx=(5, 0))

        # Info panel
        self.convert_info_panel = SubtitleInfoPanel(file_frame, "File Info")
        self.convert_info_panel.pack(fill=tk.X, pady=(10, 0))

        # === Encoding conversion options (shown by default) ===
        self.encoding_options_frame = ttk.LabelFrame(tab, text="Encoding Options", padding="10")
        self.encoding_options_frame.pack(fill=tk.X, pady=(0, 10))

        # Encoding detection display
        detect_row = ttk.Frame(self.encoding_options_frame)
        detect_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(detect_row, text="Detected encoding:").pack(side=tk.LEFT)
        self.detected_encoding_var = tk.StringVar(value="Select a file")
        self.encoding_label = ttk.Label(detect_row, textvariable=self.detected_encoding_var,
                                        font=('TkDefaultFont', 10, 'bold'), foreground='#1E90FF')
        self.encoding_label.pack(side=tk.LEFT, padx=(5, 0))

        enc_frame = ttk.Frame(self.encoding_options_frame)
        enc_frame.pack(fill=tk.X, pady=(5, 5))
        ttk.Label(enc_frame, text="Target encoding:").pack(side=tk.LEFT)
        self.convert_encoding_var = tk.StringVar(value="utf-8")
        enc_combo = ttk.Combobox(enc_frame, textvariable=self.convert_encoding_var, width=15,
                                values=['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'big5', 'shift-jis'])
        enc_combo.pack(side=tk.LEFT, padx=(5, 0))

        self.convert_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.encoding_options_frame, text="Create backup of original file",
                       variable=self.convert_backup_var).pack(anchor='w')

        self.convert_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.encoding_options_frame, text="Force conversion even if already target encoding",
                       variable=self.convert_force_var).pack(anchor='w')

        # === ASS to SRT options (hidden by default) ===
        self.ass_options_frame = ttk.LabelFrame(tab, text="ASS to SRT Options", padding="10")

        self.ass_bilingual_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text="Preserve bilingual structure (CJK on top, English below)",
                       variable=self.ass_bilingual_var).pack(anchor='w')

        self.ass_strip_effects_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.ass_options_frame, text="Remove ASS formatting effects",
                       variable=self.ass_strip_effects_var).pack(anchor='w')

        # Output path for ASS conversion
        out_row = ttk.Frame(self.ass_options_frame)
        out_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(out_row, text="Output file:").pack(side=tk.LEFT)
        self.ass_output_var = tk.StringVar()
        ttk.Entry(out_row, textvariable=self.ass_output_var, width=45).pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(out_row, text="Browse...", command=self._browse_ass_output).pack(side=tk.LEFT, padx=(5, 0))

        # Execute button
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.convert_btn = ttk.Button(btn_frame, text="Convert Encoding", command=self._execute_convert,
                                      style='Big.TButton')
        self.convert_btn.pack(side=tk.RIGHT)

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

            # Auto-set output path for ASS conversion
            if path.lower().endswith(('.ass', '.ssa')):
                self.ass_output_var.set(str(Path(path).with_suffix('.srt')))
        else:
            self.convert_info_panel.update_info(None)
            self.detected_encoding_var.set("Select a file")

    def _update_convert_type(self):
        """Update UI based on conversion type selection."""
        conv_type = self.convert_type_var.get()

        if conv_type == "encoding":
            self.ass_options_frame.pack_forget()
            self.encoding_options_frame.pack(fill=tk.X, pady=(0, 10))
            self.convert_btn.config(text="Convert Encoding", command=self._execute_convert)
        else:  # ass_to_srt
            self.encoding_options_frame.pack_forget()
            self.ass_options_frame.pack(fill=tk.X, pady=(0, 10))
            self.convert_btn.config(text="Convert ASS to SRT", command=self._execute_ass_convert)

    def _browse_ass_output(self):
        """Browse for ASS conversion output file."""
        initial_file = self.ass_output_var.get()
        if initial_file:
            initial_dir = str(Path(initial_file).parent)
            initial_name = Path(initial_file).name
        else:
            initial_dir = ""
            initial_name = ""

        file_path = filedialog.asksaveasfilename(
            title="Save SRT file as",
            initialdir=initial_dir,
            initialfile=initial_name,
            defaultextension=".srt",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )

        if file_path:
            self.ass_output_var.set(file_path)

    def _execute_ass_convert(self):
        """Execute ASS to SRT conversion."""
        input_path = self.convert_file_var.get().strip()
        output_path = self.ass_output_var.get().strip()

        if not input_path:
            messagebox.showerror("Error", "Please select an ASS/SSA file to convert")
            return

        if not Path(input_path).exists():
            messagebox.showerror("Error", f"File not found: {input_path}")
            return

        if not input_path.lower().endswith(('.ass', '.ssa')):
            messagebox.showerror("Error", "Selected file is not an ASS/SSA file")
            return

        if not output_path:
            output_path = str(Path(input_path).with_suffix('.srt'))

        self._set_status("Converting ASS to SRT...")
        self.convert_btn.config(state='disabled')

        def do_convert():
            try:
                from core.ass_converter import ASSToSRTConverter

                converter = ASSToSRTConverter(
                    strip_effects=self.ass_strip_effects_var.get(),
                    preserve_bilingual=self.ass_bilingual_var.get()
                )

                result_path = converter.convert_file(Path(input_path), Path(output_path))

                self.root.after(0, lambda: messagebox.showinfo("Success",
                    f"Converted successfully!\n\nOutput: {result_path.name}"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error",
                    f"Conversion failed: {e}"))
            finally:
                self.root.after(0, lambda: self.convert_btn.config(state='normal'))
                self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=do_convert, daemon=True).start()

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
        """Swap all settings between Track 1 and Track 2."""
        # Swap source type
        source1 = self.chinese_source_var.get()
        source2 = self.english_source_var.get()
        self.chinese_source_var.set(source2)
        self.english_source_var.set(source1)

        # Swap auto-detect language preference
        lang1 = self.chinese_auto_lang_var.get()
        lang2 = self.english_auto_lang_var.get()
        self.chinese_auto_lang_var.set(lang2)
        self.english_auto_lang_var.set(lang1)

        # Swap embedded track selection
        track1 = self.chinese_track_var.get()
        track2 = self.english_track_var.get()
        self.chinese_track_var.set(track2)
        self.english_track_var.set(track1)

        # Swap external file paths
        file1 = self.chinese_file_var.get()
        file2 = self.english_file_var.get()
        self.chinese_file_var.set(file2)
        self.english_file_var.set(file1)

        # Update UI to reflect changes
        self._update_chinese_source()
        self._update_english_source()

    def _update_shift_mode(self):
        """Update UI based on shift mode selection."""
        if self.shift_mode_var.get() == "offset":
            self.firstline_frame.pack_forget()
            self.offset_frame.pack(fill=tk.X, pady=(0, 5))
        else:
            self.offset_frame.pack_forget()
            self.firstline_frame.pack(fill=tk.X, pady=(0, 5))

    def _update_chinese_source(self):
        """Update Track 1 subtitle source UI."""
        source = self.chinese_source_var.get()
        self.chinese_auto_frame.pack_forget()
        self.chinese_track_frame.pack_forget()
        self.chinese_file_frame.pack_forget()

        if source == "auto":
            self.chinese_auto_frame.pack(fill=tk.X, pady=(5, 0))
        elif source == "embedded":
            self.chinese_track_frame.pack(fill=tk.X, pady=(5, 0))
        elif source == "external":
            self.chinese_file_frame.pack(fill=tk.X, pady=(5, 0))

    def _update_english_source(self):
        """Update Track 2 subtitle source UI."""
        source = self.english_source_var.get()
        self.english_auto_frame.pack_forget()
        self.english_track_frame.pack_forget()
        self.english_file_frame.pack_forget()

        if source == "auto":
            self.english_auto_frame.pack(fill=tk.X, pady=(5, 0))
        elif source == "embedded":
            self.english_track_frame.pack(fill=tk.X, pady=(5, 0))
        elif source == "external":
            self.english_file_frame.pack(fill=tk.X, pady=(5, 0))

    def _on_video_changed(self):
        """Handle video file selection change - auto-scan tracks."""
        video_path = self.merge_video_var.get().strip()
        if video_path and Path(video_path).exists():
            # Auto-scan for external subtitles
            self._find_external_subs(Path(video_path))
            # Auto-scan embedded tracks
            self._scan_video_tracks()

    def _find_external_subs(self, video_path: Path):
        """Find external subtitle files next to the video."""
        self.external_subs_found = []
        video_dir = video_path.parent
        video_stem = video_path.stem

        # Look for subtitle files with similar names
        for ext in ['.srt', '.ass', '.ssa', '.vtt']:
            for sub_file in video_dir.glob(f"{video_stem}*{ext}"):
                if sub_file.is_file():
                    self.external_subs_found.append(sub_file)

        # Update UI to show found subs
        if self.external_subs_found:
            sub_names = [f.name for f in self.external_subs_found[:5]]  # Show first 5
            more = f" (+{len(self.external_subs_found) - 5} more)" if len(self.external_subs_found) > 5 else ""
            self.tracks_label.config(text=f"External subs found: {', '.join(sub_names)}{more}")

    def _scan_video_tracks(self):
        """Scan video for embedded subtitle tracks."""
        video_path = self.merge_video_var.get().strip()
        if not video_path:
            messagebox.showerror("Error", "Please select a video file first")
            return

        if not Path(video_path).exists():
            messagebox.showerror("Error", f"File not found: {video_path}")
            return

        self._set_status("Scanning video tracks...")

        def do_scan():
            try:
                from core.video_containers import VideoContainerHandler
                handler = VideoContainerHandler()
                tracks = handler.list_subtitle_tracks(Path(video_path))

                self.scanned_tracks = tracks

                # Build track list for comboboxes
                track_options = []
                chinese_tracks = []
                english_tracks = []

                for t in tracks:
                    lang = t.language or 'Unknown'
                    title = f" - {t.title}" if t.title else ""
                    label = f"Track {t.track_id}: {lang}{title} ({t.codec})"
                    track_options.append((t.track_id, label, lang.lower()))

                    # Categorize by language
                    lang_lower = lang.lower()
                    if any(c in lang_lower for c in ['chi', 'zh', 'cn', 'jpn', 'ja', 'kor', 'ko']):
                        chinese_tracks.append((t.track_id, label))
                    elif any(c in lang_lower for c in ['eng', 'en']):
                        english_tracks.append((t.track_id, label))

                def update_ui():
                    # Update comboboxes
                    all_labels = [opt[1] for opt in track_options]
                    self.chinese_track_combo['values'] = all_labels
                    self.english_track_combo['values'] = all_labels

                    # Auto-select likely tracks
                    if chinese_tracks:
                        self.chinese_track_var.set(chinese_tracks[0][1])
                    elif all_labels:
                        self.chinese_track_var.set(all_labels[0])

                    if english_tracks:
                        self.english_track_var.set(english_tracks[0][1])
                    elif len(all_labels) > 1:
                        self.english_track_var.set(all_labels[1])
                    elif all_labels:
                        self.english_track_var.set(all_labels[0])

                    # Update status
                    if tracks:
                        track_summary = f"Found {len(tracks)} embedded track(s)"
                        if self.external_subs_found:
                            track_summary += f", {len(self.external_subs_found)} external file(s)"
                        self.tracks_label.config(text=track_summary)
                    else:
                        self.tracks_label.config(text="No embedded subtitle tracks found")

                    self._set_status("Ready")

                self.root.after(0, update_ui)

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to scan tracks: {e}"))
                self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=do_scan, daemon=True).start()

    def _browse_sub_file(self, lang_type: str):
        """Browse for subtitle file for Chinese or English."""
        filetypes = [("Subtitle files", "*.srt *.ass *.ssa *.vtt"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title=f"Select {lang_type.title()} Subtitle", filetypes=filetypes)
        if path:
            if lang_type == 'chinese':
                self.chinese_file_var.set(path)
            else:
                self.english_file_var.set(path)

    def _on_chinese_file_changed(self):
        """Update language label when Track 1 file changes."""
        path = self.chinese_file_var.get().strip()
        if path and Path(path).exists():
            lang = self._detect_file_language(Path(path))
            self.chinese_lang_label.config(text=f"[{lang}]" if lang else "")
        else:
            self.chinese_lang_label.config(text="")

    def _on_english_file_changed(self):
        """Update language label when Track 2 file changes."""
        path = self.english_file_var.get().strip()
        if path and Path(path).exists():
            lang = self._detect_file_language(Path(path))
            self.english_lang_label.config(text=f"[{lang}]" if lang else "")
        else:
            self.english_lang_label.config(text="")

    def _preview_embedded_track(self, track_type: str):
        """Preview an embedded subtitle track by extracting and showing it."""
        video_path = self.merge_video_var.get().strip()
        if not video_path or not Path(video_path).exists():
            messagebox.showerror("Error", "Please select a video file first")
            return

        if track_type == 'chinese':
            track_label = self.chinese_track_var.get()
        else:
            track_label = self.english_track_var.get()

        if not track_label:
            messagebox.showerror("Error", "Please select a track first")
            return

        # Extract track ID from label "Track X: ..."
        try:
            track_id = track_label.split(":")[0].replace("Track", "").strip()
        except:
            messagebox.showerror("Error", "Could not parse track ID")
            return

        self._set_status(f"Extracting track {track_id} for preview...")

        def do_extract():
            try:
                import tempfile
                from core.video_containers import VideoContainerHandler

                handler = VideoContainerHandler()
                with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                # Extract the track
                success = handler.extract_subtitle_track(
                    video_path=Path(video_path),
                    track_id=track_id,
                    output_path=tmp_path
                )

                if success and tmp_path.exists():
                    self.root.after(0, lambda: self._show_subtitle_preview(str(tmp_path)))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Failed to extract track"))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Preview failed: {e}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=do_extract, daemon=True).start()

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
            # Auto-detect language and assign to appropriate field
            lang = self._detect_file_language(Path(path))
            if lang in ['Chinese', 'Japanese', 'Korean']:
                self.chinese_file_var.set(path)
                self.chinese_source_var.set("external")
                self._update_chinese_source()
            else:
                self.english_file_var.set(path)
                self.english_source_var.set("external")
                self._update_english_source()
            self.notebook.select(0)

    def _open_video(self):
        """Open video file from menu."""
        filetypes = [("Video files", "*.mkv *.mp4 *.avi *.mov *.webm"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Open Video File", filetypes=filetypes)
        if path:
            self.merge_video_var.set(path)
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
        """Execute the merge operation with flexible source selection."""
        video_path = self.merge_video_var.get().strip()
        chinese_source = self.chinese_source_var.get()
        english_source = self.english_source_var.get()

        # Resolve Track 1 subtitle source
        chinese_path = None
        chinese_track = None

        if chinese_source == "external":
            chinese_path = self.chinese_file_var.get().strip()
            if not chinese_path:
                messagebox.showerror("Error", "Please select a subtitle file for Track 1")
                return
            if not Path(chinese_path).exists():
                messagebox.showerror("Error", f"Track 1 subtitle not found: {chinese_path}")
                return
            chinese_path = Path(chinese_path)
        elif chinese_source == "embedded":
            if not video_path:
                messagebox.showerror("Error", "Please select a video file to use embedded tracks")
                return
            track_label = self.chinese_track_var.get()
            if track_label:
                # Extract track ID from label "Track X: ..."
                try:
                    chinese_track = track_label.split(":")[0].replace("Track", "").strip()
                except:
                    pass

        # Resolve Track 2 subtitle source
        english_path = None
        english_track = None

        if english_source == "external":
            english_path = self.english_file_var.get().strip()
            if not english_path:
                messagebox.showerror("Error", "Please select a subtitle file for Track 2")
                return
            if not Path(english_path).exists():
                messagebox.showerror("Error", f"Track 2 subtitle not found: {english_path}")
                return
            english_path = Path(english_path)
        elif english_source == "embedded":
            if not video_path:
                messagebox.showerror("Error", "Please select a video file to use embedded tracks")
                return
            track_label = self.english_track_var.get()
            if track_label:
                try:
                    english_track = track_label.split(":")[0].replace("Track", "").strip()
                except:
                    pass

        # Validate we have at least one source specified if not auto
        if chinese_source == "auto" and english_source == "auto":
            if not video_path and not chinese_path and not english_path:
                messagebox.showerror("Error", "Please select a video file or specify subtitle sources")
                return

        # Validate video exists if needed
        if video_path and not Path(video_path).exists():
            messagebox.showerror("Error", f"Video file not found: {video_path}")
            return

        output_path = self.merge_output_var.get().strip() or None
        auto_align = self.merge_autoalign_var.get()
        use_translation = self.merge_translation_var.get()
        threshold = float(self.merge_threshold_var.get() or 0.8)
        output_format = self.merge_format_var.get()
        top_language = self.merge_top_var.get()

        def update_progress(step_name: str, current: int, total: int):
            """Update progress bar and label from merger callback."""
            if total > 0:
                percent = int((current / total) * 100)
                self.root.after(0, lambda: self.merge_progress.configure(value=percent))
            self.root.after(0, lambda s=step_name: self.merge_progress_label.configure(text=s))
            self.root.after(0, lambda s=step_name: self._set_status(f"Merging: {s}"))

        def run_merge():
            try:
                logger.info(f"Starting merge operation for: {video_path or 'external files'}")
                from processors.merger import BilingualMerger

                merger = BilingualMerger(
                    auto_align=auto_align,
                    use_translation=use_translation,
                    alignment_threshold=threshold,
                    top_language=top_language,
                    progress_callback=update_progress
                )

                # Determine merge approach based on sources
                if video_path and (chinese_source != "external" or english_source != "external"):
                    # Use video processing with optional external overrides
                    success = merger.process_video(
                        video_path=Path(video_path),
                        chinese_sub=chinese_path,
                        english_sub=english_path,
                        output_format=output_format,
                        output_path=Path(output_path) if output_path else None,
                        chinese_track=chinese_track,
                        english_track=english_track
                    )
                elif chinese_path and english_path:
                    # Direct file merge (both external)
                    update_progress("Merging subtitles", 1, 2)
                    success = merger.merge_subtitle_files(
                        chinese_path=chinese_path,
                        english_path=english_path,
                        output_path=Path(output_path) if output_path else None,
                        output_format=output_format
                    )
                    if success:
                        update_progress("Complete", 2, 2)
                elif chinese_path or english_path:
                    # One external file - need video for the other
                    if not video_path:
                        self.root.after(0, lambda: messagebox.showerror("Error",
                            "Need video file to extract missing subtitle track"))
                        return

                    success = merger.process_video(
                        video_path=Path(video_path),
                        chinese_sub=chinese_path,
                        english_sub=english_path,
                        output_format=output_format,
                        output_path=Path(output_path) if output_path else None
                    )
                else:
                    # Full auto - use video
                    if not video_path:
                        self.root.after(0, lambda: messagebox.showerror("Error",
                            "Please select a video or subtitle files"))
                        return

                    success = merger.process_video(
                        video_path=Path(video_path),
                        output_format=output_format,
                        output_path=Path(output_path) if output_path else None
                    )

                if success:
                    self.root.after(0, lambda: messagebox.showinfo("Success", "Subtitles merged successfully!"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Merge failed - check log for details"))

            except Exception as e:
                logger.error(f"Merge failed with exception: {e}", exc_info=True)
                self.root.after(0, lambda err=str(e): messagebox.showerror("Error", f"Merge failed: {err}"))
            finally:
                self.root.after(0, lambda: self._set_status("Ready"))

        # Show progress and disable button
        self._set_status("Merging: Starting...")
        self.merge_btn.config(state='disabled')
        self.merge_progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.merge_progress.pack(side=tk.LEFT, padx=(0, 10))
        self.merge_progress.configure(value=0)

        def run_merge_with_cleanup():
            try:
                run_merge()
            finally:
                # Re-enable button and hide progress
                self.root.after(0, lambda: self.merge_btn.config(state='normal'))
                self.root.after(0, lambda: self.merge_progress.pack_forget())
                self.root.after(0, lambda: self.merge_progress_label.pack_forget())
                self.root.after(0, lambda: self.merge_progress.configure(value=0))

        threading.Thread(target=run_merge_with_cleanup, daemon=True).start()

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
