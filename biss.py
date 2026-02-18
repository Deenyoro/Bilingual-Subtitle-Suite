#!/usr/bin/env python3
"""
Bilingual Subtitle Suite - Main Application Entry Point
=======================================================

IMPORTANT: Keep root directory clean - no random test files, temporary scripts, or experimental code
All functionality should be properly organized in core/, processors/, ui/, utils/ subdirectories

A comprehensive tool for processing subtitle files with support for:
- Bilingual subtitle merging (Chinese-English, Japanese-English, Korean-English, etc.)
- Encoding conversion and detection
- Subtitle realignment and timing adjustment
- Video container subtitle extraction
- Batch processing operations

This application consolidates the functionality of multiple subtitle processing
tools into a single, unified interface with both command-line and interactive modes.

Usage:
    # GUI mode (graphical interface)
    biss gui

    # Interactive mode (text menu)
    biss interactive

    # Command-line mode
    biss merge movie.mkv --output bilingual.srt
    biss merge chinese.srt english.srt
    biss shift subtitle.srt --offset="-2.5s"
    biss convert subtitle.srt

    # Help
    biss --help
    biss <command> --help

Author: Dean Thomas (@Deenyoro)
Version: 2.1.0
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional
import io

# Fix Windows console encoding issues with emoji/unicode characters
# This prevents 'charmap' codec errors when printing Unicode characters
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, errors='replace')

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utils.constants import APP_NAME, APP_VERSION, APP_DESCRIPTION
from utils.logging_config import setup_logging
from utils.i18n import set_locale, detect_system_locale, t
from ui.cli import CLIHandler
from ui.interactive import InteractiveInterface
from third_party import is_pgsrip_available


def create_main_parser() -> argparse.ArgumentParser:
    """
    Create the main argument parser.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='biss',
        description=f"{APP_NAME} v{APP_VERSION}\n{APP_DESCRIPTION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch GUI (default when double-clicking biss.exe)
  biss
  biss gui

  # Interactive text menu
  biss interactive

  # Merge subtitles from video
  biss merge movie.mkv --output bilingual.srt

  # Merge two subtitle files
  biss merge --chinese chinese.srt --english english.srt --output merged.srt

  # Convert subtitle encoding
  biss convert subtitle.srt --encoding utf-8 --backup

  # Realign subtitles
  biss realign source.srt reference.srt --output aligned.srt

  # Batch convert directory
  biss batch-convert /media/movies --recursive --parallel

  # Batch merge videos
  biss batch-merge /media/movies --format srt --prefer-external

  # Batch realign subtitle pairs
  biss batch-realign /media --source-ext .zh.srt --reference-ext .en.srt

  # Convert PGS subtitles to SRT
  biss convert-pgs movie.mkv --language chi_sim
  biss batch-convert-pgs /media/movies --recursive

For detailed help on any command:
  biss <command> --help
        """
    )
    
    parser.add_argument('--version', action='version', version=f'{APP_NAME} {APP_VERSION}')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--no-colors', action='store_true', help='Disable colored output')
    parser.add_argument('--lang', choices=['en', 'zh', 'ja', 'ko'], default=None,
                        help='UI language (en=English, zh=Chinese, ja=Japanese, ko=Korean)')
    
    return parser


def main():
    """
    Main application entry point.

    Handles argument parsing and dispatches to appropriate interface
    (GUI, interactive, or command-line) based on the provided arguments.
    """
    # Handle --lang flag globally (before any mode dispatch)
    lang = None
    for i, arg in enumerate(sys.argv):
        if arg == '--lang' and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
            break
        elif arg.startswith('--lang='):
            lang = arg.split('=', 1)[1]
            break
    if lang:
        set_locale(lang)
    else:
        set_locale(detect_system_locale())

    # If no arguments provided, launch GUI mode
    if len(sys.argv) == 1:
        launch_gui_mode()
        return

    # Check for global flags first
    debug_mode = '--debug' in sys.argv
    verbose_mode = '--verbose' in sys.argv or '-v' in sys.argv

    # Check if user wants GUI mode
    if len(sys.argv) >= 2 and sys.argv[1] == 'gui':
        launch_gui_mode()
        return

    # Check if user wants interactive mode (text-based menu)
    if len(sys.argv) >= 2 and sys.argv[1] == 'interactive':
        no_colors = '--no-colors' in sys.argv
        launch_interactive_mode(use_colors=not no_colors)
        return

    # Otherwise, use CLI handler for command processing
    cli_handler = CLIHandler()
    cli_parser = cli_handler.create_parser()

    # Parse all arguments with CLI parser
    try:
        args = cli_parser.parse_args()
        exit_code = cli_handler.handle_command(args)
        sys.exit(exit_code)
    except SystemExit:
        # argparse calls sys.exit() for --help, --version, etc.
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if debug_mode:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _hide_console_window():
    """Hide the console window on Windows when launching GUI from exe.

    Only hides the console if this process is the sole owner (i.e., launched
    by double-clicking the exe, not from an existing terminal session).
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        # Check how many processes share this console
        # If only 1 (ourselves), we own it — safe to hide (double-click launch)
        # If 2+, we're inside a terminal — don't hide
        pids = (ctypes.wintypes.DWORD * 16)()
        count = kernel32.GetConsoleProcessList(pids, 16)
        if count <= 1:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def launch_gui_mode():
    """
    Launch the graphical user interface.
    """
    _hide_console_window()
    try:
        from ui.gui import BISSGui
        app = BISSGui()
        app.run()
    except ImportError as e:
        print(f"GUI dependencies not available: {e}", file=sys.stderr)
        print("Falling back to interactive mode...", file=sys.stderr)
        launch_interactive_mode()
    except Exception as e:
        print(f"Error launching GUI: {e}", file=sys.stderr)
        print("Falling back to interactive mode...", file=sys.stderr)
        launch_interactive_mode()


def launch_interactive_mode(use_colors: bool = True):
    """
    Launch the interactive menu-driven interface.

    Args:
        use_colors: Whether to use colored output
    """
    try:
        interface = InteractiveInterface(use_colors=use_colors)
        exit_code = interface.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"Error in interactive mode: {e}", file=sys.stderr)
        sys.exit(1)


def check_dependencies():
    """
    Check for required and optional dependencies.
    
    Prints warnings for missing optional dependencies that enhance functionality.
    """
    missing_optional = []
    
    # Check for FFmpeg
    import subprocess
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing_optional.append("FFmpeg (required for video processing)")
    
    try:
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing_optional.append("FFprobe (required for video analysis)")
    
    # Check for encoding detection libraries
    try:
        import charset_normalizer
    except ImportError:
        try:
            import chardet
        except ImportError:
            missing_optional.append("charset-normalizer or chardet (for better encoding detection)")
    
    # Check for curses (for enhanced interactive interface)
    try:
        import curses
    except ImportError:
        missing_optional.append("curses (for enhanced interactive interface)")
    
    if missing_optional:
        print("Optional dependencies not found:")
        for dep in missing_optional:
            print(f"  - {dep}")
        print("\nThe application will work with reduced functionality.")
        print("Install missing dependencies for full feature support.\n")


def print_system_info():
    """Print system and application information."""
    import platform
    
    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"Python {platform.python_version()}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print()


if __name__ == '__main__':
    # Print system info in debug mode
    if '--debug' in sys.argv:
        print_system_info()
        check_dependencies()
    
    # Run main application
    main()
