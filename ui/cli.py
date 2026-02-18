"""
Command-line interface for the Bilingual Subtitle Suite.

This module provides comprehensive CLI functionality for all subtitle operations
including merging, conversion, realignment, and batch processing.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional
from utils.constants import APP_NAME, APP_VERSION, APP_DESCRIPTION
from utils.logging_config import setup_logging, set_log_level
from utils.file_operations import FileHandler
from processors.merger import BilingualMerger
from processors.converter import EncodingConverter
from processors.realigner import SubtitleRealigner
from processors.batch_processor import BatchProcessor
from third_party import PGSRipWrapper, PGSRipNotInstalledError, is_pgsrip_available

logger = None  # Will be initialized in setup_cli_logging


def setup_cli_logging(verbose: bool = False, debug: bool = False):
    """Set up logging for CLI operations."""
    global logger
    import logging
    
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logger = setup_logging(level=level, use_colors=True)
    return logger


class CLIHandler:
    """Handles command-line interface operations."""
    
    def __init__(self):
        """Initialize the CLI handler."""
        self.merger = BilingualMerger()
        self.converter = EncodingConverter()
        self.realigner = SubtitleRealigner()
        self.batch_processor = BatchProcessor()

        # Initialize PGSRip wrapper if available
        self.pgsrip_wrapper = None
        if is_pgsrip_available():
            try:
                self.pgsrip_wrapper = PGSRipWrapper()
            except Exception as e:
                # Logger might not be initialized yet, so use print for now
                pass  # Will be logged later if needed
    
    def create_parser(self) -> argparse.ArgumentParser:
        """
        Create the main argument parser with all subcommands.
        
        Returns:
            Configured ArgumentParser instance
        """
        parser = argparse.ArgumentParser(
            prog='biss',
            description=f'''{APP_DESCRIPTION}

Bilingual Subtitle Suite - Create bilingual subtitles easily.
Combines Chinese/Japanese/Korean subtitles with English subtitles.''',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
QUICK START - Common Use Cases:
================================

1. MERGE FROM VIDEO (extracts embedded subtitles):
   biss merge movie.mkv

2. MERGE TWO SUBTITLE FILES (auto-detects languages):
   biss merge chinese.srt english.srt

3. MERGE WITH EXPLICIT FILES:
   biss merge --chinese sub_chi.srt --english sub_eng.srt

4. SHIFT TIMING (fix sync issues):
   biss shift subtitle.srt --offset="-2.5s"     # Shift back 2.5 seconds
   biss shift subtitle.srt --offset 1500ms      # Shift forward 1.5 seconds

5. CONVERT ENCODING (fix garbled characters):
   biss convert subtitle.srt

6. INTERACTIVE MODE (menu-driven):
   biss interactive

ADVANCED OPTIONS:
=================
--auto-align          Smart multi-anchor alignment (proper nouns, numbers, similarity)
--use-translation     Use Google Translate for cross-language matching
--debug               Show detailed processing information

For detailed help on any command:
  biss <command> --help
            """
        )
        
        parser.add_argument('--version', action='version', version=f'{APP_NAME} {APP_VERSION}')
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
        parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
        parser.add_argument('--dry-run', action='store_true',
                          help='Show what would be done without making changes')
        parser.add_argument('--lang', choices=['en', 'zh', 'ja', 'ko'], default=None,
                          help='UI language (en/zh/ja/ko)')
        
        # Create subparsers for different operations
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Merge command
        self._add_merge_parser(subparsers)
        
        # Convert command
        self._add_convert_parser(subparsers)
        
        # Realign command
        self._add_realign_parser(subparsers)

        # Timing adjustment command
        self._add_timing_adjust_parser(subparsers)

        # Batch commands
        self._add_batch_parsers(subparsers)

        # PGS conversion commands
        self._add_pgs_parsers(subparsers)

        # ASS to SRT conversion command
        self._add_ass_convert_parser(subparsers)

        # Split bilingual subtitles command
        self._add_split_parser(subparsers)

        # Extract command (mkvextract integration)
        self._add_extract_parser(subparsers)

        # Interactive command
        self._add_interactive_parser(subparsers)

        return parser
    
    def _add_merge_parser(self, subparsers):
        """Add merge command parser."""
        merge_parser = subparsers.add_parser(
            'merge',
            help='Merge bilingual subtitles (Chinese-English, Japanese-English, etc.)',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='''Merge subtitle files or extract from video containers.

SIMPLE USAGE (recommended):
  # From video - auto-extracts embedded subtitles
  biss merge movie.mkv

  # Two subtitle files - auto-detects languages
  biss merge chinese.srt english.srt

  # One subtitle + video - finds the other language automatically
  biss merge chinese.srt --video movie.mkv

EXPLICIT LANGUAGE FLAGS (when auto-detection fails):
  biss merge --chinese chinese.srt --english english.srt

The tool auto-detects subtitle languages from:
  1. Filename patterns (.zh.srt, .en.srt, .chi., .eng., etc.)
  2. Content analysis (Chinese characters vs English text)
'''
        )

        # Primary input - can be video OR subtitle file
        merge_parser.add_argument('input', type=Path, nargs='?', default=None,
                                help='Video file, or first subtitle file (language auto-detected)')
        # Second positional argument for easy two-file merging
        merge_parser.add_argument('input2', type=Path, nargs='?', default=None,
                                help='Second subtitle file (language auto-detected)')

        # Explicit language specification (optional - for when auto-detection fails)
        merge_parser.add_argument('-c', '--chinese', type=Path,
                                help='Explicitly specify foreign language subtitle (Chinese/Japanese/Korean)')
        merge_parser.add_argument('-e', '--english', type=Path,
                                help='Explicitly specify English subtitle file')
        merge_parser.add_argument('--video', type=Path,
                                help='Video file to extract missing subtitles from')
        merge_parser.add_argument('-o', '--output', type=Path, help='Output file path')
        merge_parser.add_argument('-f', '--format', choices=['srt', 'ass'], default='srt',
                                help='Output format (default: srt)')
        
        # Track selection options
        merge_parser.add_argument('--chinese-track', help='Force specific Chinese track ID')
        merge_parser.add_argument('--english-track', help='Force specific English track ID (overrides intelligent selection)')
        merge_parser.add_argument('--remap-chinese', help='Language code to treat as Chinese')
        merge_parser.add_argument('--remap-english', help='Language code to treat as English')
        
        # Preference options
        merge_parser.add_argument('--prefer-external', action='store_true',
                                help='Prefer external subtitles over embedded')
        merge_parser.add_argument('--prefer-embedded', action='store_true',
                                help='Prefer embedded subtitles over external')

        # Enhanced alignment options
        merge_parser.add_argument('--auto-align', action='store_true',
                                help='Smart alignment using proper noun matching, numbers, and text similarity')
        merge_parser.add_argument('--use-translation', action='store_true',
                                help='Enable translation-assisted alignment for cross-language matching')
        merge_parser.add_argument('--alignment-threshold', type=float, default=0.8,
                                help='Confidence threshold for automatic alignment (0.0-1.0, default: 0.8)')
        merge_parser.add_argument('--translation-api-key', type=str,
                                help='Google Translation API key (or set GOOGLE_TRANSLATE_API_KEY env var)')

        # Global synchronization options
        merge_parser.add_argument('--manual-align', action='store_true',
                                help='Enable interactive anchor point selection for global synchronization')
        merge_parser.add_argument('--sync-strategy', type=str, default='auto',
                                choices=['auto', 'first-line', 'scan', 'translation', 'manual'],
                                help='Global synchronization strategy (default: auto)')
        merge_parser.add_argument('--reference-language', type=str, default='auto',
                                choices=['chinese', 'english', 'auto'],
                                help='Reference track preference when both tracks are same type (default: auto)')
        merge_parser.add_argument('--list-tracks', action='store_true',
                                help='List available subtitle tracks and exit')
        merge_parser.add_argument('--force-pgs', action='store_true',
                                help='Force PGS subtitle conversion even when other subtitles exist')
        merge_parser.add_argument('--no-pgs', action='store_true',
                                help='Disable PGS auto-activation (skip PGS conversion)')
        merge_parser.add_argument('--enable-mixed-realignment', action='store_true',
                                help='Enable enhanced realignment for mixed embedded+external tracks with major timing misalignment')
        merge_parser.add_argument('--top', type=str, default='first',
                                choices=['first', 'second'],
                                help='Which subtitle appears on top: first (default) or second')

    def _add_convert_parser(self, subparsers):
        """Add convert command parser."""
        convert_parser = subparsers.add_parser(
            'convert',
            help='Convert subtitle file encoding',
            description='Convert subtitle files to UTF-8 encoding'
        )
        
        convert_parser.add_argument('input', type=Path, help='Subtitle file to convert')
        convert_parser.add_argument('-e', '--encoding', default='utf-8',
                                  help='Target encoding (default: utf-8)')
        convert_parser.add_argument('-b', '--backup', action='store_true',
                                  help='Create backup of original file')
        convert_parser.add_argument('-f', '--force', action='store_true',
                                  help='Force conversion even if already target encoding')
    
    def _add_realign_parser(self, subparsers):
        """Add realign command parser."""
        realign_parser = subparsers.add_parser(
            'realign',
            help='Realign subtitle timing',
            description='Realign subtitle files based on reference timing'
        )
        
        realign_parser.add_argument('source', type=Path, help='Source subtitle file to align')
        realign_parser.add_argument('reference', type=Path, help='Reference subtitle file')
        realign_parser.add_argument('-o', '--output', type=Path, help='Output file path')
        realign_parser.add_argument('--source-index', type=int,
                                  help='Source event index for alignment (auto-detect if --auto-align enabled)')
        realign_parser.add_argument('--reference-index', type=int,
                                  help='Reference event index for alignment (auto-detect if --auto-align enabled)')
        realign_parser.add_argument('--no-backup', action='store_true',
                                  help='Do not create backup before overwriting')
        realign_parser.add_argument('--auto-align', action='store_true',
                                  help='Smart alignment using proper noun matching, numbers, and text similarity')
        realign_parser.add_argument('--use-translation', action='store_true',
                                  help='Enable Google Cloud Translation for cross-language alignment')
        realign_parser.add_argument('--translation-api-key', type=str,
                                  help='Google Cloud Translation API key (or set GOOGLE_TRANSLATE_API_KEY env var)')
        realign_parser.add_argument('--reference-language', type=str, default='auto',
                                  choices=['chinese', 'english', 'auto'],
                                  help='Reference track preference when both tracks are same type (default: auto)')
        realign_parser.add_argument('--alignment-threshold', type=float, default=0.8,
                                  help='Confidence threshold for automatic alignment (0.0-1.0, default: 0.8)')
        realign_parser.add_argument('--sync-strategy', type=str, default='auto',
                                  choices=['auto', 'first-line', 'scan', 'translation', 'manual'],
                                  help='Global synchronization strategy (default: auto)')

    def _add_timing_adjust_parser(self, subparsers):
        """Add timing adjustment command parser."""
        timing_parser = subparsers.add_parser(
            'shift',
            help='Adjust subtitle timing',
            description='Shift subtitle timing by offset or set first line to specific timestamp'
        )

        timing_parser.add_argument('input', type=Path, help='Subtitle file to adjust')
        timing_parser.add_argument('-o', '--output', type=Path, help='Output file path (default: overwrite input)')
        timing_parser.add_argument('-b', '--backup', action='store_true',
                                 help='Create backup of original file')

        # Mutually exclusive group for adjustment methods
        adjust_group = timing_parser.add_mutually_exclusive_group(required=True)
        adjust_group.add_argument('--offset', type=str,
                                help='Time offset (e.g., "2.5s", "-1500ms", "00:00:02,500")')
        adjust_group.add_argument('--first-line-at', type=str,
                                help='Set first subtitle to start at this timestamp (e.g., "00:00:50,983")')

    def _add_batch_parsers(self, subparsers):
        """Add batch processing command parsers."""
        # Batch convert
        batch_convert_parser = subparsers.add_parser(
            'batch-convert',
            help='Batch convert subtitle encodings',
            description='Convert multiple subtitle files in a directory'
        )
        
        batch_convert_parser.add_argument('directory', type=Path, help='Directory to process')
        batch_convert_parser.add_argument('-r', '--recursive', action='store_true',
                                        help='Process subdirectories recursively')
        batch_convert_parser.add_argument('-e', '--encoding', default='utf-8',
                                        help='Target encoding (default: utf-8)')
        batch_convert_parser.add_argument('-b', '--backup', action='store_true',
                                        help='Create backup files')
        batch_convert_parser.add_argument('-f', '--force', action='store_true',
                                        help='Force conversion')
        batch_convert_parser.add_argument('--parallel', action='store_true',
                                        help='Use parallel processing')
        
        # Batch merge
        batch_merge_parser = subparsers.add_parser(
            'batch-merge',
            help='Batch merge subtitles from videos',
            description='Process multiple video files for subtitle merging'
        )
        
        batch_merge_parser.add_argument('directory', type=Path, help='Directory containing videos')
        batch_merge_parser.add_argument('-r', '--recursive', action='store_true',
                                      help='Process subdirectories recursively')
        batch_merge_parser.add_argument('-f', '--format', choices=['srt', 'ass'], default='srt',
                                      help='Output format (default: srt)')
        batch_merge_parser.add_argument('--prefer-external', action='store_true',
                                      help='Prefer external subtitles')
        batch_merge_parser.add_argument('--prefer-embedded', action='store_true',
                                      help='Prefer embedded subtitles')
        batch_merge_parser.add_argument('--auto-confirm', action='store_true',
                                      help='Skip interactive confirmations for fully automated processing')

        # Track selection options
        batch_merge_parser.add_argument('--chinese-track', help='Force specific Chinese track ID for all files')
        batch_merge_parser.add_argument('--english-track', help='Force specific English track ID for all files (overrides intelligent selection)')
        batch_merge_parser.add_argument('--remap-chinese', help='Language code to treat as Chinese')
        batch_merge_parser.add_argument('--remap-english', help='Language code to treat as English')
        batch_merge_parser.add_argument('--top', choices=['first', 'second'], default='first',
                                      help='Which subtitle appears on top: first=foreign language, second=English (default: first)')

        # Enhanced alignment options for batch processing
        batch_merge_parser.add_argument('--auto-align', action='store_true',
                                      help='Smart alignment using proper noun matching, numbers, and text similarity')
        batch_merge_parser.add_argument('--use-translation', action='store_true',
                                      help='Enable translation-assisted alignment for cross-language matching')
        batch_merge_parser.add_argument('--alignment-threshold', type=float, default=0.8,
                                      help='Confidence threshold for automatic alignment (0.0-1.0, default: 0.8)')
        batch_merge_parser.add_argument('--translation-api-key', type=str,
                                      help='Google Translation API key (or set GOOGLE_TRANSLATE_API_KEY env var)')
        batch_merge_parser.add_argument('--manual-align', action='store_true',
                                      help='Enable interactive anchor point selection for global synchronization')
        batch_merge_parser.add_argument('--sync-strategy', type=str, default='auto',
                                      choices=['auto', 'first-line', 'scan', 'translation', 'manual'],
                                      help='Global synchronization strategy (default: auto)')
        batch_merge_parser.add_argument('--reference-language', type=str, default='auto',
                                      choices=['chinese', 'english', 'auto'],
                                      help='Reference track preference when both tracks are same type (default: auto)')

        # Bulk alignment command (non-combined)
        batch_align_parser = subparsers.add_parser('batch-align',
                                                 help='Bulk align subtitle files without combining them')
        batch_align_parser.add_argument('source_dir', type=Path,
                                       help='Source directory containing subtitles to align')
        batch_align_parser.add_argument('--source-pattern', type=str, required=True,
                                       help='Source file pattern (e.g., *.zh.srt)')
        batch_align_parser.add_argument('--reference-pattern', type=str, required=True,
                                       help='Reference file pattern (e.g., *.en.srt)')
        batch_align_parser.add_argument('--reference-dir', type=Path,
                                       help='Reference directory (if different from source)')
        batch_align_parser.add_argument('--output-dir', type=Path,
                                       help='Output directory (if different from source)')
        batch_align_parser.add_argument('--no-backup', action='store_true',
                                       help='Skip creating .bak backup files')
        batch_align_parser.add_argument('--auto-confirm', action='store_true',
                                       help='Skip interactive confirmations')

        # Enhanced alignment options for batch-align
        batch_align_parser.add_argument('--auto-align', action='store_true',
                                       help='Smart alignment using proper noun matching, numbers, and text similarity')
        batch_align_parser.add_argument('--use-translation', action='store_true',
                                       help='Enable translation-assisted alignment')
        batch_align_parser.add_argument('--alignment-threshold', type=float, default=0.8,
                                       help='Confidence threshold for automatic alignment (0.0-1.0, default: 0.8)')
        batch_align_parser.add_argument('--translation-api-key', type=str,
                                       help='Google Translation API key')
        batch_align_parser.add_argument('--manual-align', action='store_true',
                                       help='Enable interactive anchor point selection')
        batch_align_parser.add_argument('--sync-strategy', type=str, default='auto',
                                       choices=['auto', 'first-line', 'scan', 'translation', 'manual'],
                                       help='Global synchronization strategy (default: auto)')
        batch_align_parser.add_argument('--reference-language', type=str, default='auto',
                                       choices=['chinese', 'english', 'auto'],
                                       help='Reference track preference (default: auto)')

        # Backup management command
        backup_parser = subparsers.add_parser('cleanup-backups',
                                            help='Clean up .bak backup files')
        backup_parser.add_argument('directory', type=Path,
                                 help='Directory to clean up backup files')
        backup_parser.add_argument('--older-than', type=int, default=7,
                                 help='Remove backups older than N days (default: 7)')
        backup_parser.add_argument('--dry-run', action='store_true',
                                 help='Show what would be deleted without actually deleting')
        backup_parser.add_argument('--recursive', action='store_true',
                                 help='Process subdirectories recursively')
        
        # Batch realign
        batch_realign_parser = subparsers.add_parser(
            'batch-realign',
            help='Batch realign subtitle pairs',
            description='Realign matching subtitle pairs in a directory'
        )
        
        batch_realign_parser.add_argument('directory', type=Path, help='Directory containing subtitle pairs')
        batch_realign_parser.add_argument('--source-ext', required=True,
                                        help='Source file extension (e.g., .zh.srt)')
        batch_realign_parser.add_argument('--reference-ext', required=True,
                                        help='Reference file extension (e.g., .en.srt)')
        batch_realign_parser.add_argument('--output-suffix', default='',
                                        help='Suffix for output files')
        batch_realign_parser.add_argument('--no-backup', action='store_true',
                                        help='Do not create backups')

    def _add_ass_convert_parser(self, subparsers):
        """Add ASS to SRT conversion command parser."""
        ass_convert_parser = subparsers.add_parser(
            'convert-ass',
            help='Convert ASS/SSA subtitles to SRT format',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='''Convert ASS/SSA subtitle files to SRT format.

This command converts Advanced SubStation Alpha (ASS/SSA) subtitle files
to the simpler SRT format, with special handling for bilingual subtitles.

FEATURES:
  - Preserves bilingual structure (CJK text on top, English below)
  - Removes ASS formatting codes and effects
  - Handles various character encodings automatically
  - Supports batch conversion of multiple files

USAGE:
  # Convert a single file
  biss convert-ass subtitle.ass

  # Convert with custom output name
  biss convert-ass subtitle.ass -o output.srt

  # Batch convert all ASS files in a directory
  biss convert-ass *.ass
  biss convert-ass /path/to/subtitles/ -r

BILINGUAL HANDLING:
  ASS files often contain bilingual subtitles with Chinese/Japanese/Korean
  text followed by English translation. This converter preserves that
  structure in the SRT output.

  Example ASS text:
    你好世界\\N{\\fnArial}Hello World

  Becomes SRT text:
    你好世界
    Hello World
'''
        )

        ass_convert_parser.add_argument('input', type=Path, nargs='+',
                                       help='ASS/SSA file(s) or directory to convert')
        ass_convert_parser.add_argument('-o', '--output', type=Path,
                                       help='Output file path (for single file) or directory (for batch)')
        ass_convert_parser.add_argument('-r', '--recursive', action='store_true',
                                       help='Process directories recursively')
        ass_convert_parser.add_argument('--no-bilingual', action='store_true',
                                       help='Do not preserve bilingual structure')
        ass_convert_parser.add_argument('--keep-effects', action='store_true',
                                       help='Keep ASS formatting effects (not recommended for SRT)')
        ass_convert_parser.add_argument('--preview', action='store_true',
                                       help='Preview conversion without writing files')

    def _add_split_parser(self, subparsers):
        """Add split bilingual subtitles command parser."""
        split_parser = subparsers.add_parser(
            'split',
            help='Split bilingual subtitles into separate language files',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='''Split a bilingual subtitle file into separate language files.

This is the inverse of the merge operation - it takes a subtitle file that
contains both CJK (Chinese/Japanese/Korean) and English text, and produces
two separate files: one for each language.

USAGE:
  # Split a bilingual SRT into Chinese and English files
  biss split bilingual.zh.srt

  # Split with custom output directory
  biss split bilingual.srt -o /path/to/output/

  # Split without stripping HTML formatting
  biss split bilingual.srt --keep-formatting

COMMON USE CASE:
  If Chinese/CJK subtitles are not displaying properly in your media player
  (showing as squares or missing), use ASS output format which embeds a
  CJK-compatible font specification:

  biss split bilingual.zh.srt -f ass

OUTPUT:
  Given input "Movie.zh.srt" with -f ass:
    - Movie.zh.ass  (Chinese/CJK with CJK font embedded in style)
    - Movie.en.srt  (English text only)

  Given input "Movie.zh.srt" (default SRT):
    - Movie.zh.srt  (Chinese/CJK text only)
    - Movie.en.srt  (English text only)
'''
        )

        split_parser.add_argument('input', type=Path,
                                  help='Bilingual subtitle file to split')
        split_parser.add_argument('-o', '--output-dir', type=Path,
                                  help='Output directory (default: same as input file)')
        split_parser.add_argument('--keep-formatting', action='store_true',
                                  help='Keep HTML formatting tags (default: strip them)')
        split_parser.add_argument('--lang1', type=str, default='zh',
                                  help='Label for CJK language output file (default: zh)')
        split_parser.add_argument('--lang2', type=str, default='en',
                                  help='Label for English/Latin output file (default: en)')
        split_parser.add_argument('-f', '--format', choices=['srt', 'ass'], default='srt',
                                  help='Output format for CJK file (default: srt). Use "ass" to embed CJK font for better player compatibility.')

    def _add_pgs_parsers(self, subparsers):
        """Add PGS conversion command parsers."""
        # Convert PGS
        convert_pgs_parser = subparsers.add_parser(
            'convert-pgs',
            help='Convert PGS subtitles to SRT format',
            description='Convert PGS (Presentation Graphic Stream) subtitles to SRT using OCR'
        )

        convert_pgs_parser.add_argument('input', type=Path, help='Video file with PGS subtitles, or standalone .sup/.idx/.sub file')
        convert_pgs_parser.add_argument('-o', '--output', type=Path, help='Output SRT file path')
        convert_pgs_parser.add_argument('-l', '--language',
                                      choices=['eng', 'chi_sim', 'chi_tra', 'jpn', 'kor'],
                                      help='OCR language (auto-detect if not specified)')
        convert_pgs_parser.add_argument('-t', '--track', help='Specific PGS track ID to convert')
        convert_pgs_parser.add_argument('--list-tracks', action='store_true',
                                      help='List available PGS tracks and exit')

        # Batch convert PGS
        batch_convert_pgs_parser = subparsers.add_parser(
            'batch-convert-pgs',
            help='Batch convert PGS subtitles from multiple videos',
            description='Convert PGS subtitles from multiple video files'
        )

        batch_convert_pgs_parser.add_argument('directory', type=Path,
                                            help='Directory containing video files')
        batch_convert_pgs_parser.add_argument('-r', '--recursive', action='store_true',
                                            help='Process subdirectories recursively')
        batch_convert_pgs_parser.add_argument('-o', '--output-dir', type=Path,
                                            help='Output directory for SRT files')
        batch_convert_pgs_parser.add_argument('-l', '--language',
                                            choices=['eng', 'chi_sim', 'chi_tra', 'jpn', 'kor'],
                                            help='OCR language for all conversions')

        # Setup PGSRip
        setup_pgsrip_parser = subparsers.add_parser(
            'setup-pgsrip',
            help='Setup PGSRip for PGS subtitle conversion',
            description='Install and configure PGSRip and dependencies'
        )

        setup_pgsrip_parser.add_argument('action', choices=['install', 'uninstall', 'check'],
                                       help='Setup action to perform')
        setup_pgsrip_parser.add_argument('--languages', nargs='+',
                                       default=['eng', 'chi_sim', 'chi_tra'],
                                       help='OCR languages to install')
    
    def _add_extract_parser(self, subparsers):
        """Add extract command parser for mkvextract integration."""
        extract_parser = subparsers.add_parser(
            'extract',
            help='Extract subtitle tracks from MKV files (uses mkvextract)',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description='''Extract subtitle tracks from MKV video files using mkvextract.

This is much faster than ffmpeg for MKV files and allows extracting
multiple tracks in a single command.

USAGE:
  # List all tracks in an MKV file
  biss extract movie.mkv --list

  # Extract specific tracks by ID
  biss extract movie.mkv --tracks 3 42

  # Extract with custom output names
  biss extract movie.mkv --tracks 3:english.srt 42:chinese.srt

  # Extract all subtitle tracks
  biss extract movie.mkv --all

FINDING TRACK IDs:
  Use --list to see all tracks with their IDs. The ID shown is the one
  to use with --tracks. Track IDs are typically 0-based.

NOTE: Requires mkvextract (part of MKVToolNix) to be installed.
'''
        )

        extract_parser.add_argument('input', type=Path, help='MKV video file')
        extract_parser.add_argument('--list', '-l', action='store_true',
                                   help='List all tracks and exit')
        extract_parser.add_argument('--tracks', '-t', nargs='+',
                                   help='Track IDs to extract (e.g., "3" or "3:output.srt")')
        extract_parser.add_argument('--all', '-a', action='store_true',
                                   help='Extract all subtitle tracks')
        extract_parser.add_argument('--output-dir', '-o', type=Path,
                                   help='Output directory (default: same as input)')
        extract_parser.add_argument('--lang', nargs='+',
                                   help='Extract tracks matching these language codes (e.g., eng chi jpn)')

    def _add_interactive_parser(self, subparsers):
        """Add interactive command parser."""
        interactive_parser = subparsers.add_parser(
            'interactive',
            help='Launch interactive text mode',
            description='Launch interactive menu-driven interface (text-based)'
        )

        interactive_parser.add_argument('--no-colors', action='store_true',
                                      help='Disable colored output')

        # GUI command
        gui_parser = subparsers.add_parser(
            'gui',
            help='Launch graphical interface',
            description='Launch the graphical user interface (GUI)'
        )
    
    def handle_command(self, args) -> int:
        """
        Handle the parsed command-line arguments.
        
        Args:
            args: Parsed arguments from argparse
            
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        # Set up logging
        setup_cli_logging(args.verbose, args.debug)
        
        if not args.command:
            logger.error("No command specified. Use --help for usage information.")
            return 1
        
        try:
            if args.command == 'merge':
                return self._handle_merge(args)
            elif args.command == 'convert':
                return self._handle_convert(args)
            elif args.command == 'realign':
                return self._handle_realign(args)
            elif args.command == 'shift':
                return self._handle_timing_adjust(args)
            elif args.command == 'batch-convert':
                return self._handle_batch_convert(args)
            elif args.command == 'batch-merge':
                return self._handle_batch_merge(args)
            elif args.command == 'batch-align':
                return self._handle_batch_align(args)
            elif args.command == 'cleanup-backups':
                return self._handle_cleanup_backups(args)
            elif args.command == 'batch-realign':
                return self._handle_batch_realign(args)
            elif args.command == 'convert-ass':
                return self._handle_convert_ass(args)
            elif args.command == 'split':
                return self._handle_split(args)
            elif args.command == 'convert-pgs':
                return self._handle_convert_pgs(args)
            elif args.command == 'batch-convert-pgs':
                return self._handle_batch_convert_pgs(args)
            elif args.command == 'setup-pgsrip':
                return self._handle_setup_pgsrip(args)
            elif args.command == 'extract':
                return self._handle_extract(args)
            elif args.command == 'interactive':
                return self._handle_interactive(args)
            elif args.command == 'gui':
                return self._handle_gui(args)
            else:
                logger.error(f"Unknown command: {args.command}")
                return 1
                
        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            return 1
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            if args.debug:
                import traceback
                traceback.print_exc()
            return 1

    def _handle_merge(self, args) -> int:
        """Handle merge command with smart language auto-detection."""
        from core.video_containers import VideoContainerHandler
        from core.language_detection import LanguageDetector

        # Resolve input files with smart language detection
        chinese_path, english_path, video_path = self._resolve_merge_inputs(args)

        # Validate we have something to work with
        if not chinese_path and not english_path and not video_path:
            logger.error("No input files specified. Use: biss merge <file1> [file2]")
            print("\nUsage examples:")
            print("  biss merge movie.mkv                    # Extract from video")
            print("  biss merge chinese.srt english.srt      # Merge two subtitle files")
            print("  biss merge subtitle.srt --video movie.mkv")
            return 1

        # Handle track listing (requires video)
        if getattr(args, 'list_tracks', False):
            if video_path:
                return self._list_video_tracks(video_path)
            elif args.input and VideoContainerHandler.is_video_container(args.input):
                return self._list_video_tracks(args.input)
            else:
                logger.error("--list-tracks requires a video file")
                return 1

        # Dry-run mode: show what would happen without executing
        if getattr(args, 'dry_run', False):
            print("\n[DRY RUN] Would perform the following merge operation:")
            if video_path:
                print(f"  Mode: Extract from video")
                print(f"  Video: {video_path}")
            else:
                print(f"  Mode: Merge subtitle files")
            if chinese_path:
                print(f"  Foreign language: {chinese_path}")
            if english_path:
                print(f"  English: {english_path}")
            output = args.output or "(auto-generated)"
            print(f"  Output format: {args.format}")
            print(f"  Output file: {output}")
            print(f"  Auto-align: {getattr(args, 'auto_align', False)}")
            print(f"  Use translation: {getattr(args, 'use_translation', False)}")
            print("\n[DRY RUN] No changes made.")
            return 0

        # Create merger with appropriate options
        merger = self._create_merger(args)

        # Determine processing mode
        if video_path:
            # Process video file (extract embedded + use provided external)
            logger.info(f"Processing video: {video_path.name}")
            success = merger.process_video(
                video_path=video_path,
                chinese_sub=chinese_path,
                english_sub=english_path,
                output_format=args.format,
                output_path=args.output,
                chinese_track=getattr(args, 'chinese_track', None),
                english_track=getattr(args, 'english_track', None),
                remap_chinese=getattr(args, 'remap_chinese', None),
                remap_english=getattr(args, 'remap_english', None),
                prefer_external=getattr(args, 'prefer_external', False),
                prefer_embedded=getattr(args, 'prefer_embedded', False)
            )
        else:
            # Merge subtitle files directly
            if not chinese_path and not english_path:
                logger.error("Need at least one subtitle file to merge")
                return 1

            logger.info(f"Merging subtitle files")
            if chinese_path:
                logger.info(f"  Foreign language: {chinese_path.name}")
            if english_path:
                logger.info(f"  English: {english_path.name}")

            success = merger.merge_subtitle_files(
                chinese_path=chinese_path,
                english_path=english_path,
                output_path=args.output,
                output_format=args.format
            )

        return 0 if success else 1

    def _resolve_merge_inputs(self, args):
        """
        Resolve merge inputs with smart language auto-detection.

        Handles multiple input patterns:
        1. biss merge movie.mkv                    -> video processing
        2. biss merge chinese.srt english.srt     -> two subtitle files
        3. biss merge subtitle.srt --video movie.mkv -> subtitle + video
        4. biss merge --chinese x.srt --english y.srt -> explicit flags

        Returns:
            Tuple of (chinese_path, english_path, video_path)
        """
        from core.video_containers import VideoContainerHandler
        from core.language_detection import LanguageDetector

        chinese_path = getattr(args, 'chinese', None)
        english_path = getattr(args, 'english', None)
        video_path = getattr(args, 'video', None)

        # Collect all input files for auto-detection
        input_files = []
        if args.input and args.input.exists():
            input_files.append(args.input)
        if getattr(args, 'input2', None) and args.input2.exists():
            input_files.append(args.input2)

        # Process each input file
        for input_file in input_files:
            if VideoContainerHandler.is_video_container(input_file):
                # It's a video file
                if not video_path:
                    video_path = input_file
                    logger.info(f"Detected video file: {input_file.name}")
            else:
                # It's a subtitle file - auto-detect language
                detected_lang = self._detect_subtitle_language(input_file)
                logger.info(f"Detected '{detected_lang}' language for: {input_file.name}")

                if detected_lang in ['zh', 'ja', 'ko', 'chinese', 'japanese', 'korean']:
                    if not chinese_path:
                        chinese_path = input_file
                        logger.info(f"  -> Using as foreign language subtitle")
                    elif not english_path:
                        # Might be mislabeled, use as English
                        english_path = input_file
                        logger.warning(f"  -> Already have foreign sub, using as English")
                elif detected_lang in ['en', 'english']:
                    if not english_path:
                        english_path = input_file
                        logger.info(f"  -> Using as English subtitle")
                    elif not chinese_path:
                        chinese_path = input_file
                        logger.warning(f"  -> Already have English, using as foreign")
                else:
                    # Unknown language - assign to first empty slot
                    if not chinese_path:
                        chinese_path = input_file
                        logger.info(f"  -> Unknown language, using as foreign subtitle")
                    elif not english_path:
                        english_path = input_file
                        logger.info(f"  -> Unknown language, using as English subtitle")

        return chinese_path, english_path, video_path

    def _detect_subtitle_language(self, file_path: Path) -> str:
        """Detect subtitle file language from filename and content."""
        from core.language_detection import LanguageDetector

        # Try filename first (fast)
        lang = LanguageDetector.detect_language_from_filename(str(file_path.name))
        if lang != 'unknown':
            return lang

        # Fall back to content analysis (slower but more accurate)
        return LanguageDetector.detect_subtitle_language(file_path)

    def _create_merger(self, args):
        """Create BilingualMerger with appropriate options."""
        # Check if enhanced alignment is requested
        use_enhanced = (
            getattr(args, 'auto_align', False) or
            getattr(args, 'use_translation', False) or
            getattr(args, 'manual_align', False)
        )

        # Get top_language setting
        top_language = getattr(args, 'top', 'first')

        if use_enhanced:
            merger = BilingualMerger(
                auto_align=getattr(args, 'auto_align', False),
                use_translation=getattr(args, 'use_translation', False),
                alignment_threshold=getattr(args, 'alignment_threshold', 0.8),
                translation_api_key=getattr(args, 'translation_api_key', None),
                manual_align=getattr(args, 'manual_align', False),
                sync_strategy=getattr(args, 'sync_strategy', 'auto'),
                reference_language_preference=getattr(args, 'reference_language', 'auto'),
                force_pgs=getattr(args, 'force_pgs', False),
                no_pgs=getattr(args, 'no_pgs', False),
                enable_mixed_realignment=getattr(args, 'enable_mixed_realignment', False),
                top_language=top_language
            )
            logger.info(f"Enhanced alignment enabled: auto_align={args.auto_align}, "
                       f"use_translation={getattr(args, 'use_translation', False)}")
        else:
            merger = BilingualMerger(
                force_pgs=getattr(args, 'force_pgs', False),
                no_pgs=getattr(args, 'no_pgs', False),
                top_language=top_language
            )

        return merger

    def _handle_convert(self, args) -> int:
        """Handle convert command."""
        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        success = self.converter.convert_file(
            file_path=args.input,
            keep_backup=args.backup,
            force_conversion=args.force,
            target_encoding=args.encoding
        )

        if success:
            logger.info(f"Successfully converted: {args.input}")
        else:
            logger.info(f"No conversion needed: {args.input}")

        return 0

    def _handle_realign(self, args) -> int:
        """Handle realign command."""
        if not args.source.exists():
            logger.error(f"Source file not found: {args.source}")
            return 1

        if not args.reference.exists():
            logger.error(f"Reference file not found: {args.reference}")
            return 1

        # Initialize realigner with new features if requested
        if args.auto_align or args.use_translation:
            from processors.realigner import SubtitleRealigner
            realigner = SubtitleRealigner(
                use_translation=args.use_translation,
                auto_align=args.auto_align,
                translation_api_key=args.translation_api_key
            )
        else:
            realigner = self.realigner

        success = realigner.align_subtitles(
            source_path=args.source,
            reference_path=args.reference,
            output_path=args.output,
            source_align_idx=args.source_index,
            ref_align_idx=args.reference_index,
            create_backup=not args.no_backup,
            use_auto_align=args.auto_align,
            use_translation=args.use_translation
        )

        return 0 if success else 1

    def _handle_timing_adjust(self, args) -> int:
        """Handle timing adjustment command."""
        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        from processors.timing_adjuster import TimingAdjuster

        # Create timing adjuster with backup option
        adjuster = TimingAdjuster(create_backup=args.backup)

        try:
            # Dry-run mode: show what would happen
            if getattr(args, 'dry_run', False):
                print("\n[DRY RUN] Would perform the following timing adjustment:")
                print(f"  Input file: {args.input}")
                if args.offset:
                    offset_ms = adjuster.parse_offset_string(args.offset)
                    direction = "earlier" if offset_ms < 0 else "later"
                    print(f"  Operation: Shift all subtitles {abs(offset_ms)}ms {direction}")
                elif args.first_line_at:
                    print(f"  Operation: Set first subtitle to start at {args.first_line_at}")
                output = args.output or args.input
                print(f"  Output file: {output}")
                print(f"  Create backup: {args.backup}")
                print("\n[DRY RUN] No changes made.")
                return 0

            if args.offset:
                # Parse offset and apply adjustment
                offset_ms = adjuster.parse_offset_string(args.offset)
                success = adjuster.adjust_by_offset(args.input, offset_ms, args.output)
            elif args.first_line_at:
                # Adjust first line to target timestamp
                success = adjuster.adjust_first_line_to(args.input, args.first_line_at, args.output)
            else:
                logger.error("Either --offset or --first-line-at must be specified")
                return 1

            return 0 if success else 1

        except ValueError as e:
            logger.error(f"Invalid input: {e}")
            return 1
        except Exception as e:
            logger.error(f"Timing adjustment failed: {e}")
            return 1

    def _handle_batch_convert(self, args) -> int:
        """Handle batch-convert command."""
        if not args.directory.exists():
            logger.error(f"Directory not found: {args.directory}")
            return 1

        results = self.batch_processor.process_subtitles_batch(
            subtitle_paths=FileHandler.find_subtitle_files(args.directory, args.recursive),
            operation="convert",
            parallel=args.parallel,
            keep_backup=args.backup,
            force_conversion=args.force,
            target_encoding=args.encoding
        )

        print(self.batch_processor.get_processing_summary(results))
        return 0 if results['failed'] == 0 else 1

    def _handle_batch_merge(self, args) -> int:
        """Handle batch-merge command with enhanced interactive processing."""
        if not args.directory.exists():
            logger.error(f"Directory not found: {args.directory}")
            return 1

        # Create batch processor with auto-confirm setting
        batch_processor = BatchProcessor(auto_confirm=args.auto_confirm)

        # Prepare merger options for enhanced alignment
        merger_options = {}
        if hasattr(args, 'top') and args.top != 'first':
            merger_options['top_language'] = args.top
        if hasattr(args, 'auto_align') and (args.auto_align or args.use_translation or args.manual_align):
            merger_options.update({
                'auto_align': args.auto_align,
                'use_translation': args.use_translation,
                'alignment_threshold': args.alignment_threshold,
                'translation_api_key': args.translation_api_key,
                'manual_align': args.manual_align,
                'sync_strategy': args.sync_strategy,
                'reference_language_preference': args.reference_language
            })

        # Prepare video processing options (passed to process_video per-file)
        video_options = {}
        if getattr(args, 'chinese_track', None):
            video_options['chinese_track'] = args.chinese_track
        if getattr(args, 'english_track', None):
            video_options['english_track'] = args.english_track
        if getattr(args, 'remap_chinese', None):
            video_options['remap_chinese'] = args.remap_chinese
        if getattr(args, 'remap_english', None):
            video_options['remap_english'] = args.remap_english
        if getattr(args, 'prefer_external', False):
            video_options['prefer_external'] = True
        if getattr(args, 'prefer_embedded', False):
            video_options['prefer_embedded'] = True
        if getattr(args, 'format', 'srt') != 'srt':
            video_options['output_format'] = args.format

        # Use interactive processing for enhanced user control
        results = batch_processor.process_directory_interactive(
            directory=args.directory,
            pattern="*.mkv",  # Focus on video files
            merger_options=merger_options if merger_options else None,
            video_options=video_options if video_options else None
        )

        # Print summary
        print(f"\n{'='*60}")
        print("BATCH PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"Total files: {results['total']}")
        print(f"Successfully processed: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped: {results['skipped']}")

        if results['errors']:
            print(f"\nErrors:")
            for error in results['errors']:
                print(f"  - {error}")

        if results['processed_files']:
            print(f"\nProcessed files:")
            for file_path in results['processed_files']:
                print(f"  ✅ {file_path}")

        return 0 if results['failed'] == 0 else 1

    def _handle_batch_align(self, args) -> int:
        """Handle batch-align command for bulk subtitle alignment."""
        if not args.source_dir.exists():
            logger.error(f"Source directory not found: {args.source_dir}")
            return 1

        # Validate reference directory if specified
        reference_dir = args.reference_dir or args.source_dir
        if not reference_dir.exists():
            logger.error(f"Reference directory not found: {reference_dir}")
            return 1

        # Create bulk alignment processor
        from processors.bulk_aligner import BulkSubtitleAligner

        bulk_aligner = BulkSubtitleAligner(
            auto_confirm=args.auto_confirm,
            create_backup=not args.no_backup
        )

        # Prepare alignment options
        alignment_options = {
            'auto_align': args.auto_align,
            'use_translation': args.use_translation,
            'alignment_threshold': args.alignment_threshold,
            'translation_api_key': args.translation_api_key,
            'manual_align': args.manual_align,
            'sync_strategy': args.sync_strategy,
            'reference_language_preference': args.reference_language
        }

        # Perform bulk alignment
        results = bulk_aligner.align_directory(
            source_dir=args.source_dir,
            source_pattern=args.source_pattern,
            reference_pattern=args.reference_pattern,
            reference_dir=reference_dir,
            output_dir=args.output_dir,
            alignment_options=alignment_options
        )

        # Print summary
        print(f"\n{'='*60}")
        print("BULK ALIGNMENT SUMMARY")
        print(f"{'='*60}")
        print(f"Total files: {results['total']}")
        print(f"Successfully aligned: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped: {results['skipped']}")

        if results['errors']:
            print(f"\nErrors:")
            for error in results['errors']:
                print(f"  - {error}")

        if results['aligned_files']:
            print(f"\nAligned files:")
            for file_info in results['aligned_files']:
                print(f"  ✅ {file_info['source']} -> {file_info['output']}")

        return 0 if results['failed'] == 0 else 1

    def _handle_cleanup_backups(self, args) -> int:
        """Handle cleanup-backups command."""
        if not args.directory.exists():
            logger.error(f"Directory not found: {args.directory}")
            return 1

        from utils.backup_manager import BackupManager

        backup_manager = BackupManager()

        # Find backup files
        backup_files = backup_manager.find_backup_files(
            directory=args.directory,
            recursive=args.recursive,
            older_than_days=args.older_than
        )

        if not backup_files:
            print(f"No backup files found older than {args.older_than} days")
            return 0

        print(f"Found {len(backup_files)} backup files to clean up:")

        total_size = 0
        for backup_file in backup_files:
            size = backup_file.stat().st_size
            total_size += size
            age_days = backup_manager.get_file_age_days(backup_file)
            print(f"  {backup_file} ({size:,} bytes, {age_days} days old)")

        print(f"\nTotal size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")

        if args.dry_run:
            print("\n[DRY RUN] No files were actually deleted")
            return 0

        # Confirm deletion
        confirm = input(f"\nDelete {len(backup_files)} backup files? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Cleanup cancelled")
            return 0

        # Delete backup files
        deleted_count = backup_manager.cleanup_backups(backup_files)

        print(f"✅ Successfully deleted {deleted_count} backup files")
        return 0

    def _handle_batch_realign(self, args) -> int:
        """Handle batch-realign command."""
        if not args.directory.exists():
            logger.error(f"Directory not found: {args.directory}")
            return 1

        results = self.batch_processor.process_realign_batch(
            directory=args.directory,
            source_ext=args.source_ext,
            reference_ext=args.reference_ext,
            output_suffix=args.output_suffix,
            create_backup=not args.no_backup
        )

        print(self.batch_processor.get_processing_summary(results))
        return 0 if results['failed'] == 0 else 1

    def _handle_convert_ass(self, args) -> int:
        """Handle convert-ass command for ASS/SSA to SRT conversion."""
        from core.ass_converter import ASSToSRTConverter

        # Collect input files
        input_files = []

        for input_path in args.input:
            if input_path.is_dir():
                # Process directory
                pattern = '**/*.ass' if args.recursive else '*.ass'
                input_files.extend(input_path.glob(pattern))
                pattern = '**/*.ssa' if args.recursive else '*.ssa'
                input_files.extend(input_path.glob(pattern))
            elif input_path.exists():
                if input_path.suffix.lower() in ['.ass', '.ssa']:
                    input_files.append(input_path)
                else:
                    logger.warning(f"Skipping non-ASS file: {input_path}")
            else:
                logger.warning(f"File not found: {input_path}")

        if not input_files:
            logger.error("No ASS/SSA files found to convert")
            return 1

        # Create converter with options
        converter = ASSToSRTConverter(
            strip_effects=not getattr(args, 'keep_effects', False),
            preserve_bilingual=not getattr(args, 'no_bilingual', False)
        )

        # Preview mode
        if getattr(args, 'preview', False):
            print("\n" + "=" * 60)
            print("CONVERSION PREVIEW")
            print("=" * 60)

            for input_file in input_files[:3]:  # Preview first 3 files
                print(f"\n--- {input_file.name} ---")
                try:
                    preview = converter.get_preview(input_file, max_entries=5)
                    for entry in preview:
                        print(f"[{entry['start']} --> {entry['end']}]")
                        # Indent text lines for readability
                        for line in entry['text'].split('\n'):
                            print(f"  {line}")
                        print()
                except Exception as e:
                    print(f"  Error: {e}")

            if len(input_files) > 3:
                print(f"\n... and {len(input_files) - 3} more files")

            print("\n[PREVIEW MODE] No files were written.")
            return 0

        # Dry-run mode (from global --dry-run flag)
        if getattr(args, 'dry_run', False):
            print("\n[DRY RUN] Would convert the following files:")
            for input_file in input_files:
                output_file = input_file.with_suffix('.srt')
                print(f"  {input_file} -> {output_file}")
            print("\n[DRY RUN] No changes made.")
            return 0

        # Convert files
        successful = 0
        failed = 0

        # Determine output path
        output_path = getattr(args, 'output', None)

        for input_file in input_files:
            try:
                # Determine output for this file
                if output_path:
                    if output_path.is_dir():
                        output_file = output_path / input_file.with_suffix('.srt').name
                    elif len(input_files) == 1:
                        output_file = output_path
                    else:
                        output_file = output_path / input_file.with_suffix('.srt').name
                else:
                    output_file = input_file.with_suffix('.srt')

                result_path = converter.convert_file(input_file, output_file)
                print(f"Converted: {input_file.name} -> {result_path.name}")
                successful += 1

            except Exception as e:
                logger.error(f"Failed to convert {input_file.name}: {e}")
                failed += 1

        # Print summary
        print(f"\n{'='*60}")
        print(f"ASS TO SRT CONVERSION SUMMARY")
        print(f"{'='*60}")
        print(f"Total files: {len(input_files)}")
        print(f"Successfully converted: {successful}")
        print(f"Failed: {failed}")

        return 0 if failed == 0 else 1

    def _handle_split(self, args) -> int:
        """Handle split command for splitting bilingual subtitles."""
        from processors.splitter import BilingualSplitter

        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        # Dry-run mode
        if getattr(args, 'dry_run', False):
            print("\n[DRY RUN] Would split bilingual subtitle file:")
            print(f"  Input: {args.input}")
            print(f"  Output directory: {args.output_dir or args.input.parent}")
            print(f"  CJK language label: {args.lang1}")
            print(f"  English language label: {args.lang2}")
            print(f"  Strip formatting: {not args.keep_formatting}")
            print("\n[DRY RUN] No changes made.")
            return 0

        splitter = BilingualSplitter(
            strip_formatting=not getattr(args, 'keep_formatting', False)
        )

        # Check if the file appears to be bilingual
        if not splitter.is_bilingual(args.input):
            logger.warning(f"File does not appear to contain bilingual content: {args.input.name}")
            print("Warning: This file does not appear to be bilingual (no mixed CJK/Latin content detected).")
            print("Proceeding anyway...")

        try:
            lang1_path, lang2_path = splitter.split_file(
                input_path=args.input,
                output_dir=args.output_dir,
                lang1_label=args.lang1,
                lang2_label=args.lang2,
                lang1_format=getattr(args, 'format', 'srt')
            )

            print(f"\n{'='*60}")
            print("SPLIT COMPLETE")
            print(f"{'='*60}")

            if lang1_path:
                print(f"  {args.lang1.upper()}: {lang1_path}")
            else:
                print(f"  {args.lang1.upper()}: No content found")

            if lang2_path:
                print(f"  {args.lang2.upper()}: {lang2_path}")
            else:
                print(f"  {args.lang2.upper()}: No content found")

            return 0

        except Exception as e:
            logger.error(f"Split failed: {e}")
            return 1

    def _handle_convert_pgs(self, args) -> int:
        """Handle convert-pgs command."""
        if not self.pgsrip_wrapper:
            logger.error("PGSRip is not installed. Run: python biss.py setup-pgsrip install")
            return 1

        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        try:
            # Standalone subtitle files (.sup, .idx, .sub) — skip track detection
            if args.input.suffix.lower() in ('.sup', '.idx', '.sub'):
                output_path = args.output or args.input.with_suffix('.srt')
                ocr_lang = args.language or 'eng'
                success = self.pgsrip_wrapper.convert_subtitle_file(
                    args.input, output_path, ocr_lang
                )
                return 0 if success else 1

            # List tracks if requested
            if args.list_tracks:
                pgs_info = self.pgsrip_wrapper.get_pgs_info(args.input)

                print(f"\nPGS tracks in {args.input.name}:")
                if pgs_info['pgs_track_count'] == 0:
                    print("  No PGS tracks found")
                else:
                    for track in pgs_info['tracks']:
                        print(f"  Track {track['track_id']}: {track.get('language', 'unknown')}")
                        if track.get('title'):
                            print(f"    Title: {track['title']}")
                        print(f"    Estimated OCR language: {track['estimated_ocr_language']}")
                        if track['is_default']:
                            print("    [DEFAULT]")
                        if track['is_forced']:
                            print("    [FORCED]")
                        print()

                print(f"Supported OCR languages: {', '.join(pgs_info['supported_ocr_languages'])}")
                return 0

            # Detect PGS tracks
            pgs_tracks = self.pgsrip_wrapper.detect_pgs_tracks(args.input)

            if not pgs_tracks:
                logger.error("No PGS tracks found in the video file")
                return 1

            # Select track to convert
            if args.track:
                track = next((t for t in pgs_tracks if t.track_id == args.track), None)
                if not track:
                    logger.error(f"PGS track {args.track} not found")
                    return 1
            else:
                track = pgs_tracks[0]  # Use first track

            # Determine output path
            if args.output:
                output_path = args.output
            else:
                output_path = args.input.with_suffix('.pgs.srt')

            # Convert PGS track
            success = self.pgsrip_wrapper.convert_pgs_track(
                args.input, track, output_path, args.language
            )

            return 0 if success else 1

        except PGSRipNotInstalledError:
            logger.error("PGSRip is not properly installed. Run: python biss.py setup-pgsrip install")
            return 1
        except Exception as e:
            logger.error(f"PGS conversion failed: {e}")
            return 1

    def _handle_batch_convert_pgs(self, args) -> int:
        """Handle batch-convert-pgs command."""
        if not self.pgsrip_wrapper:
            logger.error("PGSRip is not installed. Run: python biss.py setup-pgsrip install")
            return 1

        if not args.directory.exists():
            logger.error(f"Directory not found: {args.directory}")
            return 1

        try:
            # Find video files
            video_files = FileHandler.find_video_files(args.directory, args.recursive)

            if not video_files:
                logger.warning(f"No video files found in {args.directory}")
                return 0

            # Batch convert PGS subtitles
            results = self.pgsrip_wrapper.batch_convert_pgs(
                video_files, args.output_dir, args.language
            )

            # Print summary
            print(self.pgsrip_wrapper.get_conversion_summary(results))

            return 0 if results['failed_conversions'] == 0 else 1

        except PGSRipNotInstalledError:
            logger.error("PGSRip is not properly installed. Run: python biss.py setup-pgsrip install")
            return 1
        except Exception as e:
            logger.error(f"Batch PGS conversion failed: {e}")
            return 1

    def _handle_setup_pgsrip(self, args) -> int:
        """Handle setup-pgsrip command."""
        try:
            from third_party.setup_pgsrip import PGSRipInstaller

            installer = PGSRipInstaller()

            if args.action == 'install':
                success = installer.install(args.languages)
                return 0 if success else 1
            elif args.action == 'uninstall':
                success = installer.uninstall()
                return 0 if success else 1
            elif args.action == 'check':
                status = installer.check_installation()
                installer._print_installation_summary()
                return 0 if all(status.values()) else 1
            else:
                logger.error(f"Unknown setup action: {args.action}")
                return 1

        except Exception as e:
            logger.error(f"PGSRip setup failed: {e}")
            return 1

    def _handle_interactive(self, args) -> int:
        """Handle interactive command."""
        from .interactive import InteractiveInterface

        interface = InteractiveInterface(use_colors=not args.no_colors)
        return interface.run()

    def _handle_gui(self, args) -> int:
        """Handle GUI command."""
        from .gui import BISSGui

        app = BISSGui()
        app.run()
        return 0

    def _list_video_tracks(self, video_path: Path) -> int:
        """List subtitle tracks in a video file."""
        from core.video_containers import VideoContainerHandler
        from core.track_analyzer import SubtitleTrackAnalyzer

        if not VideoContainerHandler.is_video_container(video_path):
            logger.error(f"Not a supported video container: {video_path}")
            return 1

        # Get subtitle tracks
        tracks = VideoContainerHandler.list_subtitle_tracks(video_path)

        if not tracks:
            print(f"No subtitle tracks found in {video_path.name}")
            return 0

        print(f"\nSubtitle tracks in {video_path.name}:")
        print("=" * 60)

        # Analyze English tracks for dialogue likelihood
        english_tracks = [t for t in tracks if t.language.lower() in {'en', 'eng', 'english'} or
                         'english' in t.title.lower() or not t.language]

        if english_tracks:
            print("\n🔍 ENGLISH TRACK ANALYSIS:")
            print("-" * 40)

            # Convert to analysis format
            track_data = []
            for track in english_tracks:
                track_info = {
                    'track_id': track.track_id,
                    'title': track.title,
                    'language': track.language,
                    'is_default': track.is_default,
                    'is_forced': track.is_forced,
                    'codec': track.codec
                }
                track_data.append(track_info)

            # Analyze tracks
            analyzer = SubtitleTrackAnalyzer()
            scores = analyzer.analyze_tracks(track_data, video_path)

            for score in scores:
                status = "✅ DIALOGUE" if score.is_dialogue_candidate else "❌ NON-DIALOGUE"
                print(f"Track {score.track_id}: {status} (Score: {score.total_score:.3f})")
                print(f"  Title: '{score.title}'")
                print(f"  Events: {score.event_count}")
                print(f"  Reasoning: {'; '.join(score.reasoning[:2])}")  # Show first 2 reasons
                print()

        print("\n📋 ALL TRACKS:")
        print("-" * 40)
        for track in tracks:
            flags = []
            if track.is_default:
                flags.append("DEFAULT")
            if track.is_forced:
                flags.append("FORCED")

            flag_str = f" [{', '.join(flags)}]" if flags else ""

            print(f"Track {track.track_id}: {track.language or 'unknown'} ({track.codec}){flag_str}")
            if track.title:
                print(f"  Title: {track.title}")
            print()

        return 0

    def _handle_extract(self, args) -> int:
        """Handle extract command using mkvextract."""
        import subprocess

        video_path = args.input

        if not video_path.exists():
            logger.error(f"File not found: {video_path}")
            return 1

        if video_path.suffix.lower() != '.mkv':
            logger.error("Extract command only supports MKV files")
            return 1

        # Check if MKVToolNix is available (both mkvextract and mkvinfo)
        missing_tools = []
        for tool in ['mkvextract', 'mkvinfo']:
            try:
                result = subprocess.run([tool, '--version'],
                                       capture_output=True, timeout=5)
                if result.returncode != 0:
                    missing_tools.append(tool)
            except (subprocess.SubprocessError, FileNotFoundError):
                missing_tools.append(tool)

        if missing_tools:
            logger.error(f"MKVToolNix not found (missing: {', '.join(missing_tools)})")
            print("\n" + "=" * 60)
            print("  MKVToolNix is required for the 'extract' command")
            print("=" * 60)
            print("\nPlease install MKVToolNix:")
            print("  - Windows: https://mkvtoolnix.download/downloads.html#windows")
            print("  - macOS:   brew install mkvtoolnix")
            print("  - Linux:   sudo apt install mkvtoolnix (Debian/Ubuntu)")
            print("             sudo dnf install mkvtoolnix (Fedora)")
            print("\nAfter installation, ensure mkvextract and mkvinfo are in your PATH.")
            print("=" * 60 + "\n")
            return 1

        # Get track info using mkvinfo
        try:
            result = subprocess.run(['mkvinfo', str(video_path)],
                                   capture_output=True, timeout=60)
            # Decode with utf-8, ignoring errors for non-UTF8 characters
            mkvinfo_output = result.stdout.decode('utf-8', errors='replace')
        except subprocess.TimeoutExpired:
            logger.error("mkvinfo timed out - the file may be too large or corrupted")
            return 1
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to get track info: {e}")
            return 1

        # Parse tracks from mkvinfo output
        tracks = self._parse_mkvinfo_tracks(mkvinfo_output)

        if args.list:
            # List tracks and exit
            print(f"\nTracks in {video_path.name}:")
            print("=" * 70)
            print(f"{'ID':<4} {'Type':<10} {'Language':<8} {'Codec':<15} {'Name'}")
            print("-" * 70)

            for track in tracks:
                # Safely encode name for console output
                name = track.get('name', '')
                try:
                    # Try to print as-is
                    print(f"{track['id']:<4} {track['type']:<10} {track['language']:<8} "
                          f"{track['codec']:<15} {name}")
                except UnicodeEncodeError:
                    # Fall back to ASCII-safe representation
                    safe_name = name.encode('ascii', errors='replace').decode('ascii')
                    print(f"{track['id']:<4} {track['type']:<10} {track['language']:<8} "
                          f"{track['codec']:<15} {safe_name}")

            print()
            print("To extract tracks, use:")
            print(f"  biss extract \"{video_path}\" --tracks <id> [<id>...]")
            print(f"  biss extract \"{video_path}\" --tracks <id>:output.srt")
            return 0

        # Determine which tracks to extract
        subtitle_tracks = [t for t in tracks if t['type'] == 'subtitles']

        if not subtitle_tracks:
            logger.error("No subtitle tracks found in file")
            return 1

        tracks_to_extract = []

        if args.all:
            # Extract all subtitle tracks
            tracks_to_extract = [(t['id'], None) for t in subtitle_tracks]
        elif args.lang:
            # Extract tracks matching language codes
            lang_codes = set(l.lower() for l in args.lang)
            for track in subtitle_tracks:
                if track['language'].lower() in lang_codes:
                    tracks_to_extract.append((track['id'], None))
            if not tracks_to_extract:
                logger.error(f"No tracks found matching languages: {args.lang}")
                return 1
        elif args.tracks:
            # Extract specific tracks
            for spec in args.tracks:
                if ':' in spec:
                    track_id, output_name = spec.split(':', 1)
                    tracks_to_extract.append((track_id, output_name))
                else:
                    tracks_to_extract.append((spec, None))
        else:
            logger.error("Please specify --list, --all, --lang, or --tracks")
            return 1

        # Determine output directory
        output_dir = args.output_dir if args.output_dir else video_path.parent

        # Build mkvextract command
        extract_args = []
        for track_id, output_name in tracks_to_extract:
            # Find track info
            track_info = next((t for t in tracks if str(t['id']) == str(track_id)), None)

            if not track_info:
                logger.warning(f"Track {track_id} not found, skipping")
                continue

            if output_name:
                output_path = output_dir / output_name
            else:
                # Generate output filename
                ext = '.srt' if track_info['codec'].lower() in ['subrip', 's_text/utf8'] else '.ass'
                lang = track_info['language'] if track_info['language'] else f"track{track_id}"
                output_path = output_dir / f"{video_path.stem}.{lang}.{track_id}{ext}"

            extract_args.append(f"{track_id}:{output_path}")

        if not extract_args:
            logger.error("No valid tracks to extract")
            return 1

        # Run mkvextract
        cmd = ['mkvextract', str(video_path), 'tracks'] + extract_args

        logger.info(f"Extracting {len(extract_args)} track(s)...")
        if args.debug:
            logger.debug(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("Extraction completed successfully!")
                for arg in extract_args:
                    track_id, output = arg.split(':', 1)
                    print(f"  Track {track_id} -> {output}")
                return 0
            else:
                logger.error(f"Extraction failed: {result.stderr}")
                return 1

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return 1

    def _parse_mkvinfo_tracks(self, mkvinfo_output: str) -> list:
        """Parse track information from mkvinfo output."""
        import re

        tracks = []
        current_track = None

        for line in mkvinfo_output.split('\n'):
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

            # Language (prefer IETF BCP 47)
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

        # Don't forget the last track
        if current_track:
            tracks.append(current_track)

        return tracks


def main():
    """Main entry point for CLI."""
    cli = CLIHandler()
    parser = cli.create_parser()
    args = parser.parse_args()

    exit_code = cli.handle_command(args)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
