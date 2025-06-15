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
            description=APP_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Merge bilingual subtitles
  biss merge movie.mkv --output bilingual.srt

  # Convert subtitle encoding
  biss convert subtitle.srt --encoding utf-8

  # Realign subtitles
  biss realign source.srt reference.srt

  # Batch convert directory
  biss batch-convert /media/movies --recursive

  # Interactive mode
  biss interactive
            """
        )
        
        parser.add_argument('--version', action='version', version=f'{APP_NAME} {APP_VERSION}')
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
        parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
        
        # Create subparsers for different operations
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Merge command
        self._add_merge_parser(subparsers)
        
        # Convert command
        self._add_convert_parser(subparsers)
        
        # Realign command
        self._add_realign_parser(subparsers)
        
        # Batch commands
        self._add_batch_parsers(subparsers)

        # PGS conversion commands
        self._add_pgs_parsers(subparsers)

        # Interactive command
        self._add_interactive_parser(subparsers)
        
        return parser
    
    def _add_merge_parser(self, subparsers):
        """Add merge command parser."""
        merge_parser = subparsers.add_parser(
            'merge',
            help='Merge bilingual subtitles (Chinese-English, Japanese-English, etc.)',
            description='Merge subtitle files or extract from video containers'
        )
        
        merge_parser.add_argument('input', type=Path, help='Video file or subtitle file')
        merge_parser.add_argument('-c', '--chinese', type=Path, help='Foreign language subtitle file (Chinese, Japanese, Korean, etc.)')
        merge_parser.add_argument('-e', '--english', type=Path, help='English subtitle file')
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
                                help='Enable automatic alignment using advanced methods')
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
                                  help='Enable automatic alignment using similarity analysis')
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

        # Enhanced alignment options for batch processing
        batch_merge_parser.add_argument('--auto-align', action='store_true',
                                      help='Enable automatic alignment using advanced methods')
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
                                       help='Enable automatic alignment using advanced methods')
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

    def _add_pgs_parsers(self, subparsers):
        """Add PGS conversion command parsers."""
        # Convert PGS
        convert_pgs_parser = subparsers.add_parser(
            'convert-pgs',
            help='Convert PGS subtitles to SRT format',
            description='Convert PGS (Presentation Graphic Stream) subtitles to SRT using OCR'
        )

        convert_pgs_parser.add_argument('input', type=Path, help='Video file with PGS subtitles')
        convert_pgs_parser.add_argument('-o', '--output', type=Path, help='Output SRT file path')
        convert_pgs_parser.add_argument('-l', '--language',
                                      choices=['eng', 'chi_sim', 'chi_tra'],
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
                                            choices=['eng', 'chi_sim', 'chi_tra'],
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
    
    def _add_interactive_parser(self, subparsers):
        """Add interactive command parser."""
        interactive_parser = subparsers.add_parser(
            'interactive',
            help='Launch interactive mode',
            description='Launch interactive menu-driven interface'
        )
        
        interactive_parser.add_argument('--no-colors', action='store_true',
                                      help='Disable colored output')
    
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
            elif args.command == 'convert-pgs':
                return self._handle_convert_pgs(args)
            elif args.command == 'batch-convert-pgs':
                return self._handle_batch_convert_pgs(args)
            elif args.command == 'setup-pgsrip':
                return self._handle_setup_pgsrip(args)
            elif args.command == 'interactive':
                return self._handle_interactive(args)
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
        """Handle merge command."""
        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        # Handle track listing
        if args.list_tracks:
            return self._list_video_tracks(args.input)

        # Create merger with enhanced alignment options if specified
        if hasattr(args, 'auto_align') and (args.auto_align or args.use_translation or args.manual_align):
            merger = BilingualMerger(
                auto_align=args.auto_align,
                use_translation=args.use_translation,
                alignment_threshold=args.alignment_threshold,
                translation_api_key=args.translation_api_key,
                manual_align=args.manual_align,
                sync_strategy=args.sync_strategy,
                reference_language_preference=args.reference_language,
                force_pgs=getattr(args, 'force_pgs', False),
                no_pgs=getattr(args, 'no_pgs', False),
                enable_mixed_realignment=getattr(args, 'enable_mixed_realignment', False)
            )
            logger.info(f"Using enhanced alignment: auto_align={args.auto_align}, "
                       f"use_translation={args.use_translation}, manual_align={args.manual_align}, "
                       f"sync_strategy={args.sync_strategy}, threshold={args.alignment_threshold}")
        else:
            # Create merger with PGS flags even for basic usage
            merger = BilingualMerger(
                force_pgs=getattr(args, 'force_pgs', False),
                no_pgs=getattr(args, 'no_pgs', False)
            )

        # Check if input is video or subtitle
        from core.video_containers import VideoContainerHandler

        if VideoContainerHandler.is_video_container(args.input):
            # Process video file
            success = merger.process_video(
                video_path=args.input,
                chinese_sub=args.chinese,
                english_sub=args.english,
                output_format=args.format,
                output_path=args.output,
                chinese_track=args.chinese_track,
                english_track=args.english_track,
                remap_chinese=args.remap_chinese,
                remap_english=args.remap_english,
                prefer_external=args.prefer_external,
                prefer_embedded=args.prefer_embedded
            )
        else:
            # Process subtitle files directly
            if not args.chinese and not args.english:
                logger.error("For subtitle input, specify --chinese and/or --english files")
                return 1

            # Let the merger determine the appropriate filename based on detected languages
            output_path = args.output  # None if not specified, merger will handle dynamic naming
            success = merger.merge_subtitle_files(
                chinese_path=args.chinese,
                english_path=args.english,
                output_path=output_path,
                output_format=args.format
            )

        return 0 if success else 1

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

        # Use interactive processing for enhanced user control
        results = batch_processor.process_directory_interactive(
            directory=args.directory,
            pattern="*.mkv",  # Focus on video files
            merger_options=merger_options if merger_options else None
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

    def _handle_convert_pgs(self, args) -> int:
        """Handle convert-pgs command."""
        if not self.pgsrip_wrapper:
            logger.error("PGSRip is not installed. Run: python biss.py setup-pgsrip install")
            return 1

        if not args.input.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        try:
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


def main():
    """Main entry point for CLI."""
    cli = CLIHandler()
    parser = cli.create_parser()
    args = parser.parse_args()

    exit_code = cli.handle_command(args)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
