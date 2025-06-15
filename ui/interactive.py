"""
Interactive menu-driven interface for the Bilingual Subtitle Suite.

This module provides a user-friendly interactive interface for all subtitle
operations with menu navigation and input validation.
"""

import sys
from pathlib import Path
from typing import Optional, List, Tuple
from utils.constants import APP_NAME, APP_VERSION
from utils.logging_config import setup_logging
from processors.merger import BilingualMerger
from processors.converter import EncodingConverter
from processors.realigner import SubtitleRealigner
from processors.batch_processor import BatchProcessor
from third_party import PGSRipWrapper, PGSRipNotInstalledError, is_pgsrip_available

# Try to import curses for enhanced interface
try:
    import curses
    CURSES_AVAILABLE = True
except ImportError:
    CURSES_AVAILABLE = False


class InteractiveInterface:
    """Interactive menu-driven interface for subtitle processing."""
    
    def __init__(self, use_colors: bool = True):
        """
        Initialize the interactive interface.
        
        Args:
            use_colors: Whether to use colored output
        """
        self.use_colors = use_colors and sys.stdout.isatty()
        self.logger = setup_logging(use_colors=self.use_colors)
        
        # Initialize processors
        self.merger = BilingualMerger()
        self.converter = EncodingConverter()
        self.realigner = SubtitleRealigner()
        self.batch_processor = BatchProcessor()

        # Initialize PGSRip wrapper if available
        self.pgsrip_wrapper = None
        if is_pgsrip_available():
            try:
                self.pgsrip_wrapper = PGSRipWrapper()
            except Exception:
                pass  # PGSRip not properly installed
    
    def run(self) -> int:
        """
        Run the interactive interface.
        
        Returns:
            Exit code (0 for success)
        """
        self._print_header()
        
        while True:
            try:
                choice = self._show_main_menu()
                
                if choice == '1':
                    self._handle_merge_subtitles()
                elif choice == '2':
                    self._handle_convert_encoding()
                elif choice == '3':
                    self._handle_realign_subtitles()
                elif choice == '4':
                    self._handle_batch_operations()
                elif choice == '5':
                    self._handle_video_processing()
                elif choice == '6':
                    self._handle_pgs_conversion()
                elif choice == '7':
                    self._show_help()
                elif choice == '0' or choice.lower() == 'q':
                    print("\nGoodbye!")
                    return 0
                else:
                    print("Invalid choice. Please try again.")
                
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user. Goodbye!")
                return 0
            except Exception as e:
                print(f"\nError: {e}")
                input("Press Enter to continue...")
    
    def _print_header(self):
        """Print the application header."""
        if self.use_colors:
            print(f"\033[1;36m{'=' * 60}\033[0m")
            print(f"\033[1;36m{APP_NAME} v{APP_VERSION}\033[0m")
            print(f"\033[1;36m{'=' * 60}\033[0m")
        else:
            print("=" * 60)
            print(f"{APP_NAME} v{APP_VERSION}")
            print("=" * 60)
        print("Interactive Subtitle Processing Interface")
        print()
    
    def _show_main_menu(self) -> str:
        """
        Show the main menu and get user choice.
        
        Returns:
            User's menu choice as string
        """
        print("\nMain Menu:")
        print("1. Merge Bilingual Subtitles")
        print("2. Convert Subtitle Encoding")
        print("3. Realign Subtitle Timing")
        print("4. Batch Operations")
        print("5. Video Processing")
        if self.pgsrip_wrapper:
            print("6. PGS Subtitle Conversion")
        else:
            print("6. PGS Subtitle Conversion (Not Available)")
        print("7. Help & Information")
        print("0. Exit")
        print()
        
        return input("Enter your choice (0-7): ").strip()

    def _get_enhanced_alignment_options(self) -> dict:
        """Get enhanced alignment options from user."""
        print("\n" + "=" * 50)
        print("ENHANCED ALIGNMENT OPTIONS")
        print("=" * 50)

        options = {}

        # Auto-align option
        auto_align = self._get_yes_no("Enable enhanced automatic alignment?", default=False)
        options['auto_align'] = auto_align

        if auto_align:
            # Translation-assisted alignment
            use_translation = self._get_yes_no("Enable translation-assisted alignment?", default=False)
            options['use_translation'] = use_translation

            if use_translation:
                # API key
                import os
                api_key = os.getenv('GOOGLE_TRANSLATE_API_KEY')
                if not api_key:
                    print("\nGoogle Cloud Translation API key required for translation features.")
                    api_key = input("Enter API key (or set GOOGLE_TRANSLATE_API_KEY env var): ").strip()
                    if api_key:
                        options['translation_api_key'] = api_key
                    else:
                        print("Translation features disabled - no API key provided.")
                        options['use_translation'] = False

            # Manual alignment option
            manual_align = self._get_yes_no("Enable interactive anchor point selection?", default=False)
            options['manual_align'] = manual_align

            # Reference language preference
            print("\nReference track preference (when both tracks are same type):")
            print("1. Auto (use track with earlier timestamps)")
            print("2. Chinese track as reference")
            print("3. English track as reference")

            ref_choice = input("Enter choice (1-3, default: 1): ").strip() or "1"
            ref_map = {"1": "auto", "2": "chinese", "3": "english"}
            options['reference_language_preference'] = ref_map.get(ref_choice, "auto")

            # Synchronization strategy
            print("\nGlobal synchronization strategy:")
            print("1. Auto (intelligent strategy selection)")
            print("2. First-line (align first subtitle entries)")
            print("3. Scan (scan forward for best match)")
            print("4. Translation (use translation for matching)")
            print("5. Manual (interactive selection)")

            sync_choice = input("Enter choice (1-5, default: 1): ").strip() or "1"
            sync_map = {"1": "auto", "2": "first-line", "3": "scan", "4": "translation", "5": "manual"}
            options['sync_strategy'] = sync_map.get(sync_choice, "auto")

            # Alignment threshold
            threshold = input("Alignment confidence threshold (0.0-1.0, default: 0.8): ").strip()
            try:
                threshold_val = float(threshold) if threshold else 0.8
                if 0.0 <= threshold_val <= 1.0:
                    options['alignment_threshold'] = threshold_val
                else:
                    print("Invalid threshold, using default 0.8")
                    options['alignment_threshold'] = 0.8
            except ValueError:
                print("Invalid threshold, using default 0.8")
                options['alignment_threshold'] = 0.8

        # PGS conversion options
        print("\nPGS Subtitle Conversion Options:")
        force_pgs = self._get_yes_no("Force PGS conversion even when other subtitles exist?", default=False)
        options['force_pgs'] = force_pgs

        if not force_pgs:
            no_pgs = self._get_yes_no("Disable PGS auto-activation (skip PGS conversion)?", default=False)
            options['no_pgs'] = no_pgs
        else:
            options['no_pgs'] = False

        return options

    def _get_enhanced_alignment_options_with_mixed_detection(self, video_path=None, chinese_sub=None, english_sub=None):
        """
        Get enhanced alignment options with automatic mixed track realignment detection.

        This method automatically enables enhanced realignment when mixed track scenarios
        with major timing misalignment are detected, providing feature parity with CLI mode.

        Args:
            video_path: Path to video file (for embedded track detection)
            chinese_sub: Path to Chinese subtitle file (external)
            english_sub: Path to English subtitle file (external)

        Returns:
            Dictionary of alignment options with automatic mixed realignment enabled if needed
        """
        # Start with standard enhanced alignment options
        options = self._get_enhanced_alignment_options()

        # Detect mixed track scenario
        mixed_scenario_detected = False
        embedded_track_info = None
        external_track_info = None

        if video_path:
            # Check for embedded tracks
            from core.video_containers import VideoContainerHandler
            video_handler = VideoContainerHandler()

            try:
                tracks = video_handler.list_subtitle_tracks(video_path)
                has_embedded_chinese = any(track for track in tracks if 'chi' in track.language.lower() or 'zh' in track.language.lower())
                has_embedded_english = any(track for track in tracks if 'eng' in track.language.lower() or 'en' in track.language.lower())

                # Determine mixed scenario
                if has_embedded_english and chinese_sub:
                    mixed_scenario_detected = True
                    embedded_track_info = "English (embedded)"
                    external_track_info = f"Chinese (external: {chinese_sub.name})"
                elif has_embedded_chinese and english_sub:
                    mixed_scenario_detected = True
                    embedded_track_info = "Chinese (embedded)"
                    external_track_info = f"English (external: {english_sub.name})"

            except Exception as e:
                self.logger.debug(f"Failed to analyze video tracks: {e}")

        # If mixed scenario detected, explain and auto-enable enhanced realignment
        if mixed_scenario_detected:
            print("\n" + "🔍 MIXED TRACK SCENARIO DETECTED" + "=" * 30)
            print("🔍 MIXED TRACK SCENARIO DETECTED")
            print("=" * 60)
            print(f"📺 Embedded track: {embedded_track_info}")
            print(f"📄 External track: {external_track_info}")
            print()
            print("This scenario may require enhanced realignment if the external")
            print("subtitle file has different timing compared to the embedded track.")
            print()
            print("Enhanced realignment will:")
            print("✅ Preserve embedded track timing (video-synchronized)")
            print("🔄 Shift external track timing to match embedded track")
            print("🗑️  Remove mistimed content before alignment point")
            print("🎯 Use semantic matching to find alignment anchor")
            print()

            # Ask user if they want to enable enhanced realignment
            enable_mixed = self._get_yes_no(
                "Enable enhanced realignment for mixed tracks?",
                default=True
            )

            if enable_mixed:
                options['enable_mixed_realignment'] = True
                print("✅ Enhanced mixed track realignment ENABLED")
                print("   The system will automatically detect major timing misalignment")
                print("   and apply intelligent realignment when needed.")
            else:
                options['enable_mixed_realignment'] = False
                print("⚠️  Enhanced mixed track realignment DISABLED")
                print("   Timing preservation will be used (may result in poor alignment)")
        else:
            # No mixed scenario detected, use standard behavior
            options['enable_mixed_realignment'] = False

        return options
    
    def _handle_merge_subtitles(self):
        """Handle bilingual subtitle merging."""
        print("\n" + "=" * 50)
        print("BILINGUAL SUBTITLE MERGING")
        print("=" * 50)
        
        print("\nChoose input method:")
        print("1. Merge two subtitle files")
        print("2. Extract and merge from video file")
        print("0. Back to main menu")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            self._merge_subtitle_files()
        elif choice == '2':
            self._merge_from_video()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")
    
    def _merge_subtitle_files(self):
        """Merge two subtitle files with enhanced alignment options."""
        print("\nMerging subtitle files...")

        chinese_path = self._get_file_path("Chinese subtitle file (optional)", optional=True)
        english_path = self._get_file_path("English subtitle file (optional)", optional=True)

        if not chinese_path and not english_path:
            print("At least one subtitle file must be provided.")
            return

        # Enhanced alignment options
        alignment_options = self._get_enhanced_alignment_options()

        output_path = self._get_output_path("bilingual subtitle", default_ext=".srt")
        output_format = self._get_output_format()

        # Create merger with enhanced options
        merger = BilingualMerger(**alignment_options)

        print(f"\nMerging subtitles...")
        success = merger.merge_subtitle_files(
            chinese_path=chinese_path,
            english_path=english_path,
            output_path=output_path,
            output_format=output_format
        )

        if success:
            print(f"✓ Successfully created: {output_path}")
        else:
            print("✗ Failed to merge subtitles")
    
    def _merge_from_video(self):
        """Extract and merge subtitles from video file with enhanced alignment and automatic mixed track detection."""
        print("\nExtracting and merging from video...")

        video_path = self._get_file_path("Video file")
        if not video_path:
            return

        output_format = self._get_output_format()

        # Optional external subtitle files
        print("\nOptional external subtitle files:")
        chinese_sub = self._get_file_path("Chinese subtitle file (optional)", optional=True)
        english_sub = self._get_file_path("English subtitle file (optional)", optional=True)

        # Processing options
        print("\nProcessing options:")
        prefer_external = self._get_yes_no("Prefer external subtitles over embedded?")

        # Enhanced alignment options with automatic mixed track detection
        alignment_options = self._get_enhanced_alignment_options_with_mixed_detection(
            video_path=video_path,
            chinese_sub=chinese_sub,
            english_sub=english_sub
        )

        # Create merger with enhanced options
        merger = BilingualMerger(**alignment_options)

        print(f"\nProcessing video: {video_path.name}")
        success = merger.process_video(
            video_path=video_path,
            chinese_sub=chinese_sub,
            english_sub=english_sub,
            output_format=output_format,
            prefer_external=prefer_external
        )

        if success:
            print("✓ Successfully processed video")
        else:
            print("✗ Failed to process video")
    
    def _handle_convert_encoding(self):
        """Handle encoding conversion."""
        print("\n" + "=" * 50)
        print("SUBTITLE ENCODING CONVERSION")
        print("=" * 50)
        
        print("\nChoose operation:")
        print("1. Convert single file")
        print("2. Convert directory")
        print("0. Back to main menu")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            self._convert_single_file()
        elif choice == '2':
            self._convert_directory()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")
    
    def _convert_single_file(self):
        """Convert encoding of a single file."""
        print("\nConverting single file...")
        
        file_path = self._get_file_path("Subtitle file to convert")
        if not file_path:
            return
        
        target_encoding = input("Target encoding (default: utf-8): ").strip() or "utf-8"
        keep_backup = self._get_yes_no("Create backup of original file?")
        force_conversion = self._get_yes_no("Force conversion even if already target encoding?")
        
        print(f"\nConverting: {file_path.name}")
        success = self.converter.convert_file(
            file_path=file_path,
            keep_backup=keep_backup,
            force_conversion=force_conversion,
            target_encoding=target_encoding
        )
        
        if success:
            print("✓ File converted successfully")
        else:
            print("- No conversion needed")
    
    def _convert_directory(self):
        """Convert encoding of files in a directory."""
        print("\nConverting directory...")
        
        directory = self._get_directory_path("Directory to process")
        if not directory:
            return
        
        recursive = self._get_yes_no("Process subdirectories recursively?")
        target_encoding = input("Target encoding (default: utf-8): ").strip() or "utf-8"
        keep_backup = self._get_yes_no("Create backup files?")
        force_conversion = self._get_yes_no("Force conversion?")
        parallel = self._get_yes_no("Use parallel processing?")
        
        print(f"\nProcessing directory: {directory}")
        
        from utils.file_operations import FileHandler
        subtitle_files = FileHandler.find_subtitle_files(directory, recursive)
        
        if not subtitle_files:
            print("No subtitle files found.")
            return
        
        print(f"Found {len(subtitle_files)} subtitle files")
        
        results = self.batch_processor.process_subtitles_batch(
            subtitle_paths=subtitle_files,
            operation="convert",
            parallel=parallel,
            keep_backup=keep_backup,
            force_conversion=force_conversion,
            target_encoding=target_encoding
        )
        
        print("\n" + self.batch_processor.get_processing_summary(results))
    
    def _handle_realign_subtitles(self):
        """Handle subtitle realignment."""
        print("\n" + "=" * 50)
        print("SUBTITLE REALIGNMENT")
        print("=" * 50)
        
        print("\nChoose operation:")
        print("1. Realign single pair")
        print("2. Batch realign directory")
        print("3. Interactive alignment")
        print("4. Auto-align using similarity analysis")
        print("5. Translation-assisted alignment")
        print("0. Back to main menu")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            self._realign_single_pair()
        elif choice == '2':
            self._realign_directory()
        elif choice == '3':
            self._interactive_alignment()
        elif choice == '4':
            self._auto_align_subtitles()
        elif choice == '5':
            self._translation_assisted_alignment()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")
    
    def _realign_single_pair(self):
        """Realign a single subtitle pair."""
        print("\nRealigning single pair...")
        
        source_path = self._get_file_path("Source subtitle file")
        if not source_path:
            return
        
        reference_path = self._get_file_path("Reference subtitle file")
        if not reference_path:
            return
        
        # Get alignment indices
        print("\nAlignment options (use 0 for automatic alignment):")
        source_idx = self._get_integer("Source event index", default=0)
        ref_idx = self._get_integer("Reference event index", default=0)
        
        create_backup = self._get_yes_no("Create backup before overwriting?", default=True)
        
        print(f"\nRealigning: {source_path.name}")
        success = self.realigner.align_subtitles(
            source_path=source_path,
            reference_path=reference_path,
            source_align_idx=source_idx,
            ref_align_idx=ref_idx,
            create_backup=create_backup
        )
        
        if success:
            print("✓ Subtitles realigned successfully")
        else:
            print("✗ Failed to realign subtitles")

    def _realign_directory(self):
        """Batch realign subtitle pairs in a directory."""
        print("\nBatch realigning directory...")

        directory = self._get_directory_path("Directory containing subtitle pairs")
        if not directory:
            return

        source_ext = input("Source file extension (e.g., .zh.srt): ").strip()
        reference_ext = input("Reference file extension (e.g., .en.srt): ").strip()

        if not source_ext or not reference_ext:
            print("Both extensions must be provided.")
            return

        output_suffix = input("Output suffix (optional): ").strip()
        create_backup = self._get_yes_no("Create backup files?", default=True)

        print(f"\nProcessing directory: {directory}")
        results = self.batch_processor.process_realign_batch(
            directory=directory,
            source_ext=source_ext,
            reference_ext=reference_ext,
            output_suffix=output_suffix,
            create_backup=create_backup
        )

        print("\n" + self.batch_processor.get_processing_summary(results))

    def _interactive_alignment(self):
        """Interactive alignment with preview."""
        print("\nInteractive alignment...")

        source_path = self._get_file_path("Source subtitle file")
        if not source_path:
            return

        reference_path = self._get_file_path("Reference subtitle file")
        if not reference_path:
            return

        # Get preview
        preview = self.realigner.get_alignment_preview(source_path, reference_path)

        if not preview:
            print("Failed to load subtitle files.")
            return

        # Show preview
        print(f"\nSource: {preview['source']['path']} ({preview['source']['total_events']} events)")
        print("-" * 60)
        for event in preview['source']['preview']:
            print(f"{event['index'] + 1}. [{event['time_range']}]")
            print(f"   {event['text']}")

        print(f"\nReference: {preview['reference']['path']} ({preview['reference']['total_events']} events)")
        print("-" * 60)
        for event in preview['reference']['preview']:
            print(f"{event['index'] + 1}. [{event['time_range']}]")
            print(f"   {event['text']}")

        # Get alignment points
        source_idx = self._get_integer("Source event number to align", min_val=1,
                                     max_val=preview['source']['total_events']) - 1
        ref_idx = self._get_integer("Reference event number to align to", min_val=1,
                                  max_val=preview['reference']['total_events']) - 1

        create_backup = self._get_yes_no("Create backup before overwriting?", default=True)

        print(f"\nRealigning: {source_path.name}")
        success = self.realigner.align_subtitles(
            source_path=source_path,
            reference_path=reference_path,
            source_align_idx=source_idx,
            ref_align_idx=ref_idx,
            create_backup=create_backup
        )

        if success:
            print("✓ Subtitles realigned successfully")
        else:
            print("✗ Failed to realign subtitles")

    def _auto_align_subtitles(self):
        """Auto-align subtitles using similarity analysis."""
        print("\nAuto-aligning subtitles using similarity analysis...")

        source_path = self._get_file_path("Source subtitle file")
        if not source_path:
            return

        reference_path = self._get_file_path("Reference subtitle file")
        if not reference_path:
            return

        output_path = self._get_output_path("Auto-aligned subtitles", default_ext=".srt")
        create_backup = self._get_yes_no("Create backup before overwriting?", default=True)

        # Initialize realigner with auto-align enabled
        from processors.realigner import SubtitleRealigner
        realigner = SubtitleRealigner(auto_align=True)

        print(f"\nAnalyzing subtitle similarity...")
        print("This may take a moment for large files...")

        success = realigner.align_subtitles(
            source_path=source_path,
            reference_path=reference_path,
            output_path=output_path,
            create_backup=create_backup,
            use_auto_align=True
        )

        if success:
            print("✓ Auto-alignment completed successfully")
            print(f"✓ Output saved to: {output_path}")
        else:
            print("✗ Auto-alignment failed")

    def _translation_assisted_alignment(self):
        """Translation-assisted alignment for cross-language subtitles."""
        print("\nTranslation-assisted alignment...")
        print("This feature uses Google Cloud Translation API for cross-language alignment.")

        # Check for API key
        import os
        api_key = os.getenv('GOOGLE_TRANSLATE_API_KEY')
        if not api_key:
            print("\nGoogle Cloud Translation API key required.")
            api_key = input("Enter API key (or set GOOGLE_TRANSLATE_API_KEY env var): ").strip()
            if not api_key:
                print("API key required for translation-assisted alignment.")
                return

        source_path = self._get_file_path("Source subtitle file")
        if not source_path:
            return

        reference_path = self._get_file_path("Reference subtitle file")
        if not reference_path:
            return

        output_path = self._get_output_path("Translation-aligned subtitles", default_ext=".srt")

        # Get target language
        print("\nSupported languages: en (English), zh (Chinese), es (Spanish), fr (French), de (German), ja (Japanese), ko (Korean)")
        target_language = input("Target language code [en]: ").strip() or "en"

        create_backup = self._get_yes_no("Create backup before overwriting?", default=True)

        # Initialize realigner with translation enabled
        from processors.realigner import SubtitleRealigner
        realigner = SubtitleRealigner(use_translation=True, auto_align=True, translation_api_key=api_key)

        print(f"\nStarting translation-assisted alignment...")
        print("This process involves:")
        print("1. Language detection")
        print("2. Text translation (if needed)")
        print("3. Similarity analysis")
        print("4. Automatic alignment")
        print("\nThis may take several minutes depending on file size...")

        success = realigner.align_with_translation(
            source_path=source_path,
            reference_path=reference_path,
            output_path=output_path,
            target_language=target_language
        )

        if success:
            print("✓ Translation-assisted alignment completed successfully")
            print(f"✓ Output saved to: {output_path}")
        else:
            print("✗ Translation-assisted alignment failed")

    def _handle_batch_operations(self):
        """Handle batch operations menu."""
        print("\n" + "=" * 50)
        print("BATCH OPERATIONS")
        print("=" * 50)

        print("\nChoose operation:")
        print("1. Batch convert encodings")
        print("2. Batch merge from videos")
        print("3. Batch realign subtitles")
        print("4. Bulk subtitle alignment (non-combined)")
        print("0. Back to main menu")

        choice = input("\nEnter choice: ").strip()

        if choice == '1':
            self._convert_directory()  # Reuse the convert directory method
        elif choice == '2':
            self._batch_merge_videos()
        elif choice == '3':
            self._realign_directory()  # Reuse the realign directory method
        elif choice == '4':
            self._bulk_subtitle_alignment()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")

    def _batch_merge_videos(self):
        """Batch merge subtitles from multiple videos with enhanced mixed track detection."""
        print("\nBatch merging from videos...")

        directory = self._get_directory_path("Directory containing video files")
        if not directory:
            return

        recursive = self._get_yes_no("Process subdirectories recursively?")
        output_format = self._get_output_format()
        prefer_external = self._get_yes_no("Prefer external subtitles over embedded?")

        # Enhanced alignment options for batch processing
        print("\nEnhanced alignment options for batch processing:")
        print("These options will apply to all videos in the batch.")

        # Get enhanced alignment options (without video-specific detection for batch)
        alignment_options = self._get_enhanced_alignment_options()

        # Ask about mixed track realignment for batch processing
        print("\nMixed Track Realignment for Batch Processing:")
        print("This feature automatically handles videos with embedded subtitles")
        print("and external subtitle files that have major timing misalignment.")
        print()
        enable_mixed_batch = self._get_yes_no(
            "Enable enhanced mixed track realignment for batch processing?",
            default=True
        )
        alignment_options['enable_mixed_realignment'] = enable_mixed_batch

        if enable_mixed_batch:
            print("✅ Enhanced mixed track realignment ENABLED for batch")
            print("   Will automatically detect and fix timing misalignment in mixed scenarios")
        else:
            print("⚠️  Enhanced mixed track realignment DISABLED for batch")

        print(f"\nProcessing directory: {directory}")

        from utils.file_operations import FileHandler
        video_files = FileHandler.find_video_files(directory, recursive)

        if not video_files:
            print("No video files found.")
            return

        print(f"Found {len(video_files)} video files")

        # Use enhanced batch processor with alignment options
        from processors.batch_processor import BatchProcessor
        enhanced_batch_processor = BatchProcessor()

        results = enhanced_batch_processor.process_directory_interactive(
            directory=directory,
            pattern="*.mkv",  # Focus on video files
            merger_options=alignment_options
        )

        # Print enhanced summary
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

    def _bulk_subtitle_alignment(self):
        """Bulk alignment of subtitle files without combining them."""
        print("\nBulk subtitle alignment (non-combined)...")
        print("This feature aligns timing of source subtitles to match reference subtitles")
        print("without combining them into bilingual files.\n")

        # Get source directory
        source_dir = self._get_directory_path("Source directory (containing subtitles to align)")
        if not source_dir:
            return

        # Get source pattern
        source_pattern = input("Source file pattern (e.g., *.zh.srt): ").strip()
        if not source_pattern:
            print("Source pattern is required.")
            return

        # Get reference pattern or directory
        print("\nReference subtitles:")
        print("1. Use pattern in same directory")
        print("2. Use separate reference directory")

        ref_choice = input("Enter choice (1-2): ").strip()

        reference_dir = None
        reference_pattern = None

        if ref_choice == "1":
            reference_pattern = input("Reference file pattern (e.g., *.en.srt): ").strip()
            if not reference_pattern:
                print("Reference pattern is required.")
                return
        elif ref_choice == "2":
            reference_dir = self._get_directory_path("Reference directory")
            if not reference_dir:
                return
            reference_pattern = input("Reference file pattern (e.g., *.en.srt): ").strip()
            if not reference_pattern:
                print("Reference pattern is required.")
                return
        else:
            print("Invalid choice.")
            return

        # Get output directory
        use_output_dir = self._get_yes_no("Use separate output directory?", default=True)
        output_dir = None
        if use_output_dir:
            output_dir = self._get_directory_path("Output directory")
            if not output_dir:
                return

        # Enhanced alignment options
        alignment_options = self._get_enhanced_alignment_options()

        # Backup options
        create_backup = self._get_yes_no("Create backup files (.bak)?", default=True)

        # Interactive confirmation
        auto_confirm = self._get_yes_no("Auto-confirm all operations?", default=False)

        print(f"\nProcessing bulk alignment...")
        print(f"Source: {source_dir} / {source_pattern}")
        if reference_dir:
            print(f"Reference: {reference_dir} / {reference_pattern}")
        else:
            print(f"Reference: {source_dir} / {reference_pattern}")
        if output_dir:
            print(f"Output: {output_dir}")
        else:
            print("Output: In-place (overwrite source files)")

        # This would call the new bulk alignment processor
        # For now, show what would be processed
        from pathlib import Path
        import glob

        source_files = list(Path(source_dir).glob(source_pattern))
        print(f"\nFound {len(source_files)} source files to align")

        if not source_files:
            print("No source files found matching pattern.")
            return

        # Show first few files as preview
        print("\nPreview of files to process:")
        for i, file in enumerate(source_files[:5]):
            print(f"  {i+1}. {file.name}")
        if len(source_files) > 5:
            print(f"  ... and {len(source_files) - 5} more files")

        if not auto_confirm:
            proceed = self._get_yes_no("Proceed with bulk alignment?")
            if not proceed:
                print("Operation cancelled.")
                return

        print("\n⚠️ Bulk alignment feature implementation in progress...")
        print("This feature will be available in the next update.")

    def _handle_video_processing(self):
        """Handle video processing menu."""
        print("\n" + "=" * 50)
        print("VIDEO PROCESSING")
        print("=" * 50)

        print("\nChoose operation:")
        print("1. Process single video")
        print("2. Batch process videos")
        print("3. List video subtitle tracks")
        print("0. Back to main menu")

        choice = input("\nEnter choice: ").strip()

        if choice == '1':
            self._merge_from_video()  # Reuse the merge from video method
        elif choice == '2':
            self._batch_merge_videos()  # Reuse the batch merge method
        elif choice == '3':
            self._list_video_tracks()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")

    def _list_video_tracks(self):
        """List subtitle tracks in a video file."""
        print("\nListing video subtitle tracks...")

        video_path = self._get_file_path("Video file")
        if not video_path:
            return

        from core.video_containers import VideoContainerHandler

        if not VideoContainerHandler.is_video_container(video_path):
            print("File is not a supported video container.")
            return

        print(f"\nAnalyzing: {video_path.name}")
        tracks = VideoContainerHandler.list_subtitle_tracks(video_path)

        if not tracks:
            print("No subtitle tracks found.")
            return

        print(f"\nFound {len(tracks)} subtitle tracks:")
        print("-" * 60)
        for track in tracks:
            print(f"Track {track.track_id}: {track.codec}")
            if track.language:
                print(f"  Language: {track.language}")
            if track.title:
                print(f"  Title: {track.title}")
            if track.is_default:
                print("  [DEFAULT]")
            if track.is_forced:
                print("  [FORCED]")
            print()

    def _handle_pgs_conversion(self):
        """Handle PGS subtitle conversion menu."""
        if not self.pgsrip_wrapper:
            print("\n" + "=" * 50)
            print("PGS SUBTITLE CONVERSION - NOT AVAILABLE")
            print("=" * 50)
            print("\nPGSRip is not installed or not properly configured.")
            print("To install PGSRip, run:")
            print("  python biss.py setup-pgsrip install")
            print("\nOr use the command line:")
            print("  python third_party/setup_pgsrip.py install")
            return

        print("\n" + "=" * 50)
        print("PGS SUBTITLE CONVERSION")
        print("=" * 50)

        print("\nChoose operation:")
        print("1. Convert PGS from single video")
        print("2. Batch convert PGS from multiple videos")
        print("3. List PGS tracks in video")
        print("4. Check PGSRip installation")
        print("0. Back to main menu")

        choice = input("\nEnter choice: ").strip()

        if choice == '1':
            self._convert_single_pgs()
        elif choice == '2':
            self._batch_convert_pgs()
        elif choice == '3':
            self._list_pgs_tracks()
        elif choice == '4':
            self._check_pgsrip_status()
        elif choice == '0':
            return
        else:
            print("Invalid choice.")

    def _convert_single_pgs(self):
        """Convert PGS subtitles from a single video."""
        print("\nConverting PGS subtitles from single video...")

        video_path = self._get_file_path("Video file with PGS subtitles")
        if not video_path:
            return

        try:
            # Get PGS tracks
            pgs_tracks = self.pgsrip_wrapper.detect_pgs_tracks(video_path)

            if not pgs_tracks:
                print("No PGS tracks found in the video file.")
                return

            print(f"\nFound {len(pgs_tracks)} PGS track(s):")
            for i, track in enumerate(pgs_tracks, 1):
                print(f"{i}. Track {track.track_id}")
                if track.language:
                    print(f"   Language: {track.language}")
                if track.title:
                    print(f"   Title: {track.title}")
                print(f"   Estimated OCR language: {track.estimated_language}")
                if track.is_default:
                    print("   [DEFAULT]")
                if track.is_forced:
                    print("   [FORCED]")
                print()

            # Select track
            if len(pgs_tracks) == 1:
                selected_track = pgs_tracks[0]
                print(f"Using track {selected_track.track_id}")
            else:
                track_num = self._get_integer("Select track number", min_val=1, max_val=len(pgs_tracks))
                selected_track = pgs_tracks[track_num - 1]

            # Get OCR language
            supported_langs = self.pgsrip_wrapper.get_supported_languages()
            print(f"\nSupported OCR languages: {', '.join(supported_langs)}")

            ocr_language = input(f"OCR language [{selected_track.estimated_language}]: ").strip()
            if not ocr_language:
                ocr_language = selected_track.estimated_language

            if ocr_language not in supported_langs:
                print(f"Warning: {ocr_language} may not be supported")

            # Get output path
            output_path = self._get_output_path("PGS conversion", default_ext=".srt")

            # Convert
            print(f"\nConverting PGS track {selected_track.track_id} using {ocr_language} OCR...")
            success = self.pgsrip_wrapper.convert_pgs_track(
                video_path, selected_track, output_path, ocr_language
            )

            if success:
                print(f"✅ Successfully converted to: {output_path}")
            else:
                print("✗ Conversion failed")

        except Exception as e:
            print(f"Error: {e}")

    def _batch_convert_pgs(self):
        """Batch convert PGS subtitles from multiple videos."""
        print("\nBatch converting PGS subtitles...")

        directory = self._get_directory_path("Directory containing video files")
        if not directory:
            return

        recursive = self._get_yes_no("Process subdirectories recursively?")

        # Get OCR language
        supported_langs = self.pgsrip_wrapper.get_supported_languages()
        print(f"\nSupported OCR languages: {', '.join(supported_langs)}")
        ocr_language = input("OCR language (leave empty for auto-detection): ").strip()

        if ocr_language and ocr_language not in supported_langs:
            print(f"Warning: {ocr_language} may not be supported")

        # Get output directory
        use_output_dir = self._get_yes_no("Use separate output directory?")
        output_dir = None
        if use_output_dir:
            output_dir = self._get_directory_path("Output directory")

        print(f"\nProcessing directory: {directory}")

        from utils.file_operations import FileHandler
        video_files = FileHandler.find_video_files(directory, recursive)

        if not video_files:
            print("No video files found.")
            return

        print(f"Found {len(video_files)} video files")

        # Batch convert
        results = self.pgsrip_wrapper.batch_convert_pgs(
            video_files, output_dir, ocr_language if ocr_language else None
        )

        print("\n" + self.pgsrip_wrapper.get_conversion_summary(results))

    def _list_pgs_tracks(self):
        """List PGS tracks in a video file."""
        print("\nListing PGS tracks...")

        video_path = self._get_file_path("Video file")
        if not video_path:
            return

        try:
            pgs_info = self.pgsrip_wrapper.get_pgs_info(video_path)

            print(f"\nPGS tracks in {video_path.name}:")
            print("-" * 60)

            if pgs_info['pgs_track_count'] == 0:
                print("No PGS tracks found.")
            else:
                for track in pgs_info['tracks']:
                    print(f"Track {track['track_id']}")
                    if track.get('language'):
                        print(f"  Language: {track['language']}")
                    if track.get('title'):
                        print(f"  Title: {track['title']}")
                    print(f"  Estimated OCR language: {track['estimated_ocr_language']}")
                    if track['is_default']:
                        print("  [DEFAULT]")
                    if track['is_forced']:
                        print("  [FORCED]")
                    print()

            print(f"Supported OCR languages: {', '.join(pgs_info['supported_ocr_languages'])}")

        except Exception as e:
            print(f"Error: {e}")

    def _check_pgsrip_status(self):
        """Check PGSRip installation status."""
        print("\nPGSRip Installation Status:")
        print("-" * 40)

        if self.pgsrip_wrapper:
            status = self.pgsrip_wrapper.get_installation_status()

            if status['installed']:
                print("✅ PGSRip is installed and ready")
                print(f"Supported languages: {', '.join(status['languages'])}")

                config = status.get('config', {})
                if 'version' in config:
                    print(f"Version: {config['version']}")
                if 'system' in config:
                    print(f"System: {config['system']}")
            else:
                print("❌ PGSRip installation issue:")
                print(f"   {status.get('error', 'Unknown error')}")
        else:
            print("❌ PGSRip is not available")
            print("   Run: python biss.py setup-pgsrip install")

    def _show_help(self):
        """Show help and information."""
        print("\n" + "=" * 50)
        print("HELP & INFORMATION")
        print("=" * 50)

        print(f"""
{APP_NAME} v{APP_VERSION}

This application provides comprehensive subtitle processing capabilities:

1. BILINGUAL SUBTITLE MERGING
   - Merge bilingual subtitles (Chinese-English, Japanese-English, Korean-English, etc.)
   - Extract subtitles from video containers (MKV, MP4, etc.)
   - Support for SRT, ASS, and VTT formats
   - Intelligent timing optimization

2. ENCODING CONVERSION
   - Convert subtitle files to UTF-8 encoding
   - Special support for Asian encodings (GB18030, GBK, Big5, Shift-JIS)
   - Automatic encoding detection
   - Batch processing capabilities

3. SUBTITLE REALIGNMENT
   - Align subtitle timing based on reference files
   - Interactive alignment point selection
   - Automatic alignment using similarity analysis
   - Translation-assisted alignment for cross-language subtitles
   - Google Cloud Translation API integration
   - Batch processing for multiple pairs

4. VIDEO PROCESSING
   - Extract embedded subtitle tracks
   - Language detection and filtering
   - Support for multiple video container formats
   - Plex-compatible output naming

5. BATCH OPERATIONS
   - Process multiple files simultaneously
   - Parallel processing for encoding conversion
   - Progress tracking and error reporting
   - Comprehensive logging

6. PGS SUBTITLE CONVERSION (Optional)
   - Convert PGS (Presentation Graphic Stream) subtitles to SRT
   - OCR support for multiple languages (Chinese, English, Japanese)
   - Automatic language detection and track selection
   - Batch processing for multiple video files
   - Requires PGSRip installation

SUPPORTED FORMATS:
- Video: MKV, MP4, AVI, MOV, and more
- Subtitles: SRT, ASS, SSA, VTT, PGS (with PGSRip)
- Encodings: UTF-8, GB18030, GBK, Big5, and more

For more information, visit the project documentation.
        """)

        # Show encoding detection info
        detection_info = self.converter.get_detection_info()
        print("\nENCODING DETECTION LIBRARIES:")
        if detection_info['charset_normalizer']:
            print("  ✓ charset-normalizer (recommended)")
        else:
            print("  ✗ charset-normalizer not available")

        if detection_info['chardet']:
            print("  ✓ chardet (fallback)")
        else:
            print("  ✗ chardet not available")

        if not detection_info['charset_normalizer'] and not detection_info['chardet']:
            print("  ⚠ No automatic encoding detection available")
            print("    Install with: pip install charset-normalizer")

    # Helper methods for user input
    def _get_file_path(self, prompt: str, optional: bool = False) -> Optional[Path]:
        """Get a file path from user input with validation."""
        while True:
            path_str = input(f"{prompt}: ").strip()

            if not path_str and optional:
                return None

            if not path_str:
                print("Path cannot be empty.")
                continue

            path = Path(path_str)
            if not path.exists():
                print(f"File not found: {path}")
                continue

            if not path.is_file():
                print(f"Path is not a file: {path}")
                continue

            return path

    def _get_directory_path(self, prompt: str) -> Optional[Path]:
        """Get a directory path from user input with validation."""
        while True:
            path_str = input(f"{prompt}: ").strip()

            if not path_str:
                print("Path cannot be empty.")
                continue

            path = Path(path_str)
            if not path.exists():
                print(f"Directory not found: {path}")
                continue

            if not path.is_dir():
                print(f"Path is not a directory: {path}")
                continue

            return path

    def _get_output_path(self, description: str, default_ext: str = ".srt") -> Path:
        """Get an output path from user input."""
        path_str = input(f"Output path for {description}: ").strip()

        if not path_str:
            return Path(f"output{default_ext}")

        path = Path(path_str)
        if not path.suffix:
            path = path.with_suffix(default_ext)

        return path

    def _get_output_format(self) -> str:
        """Get output format choice from user."""
        while True:
            format_choice = input("Output format (srt/ass) [srt]: ").strip().lower()

            if not format_choice:
                return "srt"

            if format_choice in ['srt', 'ass']:
                return format_choice

            print("Invalid format. Choose 'srt' or 'ass'.")

    def _get_yes_no(self, prompt: str, default: bool = False) -> bool:
        """Get a yes/no answer from user."""
        default_str = "Y/n" if default else "y/N"

        while True:
            answer = input(f"{prompt} ({default_str}): ").strip().lower()

            if not answer:
                return default

            if answer in ['y', 'yes']:
                return True
            elif answer in ['n', 'no']:
                return False
            else:
                print("Please answer 'y' or 'n'.")

    def _get_integer(self, prompt: str, default: int = 0, min_val: int = 0,
                    max_val: Optional[int] = None) -> int:
        """Get an integer from user input with validation."""
        while True:
            value_str = input(f"{prompt} [{default}]: ").strip()

            if not value_str:
                return default

            try:
                value = int(value_str)

                if value < min_val:
                    print(f"Value must be at least {min_val}.")
                    continue

                if max_val is not None and value > max_val:
                    print(f"Value must be at most {max_val}.")
                    continue

                return value

            except ValueError:
                print("Please enter a valid integer.")
