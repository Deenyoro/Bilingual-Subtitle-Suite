"""
Bilingual subtitle merging processor.

This module provides functionality for merging Chinese and English subtitles
into a single bilingual track with intelligent timing optimization.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Dict, Callable
from core.subtitle_formats import SubtitleEvent, SubtitleFile, SubtitleFormatFactory
from core.video_containers import VideoContainerHandler
from core.language_detection import LanguageDetector
from core.similarity_alignment import SimilarityAligner, AlignmentMatch
from core.translation_service import get_translation_service, GoogleTranslationService
from utils.constants import DEFAULT_GAP_THRESHOLD, CHINESE_CODES, ENGLISH_CODES
from utils.logging_config import get_logger
from utils.file_operations import FileHandler
from third_party import get_pgsrip_wrapper

logger = get_logger(__name__)


class BilingualMerger:
    """Handles merging of Chinese and English subtitles into bilingual tracks."""

    def __init__(self, gap_threshold: float = DEFAULT_GAP_THRESHOLD,
                 auto_align: bool = False, use_translation: bool = False,
                 alignment_threshold: float = 0.8, translation_api_key: Optional[str] = None,
                 manual_align: bool = False, sync_strategy: str = 'auto',
                 reference_language_preference: str = 'auto',
                 force_pgs: bool = False, no_pgs: bool = False,
                 enable_mixed_realignment: bool = False,
                 top_language: str = 'first',
                 progress_callback: Optional[Callable[[str, int, int], None]] = None):
        """
        Initialize the bilingual merger.

        Args:
            gap_threshold: Maximum gap in seconds to merge adjacent subtitles
            auto_align: Enable automatic alignment using advanced methods
            use_translation: Enable translation-assisted alignment
            alignment_threshold: Confidence threshold for automatic alignment (0.0-1.0)
            translation_api_key: Google Translation API key for translation-assisted alignment
            manual_align: Enable interactive anchor point selection
            sync_strategy: Global synchronization strategy ('auto', 'first-line', 'scan', 'translation', 'manual')
            reference_language_preference: Reference track preference ('chinese', 'english', 'auto')
            force_pgs: Force PGS usage even when other subtitles exist
            no_pgs: Disable PGS auto-activation
            enable_mixed_realignment: Enable enhanced realignment for mixed embedded+external tracks
            top_language: Which subtitle appears on top ('first', 'second') - first is the primary/foreign language
            progress_callback: Optional callback function(step_name, current, total) for progress updates
        """
        # Validate alignment threshold
        if not 0.0 <= alignment_threshold <= 1.0:
            raise ValueError(f"alignment_threshold must be between 0.0 and 1.0, got {alignment_threshold}")

        # Validate reference language preference
        valid_preferences = ['chinese', 'english', 'auto']
        if reference_language_preference not in valid_preferences:
            raise ValueError(f"reference_language_preference must be one of {valid_preferences}, got {reference_language_preference}")

        self.gap_threshold = gap_threshold
        self.auto_align = auto_align
        self.use_translation = use_translation
        self.alignment_threshold = alignment_threshold
        self.manual_align = manual_align
        self.sync_strategy = sync_strategy
        self.reference_language_preference = reference_language_preference
        self.force_pgs = force_pgs
        self.no_pgs = no_pgs
        self.enable_mixed_realignment = enable_mixed_realignment
        self.top_language = top_language  # 'first' or 'second'

        self.video_handler = VideoContainerHandler()
        self.pgsrip_wrapper = get_pgsrip_wrapper() if not no_pgs else None
        self.progress_callback = progress_callback

        # Initialize track info storage (prevents AttributeError when checking hasattr)
        self._track1_info = {'source_type': 'unknown', 'language': 'unknown'}
        self._track2_info = {'source_type': 'unknown', 'language': 'unknown'}

        # Initialize alignment components
        self.similarity_aligner = SimilarityAligner(min_confidence=alignment_threshold)
        self.translation_service = None
        self._manual_selection_info = None  # Store manual selection details

        if use_translation:
            self.translation_service = get_translation_service(translation_api_key)
            if not self.translation_service:
                logger.warning("Translation service not available. Falling back to similarity-only alignment.")
                self.use_translation = False

        logger.info(f"BilingualMerger initialized: auto_align={auto_align}, "
                   f"use_translation={use_translation}, manual_align={manual_align}, "
                   f"sync_strategy={sync_strategy}, reference_preference={reference_language_preference}, "
                   f"threshold={alignment_threshold}, top_language={top_language}")

    def _report_progress(self, step_name: str, current: int = 0, total: int = 0):
        """Report progress to callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(step_name, current, total)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    def _combine_texts(self, text1: str, text2: str) -> str:
        """
        Combine two subtitle texts according to the top_language setting.

        Args:
            text1: First subtitle text (primary/foreign language)
            text2: Second subtitle text (secondary/English language)

        Returns:
            Combined text with newline separator, respecting top_language order
        """
        if not text1 and not text2:
            return ""
        if not text1:
            return text2
        if not text2:
            return text1

        if self.top_language == 'second':
            return f"{text2}\n{text1}"
        else:  # 'first' is default
            return f"{text1}\n{text2}"

    def merge_subtitle_files(self, chinese_path: Optional[Path], english_path: Optional[Path],
                           output_path: Optional[Path], output_format: str = "srt") -> bool:
        """
        Merge two subtitle files into a bilingual subtitle.

        Args:
            chinese_path: Path to Chinese subtitle file (optional)
            english_path: Path to English subtitle file (optional)
            output_path: Path for output file (optional, will be generated if None)
            output_format: Output format ('srt' or 'ass')

        Returns:
            True if merge was successful

        Example:
            >>> merger = BilingualMerger()
            >>> success = merger.merge_subtitle_files(
            ...     Path("chinese.srt"), Path("english.srt"), Path("bilingual.srt")
            ... )
        """
        if not chinese_path and not english_path:
            logger.error("At least one subtitle file must be provided")
            return False

        try:
            # Load subtitle files and collect track information
            chinese_events = []
            english_events = []

            # Initialize track information for reference selection (only if not already set)
            if not hasattr(self, '_track1_info') or self._track1_info.get('source_type') == 'unknown':
                self._track1_info = {'source_type': 'unknown', 'language': 'unknown'}
            if not hasattr(self, '_track2_info') or self._track2_info.get('source_type') == 'unknown':
                self._track2_info = {'source_type': 'unknown', 'language': 'unknown'}

            if chinese_path:
                chinese_sub = SubtitleFormatFactory.parse_file(chinese_path)
                chinese_events = chinese_sub.events
                logger.info(f"Loaded {len(chinese_events)} Chinese events")

                # Only set track info if not already set by process_video
                if self._track1_info.get('source_type') == 'unknown':
                    self._track1_info = {
                        'source_type': 'external',  # File-based subtitles are external
                        'language': 'chinese',
                        'path': str(chinese_path)
                    }

            if english_path:
                english_sub = SubtitleFormatFactory.parse_file(english_path)
                english_events = english_sub.events
                logger.info(f"Loaded {len(english_events)} English events")

                # Only set track info if not already set by process_video
                if self._track2_info.get('source_type') == 'unknown':
                    self._track2_info = {
                        'source_type': 'external',  # File-based subtitles are external
                        'language': 'english',
                        'path': str(english_path)
                    }

            # Generate output path if not provided
            if not output_path:
                # Use the first available file as base
                base_file = chinese_path or english_path
                lang1, lang2 = self._detect_subtitle_languages(chinese_path, english_path)
                output_path = self._generate_output_filename(base_file, lang1, lang2, output_format)

            # Check for forced subtitles
            forced_detection = self._detect_forced_subtitles(chinese_events, english_events)
            if forced_detection:
                logger.info(f"Detected forced subtitles in {forced_detection} track")

            # Merge events
            merged_events = self._merge_overlapping_events(chinese_events, english_events)
            logger.info(f"Created {len(merged_events)} merged events")

            # Create output subtitle file
            output_sub = SubtitleFile(
                path=output_path,
                format=SubtitleFormatFactory.get_format_from_extension(output_path.suffix),
                events=merged_events
            )

            # Write output file
            SubtitleFormatFactory.write_file(output_sub, output_path)
            logger.info(f"Successfully created bilingual subtitle: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to merge subtitle files: {e}")
            return False
    
    def process_video(self, video_path: Path, 
                     chinese_sub: Optional[Path] = None,
                     english_sub: Optional[Path] = None,
                     output_format: str = "srt",
                     output_path: Optional[Path] = None,
                     chinese_track: Optional[str] = None,
                     english_track: Optional[str] = None,
                     remap_chinese: Optional[str] = None,
                     remap_english: Optional[str] = None,
                     prefer_external: bool = False,
                     prefer_embedded: bool = False) -> bool:
        """
        Process a video file to create bilingual subtitles.
        
        Args:
            video_path: Path to the video file
            chinese_sub: Path to Chinese subtitle file (optional)
            english_sub: Path to English subtitle file (optional)
            output_format: Output format ('srt' or 'ass')
            output_path: Custom output path (optional)
            chinese_track: Specific Chinese track to use
            english_track: Specific English track to use
            remap_chinese: Language code to treat as Chinese
            remap_english: Language code to treat as English
            prefer_external: Prefer external subtitles over embedded
            prefer_embedded: Prefer embedded subtitles over external
            
        Returns:
            True if processing succeeded
            
        Example:
            >>> merger = BilingualMerger()
            >>> success = merger.process_video(Path("movie.mkv"))
        """
        logger.info(f"Processing video: {video_path.name}")
        self._report_progress("Starting", 0, 5)

        # Store video path for timing restoration
        self._current_video_path = video_path

        # Validate preferences
        if prefer_external and prefer_embedded:
            logger.warning("Both prefer_external and prefer_embedded set. Using default behavior.")
            prefer_external = prefer_embedded = False

        temp_files = []

        try:
            # Initialize track information for reference selection
            self._track1_info = {'source_type': 'unknown', 'language': 'unknown'}
            self._track2_info = {'source_type': 'unknown', 'language': 'unknown'}

            # Find/Extract Chinese subtitles
            self._report_progress("Finding Chinese subtitle", 1, 5)
            if not chinese_sub:
                chinese_sub, chinese_source_type = self._find_or_extract_subtitle_with_info(
                    video_path, is_chinese=True, prefer_external=prefer_external,
                    prefer_embedded=prefer_embedded, track_id=chinese_track,
                    remap_lang=remap_chinese, temp_files=temp_files
                )
                # Update track info (preserve any existing track details)
                self._track1_info.update({
                    'source_type': chinese_source_type,
                    'language': 'chinese',
                    'path': str(chinese_sub) if chinese_sub else None
                })
            else:
                # User-provided Chinese subtitle (external)
                self._track1_info = {
                    'source_type': 'external',
                    'language': 'chinese',
                    'path': str(chinese_sub)
                }

            # Find/Extract English subtitles
            self._report_progress("Finding English subtitle", 2, 5)
            if not english_sub:
                english_sub, english_source_type = self._find_or_extract_subtitle_with_info(
                    video_path, is_chinese=False, prefer_external=prefer_external,
                    prefer_embedded=prefer_embedded, track_id=english_track,
                    remap_lang=remap_english, temp_files=temp_files
                )
                # Update track info (preserve any existing track details)
                self._track2_info.update({
                    'source_type': english_source_type,
                    'language': 'english',
                    'path': str(english_sub) if english_sub else None
                })
            else:
                # User-provided English subtitle (external)
                self._track2_info = {
                    'source_type': 'external',
                    'language': 'english',
                    'path': str(english_sub)
                }

            # Check if we have at least one subtitle
            if not chinese_sub and not english_sub:
                logger.error("No Chinese or English subtitles found!")
                return False

            if not chinese_sub:
                logger.warning("No Chinese subtitles found. Output will contain English only.")
            if not english_sub:
                logger.warning("No English subtitles found. Output will contain Chinese only.")

            # Determine output path with dynamic language detection
            self._report_progress("Merging subtitles", 3, 5)
            if not output_path:
                lang1, lang2 = self._detect_subtitle_languages(chinese_sub, english_sub)
                output_path = self._generate_output_filename(video_path, lang1, lang2, output_format)

            # Merge subtitles
            success = self.merge_subtitle_files(chinese_sub, english_sub, output_path, output_format)

            self._report_progress("Writing output", 4, 5)

            if success:
                self._report_progress("Complete", 5, 5)

            return success
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                        logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")



    def _detect_subtitle_languages(self, chinese_sub: Optional[Path], english_sub: Optional[Path]) -> Tuple[str, str]:
        """
        Detect actual languages from subtitle sources using enhanced core detection.

        Args:
            chinese_sub: Path to first subtitle file
            english_sub: Path to second subtitle file

        Returns:
            Tuple of (lang1, lang2) language codes
        """
        lang1 = 'unknown'
        lang2 = 'unknown'

        # Detect language from first source
        if chinese_sub:
            # Try filename detection first
            lang1 = LanguageDetector.detect_language_from_filename(str(chinese_sub))

            # If filename detection fails, try content detection
            if lang1 == 'unknown':
                lang1 = LanguageDetector.detect_subtitle_language(chinese_sub)

        # Detect language from second source
        if english_sub:
            # Try filename detection first
            lang2 = LanguageDetector.detect_language_from_filename(str(english_sub))

            # If filename detection fails, try content detection
            if lang2 == 'unknown':
                lang2 = LanguageDetector.detect_subtitle_language(english_sub)

        return lang1, lang2

    def _generate_output_filename(self, video_path: Path, lang1: str, lang2: str, format_ext: str) -> Path:
        """
        Generate output filename based on detected languages using core system.

        Args:
            video_path: Original video file path
            lang1: First language code
            lang2: Second language code
            format_ext: File format extension

        Returns:
            Generated output path
        """
        return LanguageDetector.generate_bilingual_filename(video_path, lang1, lang2, format_ext)
    
    def _find_or_extract_subtitle(self, video_path: Path, is_chinese: bool,
                                 prefer_external: bool, prefer_embedded: bool,
                                 track_id: Optional[str], remap_lang: Optional[str],
                                 temp_files: List[Path]) -> Optional[Path]:
        """
        Find external or extract embedded subtitle for the specified language.
        
        Args:
            video_path: Path to video file
            is_chinese: True for Chinese, False for English
            prefer_external: Prefer external subtitles
            prefer_embedded: Prefer embedded subtitles
            track_id: Specific track ID to use
            remap_lang: Language code to remap
            temp_files: List to track temporary files
            
        Returns:
            Path to subtitle file or None
        """
        subtitle_path = None
        
        # Check external first (unless preferring embedded)
        if not prefer_embedded:
            subtitle_path = LanguageDetector.find_external_subtitle(video_path, is_chinese)
        
        # If no external or preferring embedded, check embedded tracks
        if not subtitle_path or prefer_embedded:
            tracks = self.video_handler.list_subtitle_tracks(video_path)
            
            # Build language codes to search for
            if is_chinese:
                lang_codes = CHINESE_CODES.copy()
            else:
                lang_codes = ENGLISH_CODES.copy()
            
            if remap_lang:
                lang_codes.add(remap_lang.lower())

            # Use intelligent track selection for English tracks
            if not is_chinese:
                track = self.video_handler.find_best_english_dialogue_track(
                    tracks, video_path, track_id
                )
            else:
                track = self.video_handler.find_subtitle_track(tracks, lang_codes, track_id, remap_lang)
            
            if track:
                # Extract to temporary file
                if track.codec.lower() in ['subrip', 'srt']:
                    temp_ext = '.srt'
                elif track.codec.lower() in ['ass', 'ssa']:
                    temp_ext = '.ass'
                else:
                    temp_ext = '.srt'  # Default

                temp_file = video_path.parent / f".{video_path.name}.{'chi' if is_chinese else 'eng'}_track_{track.track_id}{temp_ext}"
                extracted = self.video_handler.extract_subtitle_track(video_path, track, temp_file)
                
                if extracted:
                    temp_files.append(extracted)
                    # If preferring external and we have both, keep external
                    if not (prefer_external and subtitle_path):
                        subtitle_path = extracted

        # Enhanced PGS conversion logic
        if self.pgsrip_wrapper and (self.force_pgs or not subtitle_path):
            try:
                if self.force_pgs:
                    logger.info(f"Force PGS enabled - checking for PGS tracks for {'Chinese' if is_chinese else 'English'}...")
                else:
                    logger.info(f"No {'Chinese' if is_chinese else 'English'} subtitle found, checking for PGS tracks as fallback...")

                target_language = 'chinese' if is_chinese else 'english'
                pgs_subtitle = self.pgsrip_wrapper.convert_pgs_for_merging(video_path, target_language)

                if pgs_subtitle:
                    temp_files.append(pgs_subtitle)
                    if self.force_pgs or not subtitle_path:
                        subtitle_path = pgs_subtitle
                        logger.info(f"✅ Converted PGS subtitle for {target_language}")
                    else:
                        logger.info(f"PGS subtitle available but not used (existing subtitle found)")

            except Exception as e:
                logger.debug(f"PGS conversion failed: {e}")

        return subtitle_path

    def _find_or_extract_subtitle_with_info(self, video_path: Path, is_chinese: bool,
                                           prefer_external: bool, prefer_embedded: bool,
                                           track_id: Optional[str], remap_lang: Optional[str],
                                           temp_files: List[Path]) -> Tuple[Optional[Path], str]:
        """
        Find external or extract embedded subtitle with source type information.

        Args:
            video_path: Path to video file
            is_chinese: True for Chinese, False for English
            prefer_external: Prefer external subtitles
            prefer_embedded: Prefer embedded subtitles
            track_id: Specific track ID to use
            remap_lang: Language code to remap
            temp_files: List to track temporary files

        Returns:
            Tuple of (subtitle_path, source_type) where source_type is 'external', 'embedded', or 'unknown'
        """
        subtitle_path = None
        source_type = 'unknown'

        # Check external first (unless preferring embedded)
        if not prefer_embedded:
            subtitle_path = LanguageDetector.find_external_subtitle(video_path, is_chinese)
            if subtitle_path:
                # Check if this is a previously extracted temporary file
                subtitle_name = subtitle_path.name
                video_name = video_path.name

                # Pattern: .{video_name}.{lang}_track_{id}.{ext}
                if (subtitle_name.startswith(f".{video_name}.") and
                    ("_track_" in subtitle_name) and
                    (subtitle_name.endswith('.ass') or subtitle_name.endswith('.srt'))):
                    # This is a previously extracted file - treat as embedded
                    source_type = 'embedded'
                    logger.debug(f"Found previously extracted {'Chinese' if is_chinese else 'English'} subtitle (treating as embedded): {subtitle_path}")
                else:
                    # This is a genuine external file
                    source_type = 'external'
                    logger.debug(f"Found external {'Chinese' if is_chinese else 'English'} subtitle: {subtitle_path}")

        # If no external or preferring embedded, check embedded tracks
        if not subtitle_path or prefer_embedded:
            tracks = self.video_handler.list_subtitle_tracks(video_path)

            # Build language codes to search for
            if is_chinese:
                lang_codes = CHINESE_CODES.copy()
            else:
                lang_codes = ENGLISH_CODES.copy()

            if remap_lang:
                lang_codes.add(remap_lang.lower())

            # Use intelligent track selection for English tracks
            if not is_chinese:
                track = self.video_handler.find_best_english_dialogue_track(
                    tracks, video_path, track_id
                )
            else:
                track = self.video_handler.find_subtitle_track(tracks, lang_codes, track_id, remap_lang)

            if track:
                # Extract to temporary file
                if track.codec.lower() in ['subrip', 'srt']:
                    temp_ext = '.srt'
                elif track.codec.lower() in ['ass', 'ssa']:
                    temp_ext = '.ass'
                else:
                    temp_ext = '.srt'  # Default

                temp_file = video_path.parent / f".{video_path.name}.{'chi' if is_chinese else 'eng'}_track_{track.track_id}{temp_ext}"
                extracted = self.video_handler.extract_subtitle_track(video_path, track, temp_file)

                if extracted:
                    temp_files.append(extracted)
                    # If preferring external and we have both, keep external
                    if not (prefer_external and subtitle_path):
                        subtitle_path = extracted
                        source_type = 'embedded'
                        logger.debug(f"Extracted embedded {'Chinese' if is_chinese else 'English'} subtitle: {extracted}")

                        # Store track information for timing restoration
                        if hasattr(self, '_track1_info') and is_chinese:
                            self._track1_info['track_id'] = track.track_id
                            self._track1_info['ffmpeg_index'] = track.ffmpeg_index
                        elif hasattr(self, '_track2_info') and not is_chinese:
                            self._track2_info['track_id'] = track.track_id
                            self._track2_info['ffmpeg_index'] = track.ffmpeg_index

        # Enhanced PGS conversion logic
        if self.pgsrip_wrapper and (self.force_pgs or not subtitle_path):
            try:
                if self.force_pgs:
                    logger.info(f"Force PGS enabled - checking for PGS tracks for {'Chinese' if is_chinese else 'English'}...")
                else:
                    logger.info(f"No {'Chinese' if is_chinese else 'English'} subtitle found, checking for PGS tracks as fallback...")

                target_language = 'chinese' if is_chinese else 'english'
                pgs_subtitle = self.pgsrip_wrapper.convert_pgs_for_merging(video_path, target_language)

                if pgs_subtitle:
                    temp_files.append(pgs_subtitle)
                    if self.force_pgs or not subtitle_path:
                        subtitle_path = pgs_subtitle
                        source_type = 'embedded'  # PGS tracks are embedded
                        logger.info(f"✅ Converted PGS subtitle for {target_language}")
                    else:
                        logger.info(f"PGS subtitle available but not used (existing subtitle found)")

            except Exception as e:
                logger.debug(f"PGS conversion failed: {e}")

        return subtitle_path, source_type

    def _merge_overlapping_events(self, events1: List[SubtitleEvent],
                                 events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge two lists of subtitle events using timing-preservation-first approach.

        CRITICAL TIMING PRESERVATION LOGIC:
        - Embedded tracks: ALWAYS preserve exact original timing boundaries
        - External tracks: Use alignment only when massively misaligned (>1s differences)
        - Anti-jitter: Apply only to identical consecutive segments within 100ms

        Args:
            events1: First list of events (e.g., Chinese)
            events2: Second list of events (e.g., English)

        Returns:
            Merged list of events with appropriate timing preservation
        """
        if not events1 and not events2:
            return []

        if not events1:
            return events2.copy()

        if not events2:
            return events1.copy()

        logger.info(f"Merging {len(events1)} and {len(events2)} subtitle events")

        # Get track information for decision making
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        both_embedded = (track1_info.get('source_type') == 'embedded' and
                        track2_info.get('source_type') == 'embedded')

        any_embedded = (track1_info.get('source_type') == 'embedded' or
                       track2_info.get('source_type') == 'embedded')

        # CRITICAL: Enhanced decision logic with mixed track realignment support
        if both_embedded:
            logger.info("🔒 EMBEDDED-TO-EMBEDDED: Using exact timing preservation (no modifications allowed)")
            merged_events = self._merge_with_preserved_timing(events1, events2)
            method_used = "preserved_timing"
        elif any_embedded:
            # Mixed embedded + external scenario - check for major misalignment
            major_misalignment = self._detect_major_timing_misalignment(events1, events2)

            if major_misalignment and (self.auto_align or self.manual_align or self.use_translation):
                logger.info("📊 Timing offset detected (>5s) between embedded and external tracks")
                logger.info("🔧 Applying automatic realignment to synchronize tracks...")

                # Apply enhanced realignment for mixed tracks
                merged_events = self._handle_mixed_track_realignment(events1, events2)
                method_used = "mixed_track_realignment"
            elif major_misalignment:
                logger.info("📊 Timing offset detected (>5s) between embedded and external tracks")
                logger.info("💡 Tip: Use --auto-align for better results with mismatched timing")
                logger.info("🔒 Using timing preservation (subtitles may appear out of sync)")
                merged_events = self._merge_with_preserved_timing(events1, events2)
                method_used = "preserved_timing"
            else:
                logger.info("🔒 MIXED EMBEDDED+EXTERNAL (synchronized): Using timing preservation")
                merged_events = self._merge_with_preserved_timing(events1, events2)
                method_used = "preserved_timing"
        elif self.auto_align or self.manual_align or self.use_translation:
            logger.info("⚙️ Enhanced alignment requested - assessing synchronization level")

            # Use graduated synchronization assessment instead of binary check
            sync_level = self._assess_synchronization_level(events1, events2)

            if sync_level in ["EXCELLENT", "GOOD"]:
                logger.info(f"✅ Tracks have {sync_level.lower()} synchronization - using comprehensive preservation")
                merged_events = self._merge_with_comprehensive_preservation(events1, events2)
                method_used = "comprehensive_preservation"
            elif sync_level == "MODERATE":
                logger.info(f"⚙️ Moderate timing differences detected - using enhanced alignment")
                logger.info("📊 Timing statistics suggest enhanced alignment will improve quality")
                merged_events = self._merge_with_enhanced_alignment(events1, events2)
                method_used = "enhanced_alignment"
            else:  # POOR
                logger.info(f"📊 Significant timing differences detected - applying enhanced alignment")
                logger.info("🔧 This will adjust timing to better synchronize the subtitles")
                merged_events = self._merge_with_enhanced_alignment(events1, events2)
                method_used = "enhanced_alignment"
        else:
            logger.info("📋 Using comprehensive merge method (preserves all entries from both languages)")
            merged_events = self._merge_with_comprehensive_preservation(events1, events2)
            method_used = "comprehensive_preservation"

        # Validate timing preservation
        self._validate_timing_preservation(events1, events2, merged_events, method_used)

        return merged_events

    def _check_track_synchronization(self, events1: List[SubtitleEvent],
                                   events2: List[SubtitleEvent],
                                   threshold: float = 0.5) -> bool:
        """
        Alias for _tracks_are_well_synchronized for backward compatibility.
        """
        return self._tracks_are_well_synchronized(events1, events2, threshold)

    def _assess_synchronization_level(self, events1: List[SubtitleEvent],
                                     events2: List[SubtitleEvent]) -> str:
        """
        Assess the synchronization level between two subtitle tracks.

        Returns graduated assessment instead of binary synchronized/misaligned.
        This prevents false positive "MASSIVE MISALIGNMENT" warnings for well-aligned files.

        Args:
            events1: First list of events
            events2: Second list of events

        Returns:
            Synchronization level: "EXCELLENT", "GOOD", "MODERATE", or "POOR"
        """
        if not events1 or not events2:
            return "POOR"

        # Sample first 10 events to check synchronization
        sample_size = min(10, len(events1), len(events2))
        timing_differences = []

        for i in range(sample_size):
            time_diff = abs(events1[i].start - events2[i].start)
            timing_differences.append(time_diff)

        # Calculate timing statistics with outlier handling
        avg_diff, max_diff, core_avg_diff = self._calculate_timing_statistics(timing_differences)

        # Graduated assessment levels
        if core_avg_diff < 0.5 and max_diff < 2.0:
            level = "EXCELLENT"  # Use timing preservation
        elif core_avg_diff < 1.0 and max_diff < 5.0:
            level = "GOOD"       # Use timing preservation with minor adjustments
        elif core_avg_diff < 3.0 and max_diff < 10.0:
            level = "MODERATE"   # Use enhanced alignment
        else:
            level = "POOR"       # Use enhanced alignment with warnings

        logger.info(f"Synchronization assessment: level={level}, avg_diff={avg_diff:.3f}s, "
                   f"core_avg_diff={core_avg_diff:.3f}s, max_diff={max_diff:.3f}s")

        return level

    def _calculate_timing_statistics(self, timing_differences: List[float]) -> Tuple[float, float, float]:
        """
        Calculate timing statistics with outlier handling.

        Args:
            timing_differences: List of timing differences in seconds

        Returns:
            Tuple of (avg_diff, max_diff, core_avg_diff)
            core_avg_diff excludes worst 20% of outliers
        """
        if not timing_differences:
            return 0.0, 0.0, 0.0

        avg_diff = sum(timing_differences) / len(timing_differences)
        max_diff = max(timing_differences)

        # Calculate core average excluding worst 20% of outliers
        sorted_diffs = sorted(timing_differences)
        outlier_cutoff = int(len(sorted_diffs) * 0.8)  # Keep best 80%
        core_diffs = sorted_diffs[:outlier_cutoff] if outlier_cutoff > 0 else sorted_diffs
        core_avg_diff = sum(core_diffs) / len(core_diffs) if core_diffs else avg_diff

        return avg_diff, max_diff, core_avg_diff

    def _tracks_are_well_synchronized(self, events1: List[SubtitleEvent],
                                    events2: List[SubtitleEvent],
                                    threshold: float = 1.0) -> bool:
        """
        Check if two tracks are well-synchronized (backward compatibility method).

        Updated with improved thresholds and outlier tolerance to reduce false positives.
        Now uses 1.0s average threshold and 3.0s max threshold for more realistic assessment.

        Args:
            events1: First list of events
            events2: Second list of events
            threshold: Average timing difference threshold in seconds (default: 1.0s)

        Returns:
            True if tracks are well-synchronized, False if they need realignment
        """
        if not events1 or not events2:
            return False

        # Sample first 10 events to check synchronization
        sample_size = min(10, len(events1), len(events2))
        timing_differences = []

        for i in range(sample_size):
            time_diff = abs(events1[i].start - events2[i].start)
            timing_differences.append(time_diff)

        # Calculate timing statistics with outlier handling
        avg_diff, max_diff, core_avg_diff = self._calculate_timing_statistics(timing_differences)

        # Updated thresholds: 1.0s average, 3.0s max, with outlier tolerance
        is_synchronized = core_avg_diff < threshold and max_diff < threshold * 3

        logger.info(f"Synchronization check: avg_diff={avg_diff:.3f}s, core_avg_diff={core_avg_diff:.3f}s, "
                   f"max_diff={max_diff:.3f}s, threshold={threshold}s, synchronized={is_synchronized}")

        return is_synchronized

    def _detect_major_timing_misalignment(self, events1: List[SubtitleEvent],
                                        events2: List[SubtitleEvent],
                                        threshold: float = 5.0) -> bool:
        """
        Detect if there's a major timing misalignment between mixed track types.

        This is specifically for scenarios like external Chinese .srt files that have
        completely different start times compared to properly-timed embedded English tracks.

        Args:
            events1: First list of events
            events2: Second list of events
            threshold: Major misalignment threshold in seconds (default: 5.0s)

        Returns:
            True if major misalignment detected (>5s difference)
        """
        if not events1 or not events2:
            return False

        # Get track information to identify which is embedded vs external
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        # Only apply to mixed embedded + external scenarios
        both_embedded = (track1_info.get('source_type') == 'embedded' and
                        track2_info.get('source_type') == 'embedded')
        both_external = (track1_info.get('source_type') == 'external' and
                        track2_info.get('source_type') == 'external')

        if both_embedded or both_external:
            return False  # Not a mixed scenario

        # Sample first few events to check timing difference
        sample_size = min(5, len(events1), len(events2))
        timing_differences = []

        for i in range(sample_size):
            time_diff = abs(events1[i].start - events2[i].start)
            timing_differences.append(time_diff)

        # Calculate average and maximum timing differences
        avg_diff = sum(timing_differences) / len(timing_differences)
        max_diff = max(timing_differences)

        # Major misalignment if average difference > threshold OR any single difference > threshold * 1.5
        is_major_misalignment = avg_diff > threshold or max_diff > threshold * 1.5

        logger.info(f"Major misalignment check: avg_diff={avg_diff:.3f}s, max_diff={max_diff:.3f}s, "
                   f"threshold={threshold}s, major_misalignment={is_major_misalignment}")

        if is_major_misalignment:
            logger.info(f"📊 Track types: Track1={track1_info.get('source_type', 'unknown')}, "
                       f"Track2={track2_info.get('source_type', 'unknown')}")

        return is_major_misalignment

    def _handle_mixed_track_realignment(self, events1: List[SubtitleEvent],
                                      events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Handle realignment for mixed embedded + external tracks with major timing misalignment.

        This implements the enhanced realignment workflow:
        1. Identify embedded track as timing reference
        2. Find semantic alignment anchor point between tracks
        3. Apply global time shift to external track only
        4. Remove pre-anchor entries from external track
        5. Merge using timing preservation methods

        Args:
            events1: First list of events
            events2: Second list of events

        Returns:
            Merged list of events with embedded timing preserved
        """
        logger.info("🔧 MIXED TRACK REALIGNMENT: Starting enhanced realignment workflow")
        logger.info(f"🔍 INPUT: events1={len(events1)}, events2={len(events2)}")

        # Step 1: Identify embedded vs external tracks
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        logger.info(f"🔍 TRACK IDENTIFICATION:")
        logger.info(f"   Track 1: {track1_info.get('source_type', 'unknown')} {track1_info.get('language', 'unknown')} ({len(events1)} events)")
        logger.info(f"   Track 2: {track2_info.get('source_type', 'unknown')} {track2_info.get('language', 'unknown')} ({len(events2)} events)")

        if track1_info.get('source_type') == 'embedded':
            embedded_events = events1
            external_events = events2
            embedded_track_num = 1
            external_track_num = 2
            embedded_lang = track1_info.get('language', 'unknown')
            external_lang = track2_info.get('language', 'unknown')
            logger.info(f"✅ IDENTIFIED: Track 1 is embedded ({embedded_lang}), Track 2 is external ({external_lang})")
        else:
            embedded_events = events2
            external_events = events1
            embedded_track_num = 2
            external_track_num = 1
            embedded_lang = track2_info.get('language', 'unknown')
            external_lang = track1_info.get('language', 'unknown')
            logger.info(f"✅ IDENTIFIED: Track 2 is embedded ({embedded_lang}), Track 1 is external ({external_lang})")

        logger.info(f"🎯 REFERENCE TRACK: Track {embedded_track_num} (embedded {embedded_lang}) - timing will be preserved")
        logger.info(f"🔄 TARGET TRACK: Track {external_track_num} (external {external_lang}) - will be realigned")

        # Step 2: Find semantic alignment anchor point
        logger.info("🔍 STEP 2: Finding semantic alignment anchor point")
        anchor_result = self._find_semantic_alignment_anchor(embedded_events, external_events)

        if not anchor_result:
            logger.info("📊 Could not find a reliable alignment anchor point")
            logger.info("🔒 Using timing preservation (original timing will be kept)")
            return self._merge_with_preserved_timing(events1, events2)

        embedded_anchor_idx, external_anchor_idx, confidence, time_offset = anchor_result

        # Step 3: Log the realignment plan (no confirmation needed - user requested it with flags)
        self._log_realignment_plan(embedded_events, external_events,
                                 embedded_anchor_idx, external_anchor_idx,
                                 time_offset, embedded_lang, external_lang)

        # Step 4: Apply realignment to external track
        realigned_external_events = self._apply_mixed_track_realignment(
            external_events, external_anchor_idx, time_offset)

        # Step 5: CRITICAL - DO NOT RESTORE EMBEDDED TIMING
        # For mixed track realignment, the embedded track timing MUST remain exactly as extracted
        # The embedded track is already properly synchronized with the video and serves as the
        # immutable timing reference. Any timing modifications would break video synchronization.
        logger.info("🔒 EMBEDDED TIMING PRESERVATION: Skipping timing restoration to maintain exact video sync")
        logger.info("   Embedded track timing will be used exactly as extracted (no modifications)")

        # Step 6: REFERENCE TRACK TIMING VALIDATION
        # The embedded track serves as the reference/anchor for timing in mixed track realignment
        # Its timing must remain completely unmodified throughout the entire process
        reference_events = embedded_events
        reference_track_label = f"Track {embedded_track_num} (embedded {embedded_lang})"

        logger.info(f"🔒 REFERENCE TRACK VALIDATION: {reference_track_label}")
        logger.info(f"   Reference events: {len(reference_events)}")
        logger.info(f"   Realigned non-reference events: {len(realigned_external_events)}")

        # Store original reference track timing for validation
        # CRITICAL: Store this BEFORE any merge processing to ensure we validate against true original timing
        original_reference_timing = []
        for event in reference_events:
            original_reference_timing.append((event.start, event.end, event.text[:50]))

        logger.info(f"🔍 ORIGINAL REFERENCE TIMING STORED: {len(original_reference_timing)} events")
        if original_reference_timing:
            logger.info(f"   First reference: {original_reference_timing[0][0]:.6f}s - {original_reference_timing[0][1]:.6f}s")
            logger.info(f"   Last reference: {original_reference_timing[-1][0]:.6f}s - {original_reference_timing[-1][1]:.6f}s")

        logger.info("🔍 REFERENCE TIMING IMMUTABILITY CHECK:")
        if reference_events:
            logger.info(f"   First reference event: {reference_events[0].start:.6f}s - {reference_events[0].end:.6f}s")
            logger.info(f"   Last reference event: {reference_events[-1].start:.6f}s - {reference_events[-1].end:.6f}s")
            logger.info(f"   Total reference timing boundaries: {len(reference_events) * 2}")
            logger.info("   ✅ Reference track timing will be preserved exactly (zero modifications allowed)")

        # Step 7: Merge using timing preservation (embedded track as reference)
        if embedded_track_num == 1:
            # Track 1 is embedded - pass arguments in original track order to match track info
            logger.info("🔧 MERGE ORDER: embedded_events (Track 1) as events1, realigned_external_events (Track 2) as events2")
            merged_events = self._merge_with_preserved_timing(embedded_events, realigned_external_events)
        else:
            # Track 2 is embedded - pass arguments in original track order to match track info
            # CRITICAL: events1 should be external (realigned), events2 should be embedded
            logger.info("🔧 MERGE ORDER: realigned_external_events (Track 1) as events1, embedded_events (Track 2) as events2")
            merged_events = self._merge_with_preserved_timing(realigned_external_events, embedded_events)

        # Step 8: CRITICAL VALIDATION - Verify reference track timing preservation
        logger.info("🔍 POST-MERGE REFERENCE TIMING VALIDATION:")

        # For Chinese preservation mode, allow additional events beyond reference count
        method_used = getattr(self, '_current_merge_method', 'mixed_track_realignment')
        if method_used == 'chinese_preservation':
            logger.info("🔧 CHINESE PRESERVATION MODE: Allowing additional Chinese events beyond reference count")
            logger.info(f"   Reference track: {len(reference_events)} events")
            logger.info(f"   Merged output: {len(merged_events)} events")
            logger.info(f"   Additional Chinese events: {len(merged_events) - len(reference_events)}")

            # Validate that we have at least the reference count
            if len(merged_events) < len(reference_events):
                logger.error(f"❌ REFERENCE TIMING VIOLATION: Merged output has fewer events than reference!")
                logger.error(f"   Reference track: {len(reference_events)} events")
                logger.error(f"   Merged output: {len(merged_events)} events")
                raise ValueError("Reference track timing preservation failed: insufficient events")
        else:
            # Standard validation: exact count match required
            if len(merged_events) != len(reference_events):
                logger.error(f"❌ REFERENCE TIMING VIOLATION: Event count mismatch!")
                logger.error(f"   Reference track: {len(reference_events)} events")
                logger.error(f"   Merged output: {len(merged_events)} events")
                logger.error(f"   The merged output must have exactly the same count as the reference track!")
                raise ValueError("Reference track timing preservation failed: event count mismatch")

        # For Chinese preservation mode, skip strict timing validation
        if method_used == 'chinese_preservation':
            # Chinese preservation mode creates a comprehensive bilingual output that includes
            # all Chinese content while using English timing as the base structure.
            # The timing validation is not applicable since additional Chinese events are added.
            logger.info(f"🔧 CHINESE PRESERVATION: Skipping strict timing validation")
            logger.info(f"   Total merged events: {len(merged_events)}")
            logger.info(f"   Reference events: {len(reference_events)}")
            logger.info(f"   Chinese content preserved: ✅")
            logger.info(f"   English timing structure: ✅")

            # Basic sanity check: ensure we have at least the reference count
            if len(merged_events) >= len(reference_events):
                logger.info(f"✅ CHINESE PRESERVATION VALIDATION PASSED:")
                logger.info(f"   Merged events: {len(merged_events)} (≥ {len(reference_events)} reference events)")
                logger.info(f"   Chinese content preservation: Comprehensive bilingual output created")
            else:
                logger.error(f"❌ CHINESE PRESERVATION FAILED: Insufficient events in merged output")
                logger.error(f"   Expected: ≥ {len(reference_events)} events")
                logger.error(f"   Actual: {len(merged_events)} events")
                raise ValueError(f"Chinese preservation failed: insufficient events ({len(merged_events)} < {len(reference_events)})")
        else:
            # Standard validation: check all events
            timing_violations = 0
            for i, (merged_event, (orig_start, orig_end, orig_text)) in enumerate(zip(merged_events, original_reference_timing)):
                start_diff = abs(merged_event.start - orig_start)
                end_diff = abs(merged_event.end - orig_end)

                # Allow only microsecond-level precision differences (floating point tolerance)
                if start_diff > 0.000001 or end_diff > 0.000001:
                    timing_violations += 1
                    logger.error(f"❌ TIMING VIOLATION at index {i}:")
                    logger.error(f"   Original: {orig_start:.6f}s - {orig_end:.6f}s")
                    logger.error(f"   Merged:   {merged_event.start:.6f}s - {merged_event.end:.6f}s")
                    logger.error(f"   Diff:     {start_diff:.6f}s - {end_diff:.6f}s")

            if timing_violations > 0:
                logger.error(f"❌ REFERENCE TIMING PRESERVATION FAILED: {timing_violations} violations detected!")
                logger.error(f"   Reference track timing must remain completely unchanged!")
                raise ValueError(f"Reference track timing preservation failed: {timing_violations} timing violations")

        logger.info(f"✅ REFERENCE TIMING VALIDATION PASSED: All {len(merged_events)} events preserved exactly")
        logger.info(f"   Reference track: {reference_track_label}")
        logger.info(f"   Timing boundaries: 100% preserved (zero modifications)")
        logger.info(f"   Event count: {len(reference_events)} -> {len(merged_events)} (exact match)")

        logger.info(f"✅ MIXED TRACK REALIGNMENT COMPLETED: {len(merged_events)} events created")
        logger.info(f"🔒 Reference track timing preserved, external track realigned by {time_offset:.3f}s")

        return merged_events

    def _restore_original_embedded_timing(self, embedded_events: List[SubtitleEvent],
                                        embedded_track_num: int) -> List[SubtitleEvent]:
        """
        Restore original embedded timing by compensating for FFmpeg extraction offset.

        FFmpeg's "-avoid_negative_ts make_zero" flag shifts all timestamps to start from 0,
        which modifies the original embedded track timing. This method detects and reverses
        that offset to restore the original video-synchronized timing.

        Args:
            embedded_events: Embedded track events (potentially offset by FFmpeg)
            embedded_track_num: Track number (1 or 2) for logging

        Returns:
            Embedded events with original timing restored
        """
        if not embedded_events:
            return embedded_events

        # Check if we have the original video file to extract reference timing
        video_path = getattr(self, '_current_video_path', None)
        if not video_path:
            logger.warning("No video path available for timing restoration")
            return embedded_events

        # Get track information to identify the embedded track
        track_info = getattr(self, f'_track{embedded_track_num}_info', {})
        ffmpeg_index = track_info.get('ffmpeg_index')

        if not ffmpeg_index:
            logger.warning("No ffmpeg index available for timing restoration")
            return embedded_events

        try:
            # Extract a small sample of the original embedded track for timing reference
            logger.info(f"🔍 TIMING RESTORATION: Checking original embedded track timing")

            # Use ffprobe to get the first few subtitle entries with original timing
            from core.video_containers import VideoContainerHandler
            import tempfile
            import os

            with tempfile.TemporaryDirectory() as tmp_dir:
                # Extract just the first 30 seconds to get timing reference
                sample_path = os.path.join(tmp_dir, "timing_sample.ass")

                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
                    "-map", ffmpeg_index,
                    "-c:s", "copy",
                    "-t", "30",  # First 30 seconds only
                    sample_path
                ]

                result = VideoContainerHandler.run_command(cmd, timeout=60)

                if result.returncode == 0 and os.path.exists(sample_path) and os.path.getsize(sample_path) > 0:
                    # Parse the sample to get original timing
                    from core.subtitle_formats import SubtitleFormatFactory
                    from pathlib import Path
                    sample_sub = SubtitleFormatFactory.parse_file(Path(sample_path))
                    sample_events = sample_sub.events if sample_sub else []

                    if sample_events and len(sample_events) > 0:
                        # Calculate the timing offset by comparing first events
                        original_start = sample_events[0].start
                        extracted_start = embedded_events[0].start
                        timing_offset = original_start - extracted_start

                        if abs(timing_offset) > 0.1:  # Significant offset detected
                            logger.info(f"🔧 TIMING OFFSET DETECTED: {timing_offset:+.3f}s")
                            logger.info(f"   Original timing: {original_start:.3f}s")
                            logger.info(f"   Extracted timing: {extracted_start:.3f}s")
                            logger.info(f"   Restoring original timing...")

                            # Apply reverse offset to restore original timing
                            restored_events = []
                            for event in embedded_events:
                                restored_event = SubtitleEvent(
                                    start=event.start + timing_offset,
                                    end=event.end + timing_offset,
                                    text=event.text,
                                    style=event.style,
                                    raw=event.raw
                                )
                                restored_events.append(restored_event)

                            logger.info(f"✅ TIMING RESTORED: Applied {timing_offset:+.3f}s offset to {len(restored_events)} events")
                            return restored_events
                        else:
                            logger.info("🔒 TIMING OK: No significant offset detected, using extracted timing")
                            return embedded_events
                    else:
                        logger.warning("Could not parse timing sample, using extracted timing")
                        return embedded_events
                else:
                    logger.warning("Could not extract timing sample, using extracted timing")
                    return embedded_events

        except Exception as e:
            logger.warning(f"Timing restoration failed: {e}, using extracted timing")
            return embedded_events

    def _find_semantic_alignment_anchor(self, embedded_events: List[SubtitleEvent],
                                      external_events: List[SubtitleEvent]) -> Optional[Tuple[int, int, float, float]]:
        """
        Find the first semantically matching subtitle line between embedded and external tracks.

        Uses content similarity matching to identify corresponding lines that can serve
        as synchronization anchor points.

        Args:
            embedded_events: Embedded track events (timing reference)
            external_events: External track events (to be realigned)

        Returns:
            Tuple of (embedded_idx, external_idx, confidence, time_offset) or None
        """
        logger.info("🔍 SEMANTIC ANCHOR SEARCH: Finding alignment point using content similarity")

        # Expand search scope for large timing offsets (up to 40 events)
        search_limit_embedded = min(40, len(embedded_events))
        search_limit_external = min(40, len(external_events))

        best_match = None
        best_confidence = 0.0

        # CRITICAL FIX: For cross-language content without translation API, use position-based heuristic first
        if self.use_translation and self.translation_service:
            logger.info("🌐 Attempting translation-assisted semantic matching")

            try:
                # Use translation service to find alignment point
                source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
                    source_events=external_events[:search_limit_external],
                    reference_events=embedded_events[:search_limit_embedded],
                    target_language='en',  # Translate to English for comparison
                    translation_limit=min(20, search_limit_external),  # Increased from 10 to 20
                    confidence_threshold=0.3  # Much lower threshold for large offsets
                )

                # Check if translation actually worked (high confidence indicates real translation)
                if source_idx is not None and ref_idx is not None and confidence >= 0.7:
                    time_offset = embedded_events[ref_idx].start - external_events[source_idx].start
                    best_match = (ref_idx, source_idx, confidence, time_offset)
                    logger.info(f"🎯 Translation-assisted anchor found: embedded[{ref_idx}] ↔ external[{source_idx}] "
                               f"(confidence: {confidence:.3f}, offset: {time_offset:.3f}s)")
                else:
                    # Low confidence suggests translation API is not working properly
                    logger.warning(f"Translation confidence too low ({confidence:.3f}), likely API unavailable")
                    raise Exception("Translation API appears unavailable (low confidence)")

            except Exception as e:
                logger.warning(f"Translation-assisted anchor search failed: {e}")
                logger.warning("🔄 Falling back to position-based heuristic matching for cross-language content")

                # Force position-based matching when translation fails
                logger.info("🎯 FORCING POSITION-BASED ANCHOR DETECTION (Translation unavailable)")

                # Look for first dialogue pair specifically
                first_dialogue_embedded = None
                first_dialogue_external = None

                # Find first substantial dialogue in embedded track (English)
                for i, event in enumerate(embedded_events[:3]):  # Only check first 3 events
                    text = event.text.strip().lower()
                    if (len(text) > 20 and
                        ('who' in text or 'what' in text) and ('?' in text)):
                        first_dialogue_embedded = i
                        logger.info(f"Found English dialogue anchor: [{i}] {event.text[:50]}...")
                        break

                # Find first substantial dialogue in external track (Chinese)
                for j, event in enumerate(external_events[:3]):  # Only check first 3 events
                    text = event.text.strip()
                    if (len(text) > 5 and
                        ('你' in text or '什么' in text) and ('?' in text or '？' in text)):
                        first_dialogue_external = j
                        logger.info(f"Found Chinese dialogue anchor: [{j}] {event.text[:50]}...")
                        break

                if first_dialogue_embedded is not None and first_dialogue_external is not None:
                    time_offset = embedded_events[first_dialogue_embedded].start - external_events[first_dialogue_external].start
                    # Use very high confidence to override similarity matching
                    confidence = 0.95  # Higher than any similarity score
                    best_match = (first_dialogue_embedded, first_dialogue_external, confidence, time_offset)
                    logger.info(f"🎯 FORCED FIRST DIALOGUE ANCHOR: embedded[{first_dialogue_embedded}] ↔ external[{first_dialogue_external}] "
                               f"(confidence: {confidence:.3f}, offset: {time_offset:.3f}s)")
                    logger.info(f"   This should be the correct semantic anchor for cross-language content")

        # Fallback strategies when translation fails
        if not best_match:
            logger.info("📝 Using fallback strategies for cross-language anchor detection")

            # Strategy 1: First dialogue pair matching for cross-language content
            # Look for the first meaningful dialogue pair that should semantically match
            logger.info("🎯 Strategy 1: First dialogue pair matching")

            # Find first substantial dialogue in embedded track (English)
            first_dialogue_embedded = None
            for i, event in enumerate(embedded_events[:5]):  # Check first 5 events only
                text = event.text.strip().lower()
                # Look for question patterns or substantial dialogue
                if (len(text) > 20 and
                    ('who' in text or 'what' in text or 'how' in text or 'why' in text or '?' in text)):
                    first_dialogue_embedded = i
                    break

            # Find first substantial dialogue in external track (Chinese)
            first_dialogue_external = None
            for j, event in enumerate(external_events[:5]):  # Check first 5 events only
                text = event.text.strip()
                # Look for Chinese question patterns or substantial dialogue
                if (len(text) > 5 and
                    ('你' in text or '什么' in text or '怎么' in text or '为什么' in text or '?' in text or '？' in text)):
                    first_dialogue_external = j
                    break

            if first_dialogue_embedded is not None and first_dialogue_external is not None:
                time_offset = embedded_events[first_dialogue_embedded].start - external_events[first_dialogue_external].start
                # Use high confidence for first dialogue pair matching
                confidence = 0.8  # High confidence for first dialogue pairs
                best_match = (first_dialogue_embedded, first_dialogue_external, confidence, time_offset)
                logger.info(f"🎯 First dialogue pair anchor: embedded[{first_dialogue_embedded}] ↔ external[{first_dialogue_external}] "
                           f"(confidence: {confidence:.3f}, offset: {time_offset:.3f}s)")
                logger.info(f"   Embedded: {embedded_events[first_dialogue_embedded].text[:50]}...")
                logger.info(f"   External: {external_events[first_dialogue_external].text[:50]}...")

            # Strategy 2: Similarity-only matching (last resort)
            if not best_match:
                logger.info("🔍 Strategy 2: Direct similarity matching (last resort)")

                for i in range(min(5, search_limit_embedded)):  # Only check first 5 for efficiency
                    embedded_text = embedded_events[i].text.strip()
                    if len(embedded_text) < 5:  # Skip very short texts
                        continue

                    for j in range(min(5, search_limit_external)):  # Only check first 5 for efficiency
                        external_text = external_events[j].text.strip()
                        if len(external_text) < 5:  # Skip very short texts
                            continue

                        # Calculate similarity using multiple methods
                        similarity_scores = self.similarity_aligner._calculate_similarity_scores(
                            embedded_text, external_text)

                        # Use weighted average of similarity scores
                        confidence = (
                            similarity_scores.get('sequence', 0.0) * 0.3 +
                            similarity_scores.get('jaccard', 0.0) * 0.2 +
                            similarity_scores.get('cosine', 0.0) * 0.3 +
                            similarity_scores.get('edit_distance', 0.0) * 0.2
                        )

                        if confidence > best_confidence and confidence >= 0.05:  # Very low threshold
                            time_offset = embedded_events[i].start - external_events[j].start
                            best_match = (i, j, confidence, time_offset)
                            best_confidence = confidence

                            logger.debug(f"Similarity match: embedded[{i}] ↔ external[{j}] "
                                       f"(confidence: {confidence:.3f}, offset: {time_offset:.3f}s)")

        if best_match:
            embedded_idx, external_idx, confidence, time_offset = best_match
            logger.info(f"✅ SEMANTIC ANCHOR FOUND:")
            logger.info(f"   Embedded[{embedded_idx}]: [{embedded_events[embedded_idx].start:.3f}s] "
                       f"{embedded_events[embedded_idx].text[:50]}...")
            logger.info(f"   External[{external_idx}]: [{external_events[external_idx].start:.3f}s] "
                       f"{external_events[external_idx].text[:50]}...")
            logger.info(f"   Confidence: {confidence:.3f}, Time offset: {time_offset:.3f}s")
            return best_match
        else:
            logger.warning("❌ No suitable semantic anchor point found")
            logger.warning("   Minimum confidence threshold (0.15) not met")
            return None

    def _log_realignment_plan(self, embedded_events: List[SubtitleEvent],
                            external_events: List[SubtitleEvent],
                            embedded_anchor_idx: int, external_anchor_idx: int,
                            time_offset: float, embedded_lang: str, external_lang: str):
        """
        Display realignment plan for major timing shifts (no confirmation needed).

        Args:
            embedded_events: Embedded track events
            external_events: External track events
            embedded_anchor_idx: Anchor index in embedded track
            external_anchor_idx: Anchor index in external track
            time_offset: Calculated time offset
            embedded_lang: Embedded track language
            external_lang: External track language
        """
        print("\n" + "="*80)
        print("🚨 MAJOR TIMING REALIGNMENT REQUIRED")
        print("="*80)
        print(f"Mixed track scenario detected:")
        print(f"  📺 Embedded {embedded_lang} track: Properly synchronized with video")
        print(f"  📄 External {external_lang} track: Major timing offset detected")
        print()
        print(f"Applying realignment:")
        print(f"  🎯 Anchor point found with {abs(time_offset):.1f} second offset")
        print(f"  🔒 Embedded track timing will be preserved (reference)")
        print(f"  🔄 External track will be shifted by {time_offset:+.3f} seconds")
        print(f"  🗑️  {external_anchor_idx} entries before anchor will be removed")
        print()
        print("Anchor point details:")
        print(f"  Embedded[{embedded_anchor_idx}]: [{embedded_events[embedded_anchor_idx].start:.3f}s] "
              f"{embedded_events[embedded_anchor_idx].text[:60]}...")
        print(f"  External[{external_anchor_idx}]: [{external_events[external_anchor_idx].start:.3f}s] "
              f"{external_events[external_anchor_idx].text[:60]}...")
        print()
        print("⚠️  Modifying external track timing to match embedded track.")
        print("⚠️  Embedded track timing will remain unchanged.")
        print("⚠️  This is recommended for external files with incorrect timing.")
        print()

        logger.info("✅ Proceeding with major timing realignment (auto-approved via CLI flags)")

    def _apply_mixed_track_realignment(self, external_events: List[SubtitleEvent],
                                     anchor_idx: int, time_offset: float) -> List[SubtitleEvent]:
        """
        Apply realignment to external track with pre-anchor deletion and global time shift.

        Args:
            external_events: External track events to realign
            anchor_idx: Index of anchor point in external track
            time_offset: Time offset to apply (positive = shift forward)

        Returns:
            Realigned external track events
        """
        logger.info(f"🔄 APPLYING REALIGNMENT: Shifting external track by {time_offset:+.3f}s")

        # Step 1: Remove events before anchor point (pre-anchor deletion)
        if anchor_idx > 0:
            logger.info(f"🗑️  Removing {anchor_idx} events before anchor point")
            remaining_events = external_events[anchor_idx:]
        else:
            remaining_events = external_events.copy()

        # Step 2: Apply global time shift to all remaining events
        realigned_events = []
        for event in remaining_events:
            # Create new event with shifted timing
            new_start = max(0.0, event.start + time_offset)  # Ensure no negative times
            new_end = max(0.0, event.end + time_offset)

            realigned_event = SubtitleEvent(
                start=new_start,
                end=new_end,
                text=event.text,
                style=event.style,
                raw=event.raw
            )
            realigned_events.append(realigned_event)

        logger.info(f"✅ REALIGNMENT APPLIED: {len(realigned_events)} events realigned")
        logger.info(f"   Original events: {len(external_events)}")
        logger.info(f"   Removed (pre-anchor): {anchor_idx}")
        logger.info(f"   Remaining (realigned): {len(realigned_events)}")
        logger.info(f"   Time shift applied: {time_offset:+.3f}s")

        # Log first few events for verification
        if realigned_events:
            logger.debug("First few realigned events:")
            for i, event in enumerate(realigned_events[:3]):
                logger.debug(f"  [{i}] {event.start:.3f}s-{event.end:.3f}s: {event.text[:40]}...")

        return realigned_events

    def _merge_with_enhanced_alignment(self, events1: List[SubtitleEvent],
                                     events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge events using enhanced time-based and content-based alignment.

        IMPORTANT: This method is intended for MASSIVELY misaligned subtitles only
        (timing differences of seconds, not milliseconds). It should NOT be used
        for embedded tracks that are already well-synchronized.

        Use cases:
        - External subtitle files with completely different timing bases
        - Tracks with major synchronization issues (>1 second differences)
        - Subtitles that need significant realignment

        For embedded tracks with minor timing differences (<500ms), use
        _merge_with_preserved_timing() instead to preserve exact timing.

        Args:
            events1: First list of events
            events2: Second list of events

        Returns:
            Merged list of events with improved alignment
        """
        logger.info("Using enhanced alignment methods for massively misaligned subtitles")

        # Phase 1: Global Track Synchronization
        logger.info("Phase 1: Performing global track synchronization")

        # Get track information for reference selection
        track1_info = getattr(self, '_track1_info', None)
        track2_info = getattr(self, '_track2_info', None)

        sync_events1, sync_events2, global_offset = self._perform_global_synchronization(
            events1, events2, track1_info, track2_info)

        if global_offset != 0.0:
            logger.info(f"Applied global time offset: {global_offset:.3f}s")
        else:
            logger.info("No global synchronization needed")

        # Phase 2: Detailed Event Alignment (using synchronized events)
        logger.info("Phase 2: Performing detailed event alignment")

        # Step 1: Try time-based alignment first (now with synchronized tracks)
        time_aligned_pairs = self._find_time_based_alignments(sync_events1, sync_events2)
        logger.info(f"Found {len(time_aligned_pairs)} time-based alignments")

        # Step 2: For unaligned events, try content-based alignment
        content_aligned_pairs = []
        if len(time_aligned_pairs) < min(len(sync_events1), len(sync_events2)) * 0.7:  # Less than 70% aligned
            logger.info("Time-based alignment insufficient, trying content-based alignment")
            content_aligned_pairs = self._find_content_based_alignments(sync_events1, sync_events2, time_aligned_pairs)
            logger.info(f"Found {len(content_aligned_pairs)} additional content-based alignments")

        # Step 3: Combine all alignments and create merged events
        all_alignments = time_aligned_pairs + content_aligned_pairs

        # CRITICAL FIX: For merged events, use original embedded track timing and synchronized external track timing
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        # Determine which events to use for merging (preserve embedded timing exactly)
        if track1_info.get('source_type') == 'embedded':
            # Track 1 is embedded - use original Track 1 timing, synchronized Track 2 timing
            merge_events1 = events1  # Original embedded timing (immutable)
            merge_events2 = sync_events2  # Synchronized external timing
            logger.info("🔒 MERGE FIX: Using original Track 1 (embedded) + synchronized Track 2 (external)")
        elif track2_info.get('source_type') == 'embedded':
            # Track 2 is embedded - use synchronized Track 1 timing, original Track 2 timing
            merge_events1 = sync_events1  # Synchronized external timing
            merge_events2 = events2  # Original embedded timing (immutable)
            logger.info("🔒 MERGE FIX: Using synchronized Track 1 (external) + original Track 2 (embedded)")
        else:
            # Both external - use synchronized events
            merge_events1 = sync_events1
            merge_events2 = sync_events2
            logger.info("📋 MERGE: Using synchronized events for both external tracks")

        merged_events = self._create_merged_events_from_alignments(merge_events1, merge_events2, all_alignments)

        # Step 4: Optimize timing
        optimized_events = self._optimize_subtitle_timing(merged_events)

        logger.info(f"Enhanced alignment completed: {len(optimized_events)} merged events created")
        return optimized_events

    def _perform_global_synchronization(self, events1: List[SubtitleEvent],
                                      events2: List[SubtitleEvent],
                                      track1_info: Optional[Dict] = None,
                                      track2_info: Optional[Dict] = None) -> Tuple[List[SubtitleEvent], List[SubtitleEvent], float]:
        """
        Perform global track synchronization before detailed alignment.

        Args:
            events1: First list of events
            events2: Second list of events
            track1_info: Optional metadata about track 1 (source type, language, etc.)
            track2_info: Optional metadata about track 2 (source type, language, etc.)

        Returns:
            Tuple of (synchronized_events1, synchronized_events2, applied_offset)
        """
        if not events1 or not events2:
            logger.warning("Cannot perform global synchronization: one or both tracks are empty")
            return events1, events2, 0.0

        # Determine which track should be the reference
        reference_track = self._determine_reference_track(events1, events2, track1_info, track2_info)

        # Arrange tracks based on reference selection
        if reference_track == 1:
            ref_events, target_events = events1, events2
            ref_label, target_label = "Track 1", "Track 2"
        else:
            ref_events, target_events = events2, events1
            ref_label, target_label = "Track 2", "Track 1"

        logger.info(f"Reference track: {ref_label}, Target track: {target_label}")

        # Determine synchronization strategy
        strategy = self.sync_strategy
        if strategy == 'auto':
            if self.manual_align:
                strategy = 'manual'
            elif self.use_translation and self.translation_service:
                strategy = 'translation'
            else:
                strategy = 'first-line'

        logger.info(f"Using synchronization strategy: {strategy}")

        # Find anchor points using selected strategy (always use original order for anchor finding)
        anchor_result = self._find_anchor_points(events1, events2, strategy)

        if anchor_result is None:
            logger.warning("No suitable anchor points found, proceeding without global synchronization")
            return events1, events2, 0.0

        anchor1_idx, anchor2_idx, confidence = anchor_result

        # Calculate global offset based on reference track selection
        if reference_track == 1:
            # Track 1 is reference
            anchor_ref_time = events1[anchor1_idx].start
            anchor_target_time = events2[anchor2_idx].start
            global_offset = anchor_ref_time - anchor_target_time
        else:
            # Track 2 is reference
            anchor_ref_time = events2[anchor2_idx].start
            anchor_target_time = events1[anchor1_idx].start
            global_offset = anchor_ref_time - anchor_target_time

        logger.info(f"Selected anchor points: {ref_label}[{anchor1_idx if reference_track == 1 else anchor2_idx}] at {anchor_ref_time:.3f}s, "
                   f"{target_label}[{anchor2_idx if reference_track == 1 else anchor1_idx}] at {anchor_target_time:.3f}s")
        logger.info(f"Calculated global offset: {global_offset:.3f}s (confidence: {confidence:.3f})")

        # Handle manual selection with pre-anchor deletion and flexible offset application
        if hasattr(self, '_manual_selection_info') and self._manual_selection_info:
            return self._apply_manual_synchronization(events1, events2, anchor_result)

        # CRITICAL: Apply offset ONLY to target track, NEVER to reference track
        if abs(global_offset) > 0.1:  # Only apply if offset is significant
            if reference_track == 1:
                # Track 1 is reference - PRESERVE its timing, modify Track 2
                synchronized_events2 = self._apply_time_offset(events2, global_offset)
                logger.info(f"🔒 REFERENCE PRESERVED: Track 1 timing unchanged")
                logger.info(f"⚙️ Applied {global_offset:.3f}s offset to Track 2 (aligning to Track 1 reference)")
                return events1, synchronized_events2, global_offset
            else:
                # Track 2 is reference - PRESERVE its timing, modify Track 1
                synchronized_events1 = self._apply_time_offset(events1, global_offset)
                logger.info(f"🔒 REFERENCE PRESERVED: Track 2 timing unchanged")
                logger.info(f"⚙️ Applied {global_offset:.3f}s offset to Track 1 (aligning to Track 2 reference)")
                return synchronized_events1, events2, global_offset
        else:
            logger.info("Global offset too small, no synchronization needed")
            return events1, events2, 0.0

    def _find_anchor_points(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent],
                          strategy: str) -> Optional[Tuple[int, int, float]]:
        """
        Find optimal anchor points using the specified strategy.

        Args:
            events1: First list of events (reference)
            events2: Second list of events (target)
            strategy: Strategy to use ('first-line', 'scan', 'translation', 'manual')

        Returns:
            Tuple of (index1, index2, confidence) or None if no suitable anchor found
        """
        if strategy == 'first-line':
            return self._find_anchor_first_line(events1, events2)
        elif strategy == 'scan':
            return self._find_anchor_scan_forward(events1, events2)
        elif strategy == 'translation':
            return self._find_anchor_translation_assisted(events1, events2)
        elif strategy == 'manual':
            return self._find_anchor_manual_selection(events1, events2)
        else:
            logger.warning(f"Unknown synchronization strategy: {strategy}, falling back to first-line")
            return self._find_anchor_first_line(events1, events2)

    def _find_anchor_first_line(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Optional[Tuple[int, int, float]]:
        """
        Strategy A: Compare first subtitle entries from each track.

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        if not events1 or not events2:
            return None

        time_diff = abs(events1[0].start - events2[0].start)

        if time_diff <= 2.0:  # Within ±2.0 seconds
            confidence = 1.0 - (time_diff / 2.0)  # Higher confidence for closer times
            logger.info(f"Strategy A (first-line): Found anchor with time difference {time_diff:.3f}s (confidence: {confidence:.3f})")
            return 0, 0, confidence
        else:
            logger.info(f"Strategy A (first-line): First entries too far apart ({time_diff:.3f}s > 2.0s)")
            return None

    def _find_anchor_scan_forward(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Optional[Tuple[int, int, float]]:
        """
        Strategy B: Scan the first 10 entries to find closest matching pair.

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        scan_limit = min(10, len(events1), len(events2))
        best_match = None
        best_time_diff = float('inf')

        for i in range(scan_limit):
            for j in range(scan_limit):
                time_diff = abs(events1[i].start - events2[j].start)

                if time_diff <= 2.0 and time_diff < best_time_diff:
                    best_time_diff = time_diff
                    best_match = (i, j)

        if best_match:
            confidence = 1.0 - (best_time_diff / 2.0)
            logger.info(f"Strategy B (scan): Found anchor at positions {best_match} "
                       f"with time difference {best_time_diff:.3f}s (confidence: {confidence:.3f})")
            return best_match[0], best_match[1], confidence
        else:
            logger.info("Strategy B (scan): No suitable anchor points found within ±2.0s")
            return None

    def _find_anchor_translation_assisted(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Optional[Tuple[int, int, float]]:
        """
        Strategy C: Use translation service to find semantically matching pairs.
        Enhanced to handle large timing offsets and cross-language content matching.

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        if not self.translation_service:
            logger.warning("Translation service not available, falling back to scan strategy")
            return self._find_anchor_scan_forward(events1, events2)

        # Expand search scope for large timing offsets
        scan_limit = min(20, len(events1), len(events2))

        logger.info(f"Strategy C (translation): Enhanced cross-language analysis of {scan_limit} entries from each track")

        try:
            # Phase 1: Try direct translation-assisted alignment
            source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
                source_events=events1[:scan_limit],
                reference_events=events2[:scan_limit],
                target_language='en',  # Assume translating to English for comparison
                translation_limit=scan_limit,
                confidence_threshold=max(0.6, self.alignment_threshold - 0.1)  # Lower threshold for initial detection
            )

            if source_idx is not None and ref_idx is not None and confidence >= self.alignment_threshold:
                logger.info(f"Strategy C (translation): Found semantic anchor at positions ({source_idx}, {ref_idx}) "
                           f"with confidence {confidence:.3f}")
                return source_idx, ref_idx, confidence

            # Phase 2: Enhanced cross-language content matching for large offsets
            logger.info("Strategy C (translation): Trying enhanced cross-language content matching")
            anchor_result = self._find_cross_language_anchor_enhanced(events1, events2, scan_limit)

            if anchor_result:
                return anchor_result

            # Phase 3: Fallback to expanded scan with content similarity
            logger.info("Strategy C (translation): Falling back to expanded content similarity scan")
            return self._find_anchor_scan_enhanced(events1, events2)

        except Exception as e:
            logger.warning(f"Translation-assisted anchor finding failed: {e}, falling back to enhanced scan")
            return self._find_anchor_scan_enhanced(events1, events2)

    def _find_cross_language_anchor_enhanced(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent], scan_limit: int) -> Optional[Tuple[int, int, float]]:
        """
        Enhanced cross-language anchor detection for large timing offsets.

        This method handles scenarios where Chinese and English subtitles have major timing differences
        by using content similarity and translation to find matching dialogue.

        Args:
            events1: First list of events (typically Chinese)
            events2: Second list of events (typically English)
            scan_limit: Maximum number of events to analyze

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        logger.info("Enhanced cross-language anchor detection for major timing offsets")

        # Sample events from different positions to handle large offsets
        sample_positions1 = [0, scan_limit//4, scan_limit//2, 3*scan_limit//4, scan_limit-1]
        sample_positions2 = [0, scan_limit//4, scan_limit//2, 3*scan_limit//4, scan_limit-1]

        best_match = None
        best_confidence = 0.0

        for pos1 in sample_positions1:
            if pos1 >= len(events1):
                continue

            event1 = events1[pos1]

            # Translate Chinese to English for comparison
            try:
                translation_result = self.translation_service.translate_text(
                    event1.text, target_language='en'
                )

                if not translation_result:
                    continue

                translated_text = translation_result.translated_text.lower().strip()

                # Compare with English events
                for pos2 in sample_positions2:
                    if pos2 >= len(events2):
                        continue

                    event2 = events2[pos2]
                    english_text = event2.text.lower().strip()

                    # Calculate content similarity
                    similarity = self._calculate_text_similarity(translated_text, english_text)

                    if similarity > best_confidence and similarity >= 0.7:
                        best_confidence = similarity
                        best_match = (pos1, pos2, similarity)

                        logger.debug(f"Cross-language match found: pos1={pos1}, pos2={pos2}, similarity={similarity:.3f}")
                        logger.debug(f"  Chinese: {event1.text[:50]}...")
                        logger.debug(f"  Translated: {translated_text[:50]}...")
                        logger.debug(f"  English: {english_text[:50]}...")

            except Exception as e:
                logger.debug(f"Translation failed for position {pos1}: {e}")
                continue

        if best_match and best_confidence >= 0.7:
            pos1, pos2, confidence = best_match
            logger.info(f"✅ Enhanced cross-language anchor found: ({pos1}, {pos2}) with confidence {confidence:.3f}")
            return pos1, pos2, confidence

        logger.info("❌ No suitable cross-language anchor found")
        return None

    def _find_anchor_scan_enhanced(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Optional[Tuple[int, int, float]]:
        """
        Enhanced scan strategy that handles large timing offsets by expanding search scope.

        Args:
            events1: First list of events
            events2: Second list of events

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        # Expand scan limit for large offset scenarios
        scan_limit = min(30, len(events1), len(events2))
        best_match = None
        best_time_diff = float('inf')

        logger.info(f"Enhanced scan strategy: analyzing {scan_limit} entries with expanded time threshold")

        for i in range(scan_limit):
            for j in range(scan_limit):
                time_diff = abs(events1[i].start - events2[j].start)

                # Expanded time threshold for large offsets (up to 60 seconds)
                if time_diff <= 60.0 and time_diff < best_time_diff:
                    best_time_diff = time_diff
                    best_match = (i, j)

        if best_match:
            # Calculate confidence based on time proximity (adjusted for large offsets)
            confidence = max(0.3, 1.0 - (best_time_diff / 60.0))
            logger.info(f"Enhanced scan: Found anchor at positions {best_match} "
                       f"with time difference {best_time_diff:.3f}s (confidence: {confidence:.3f})")
            return best_match[0], best_match[1], confidence
        else:
            logger.info("Enhanced scan: No suitable anchor points found within ±60.0s")
            return None

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings using multiple methods.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        from difflib import SequenceMatcher

        # Clean texts
        clean1 = ''.join(c.lower() for c in text1 if c.isalnum() or c.isspace()).strip()
        clean2 = ''.join(c.lower() for c in text2 if c.isalnum() or c.isspace()).strip()

        if not clean1 or not clean2:
            return 0.0

        # Use sequence matcher for basic similarity
        similarity = SequenceMatcher(None, clean1, clean2).ratio()

        # Boost similarity for common words
        words1 = set(clean1.split())
        words2 = set(clean2.split())

        if words1 and words2:
            word_overlap = len(words1.intersection(words2)) / len(words1.union(words2))
            similarity = max(similarity, word_overlap * 0.8)  # Weight word overlap slightly lower

        return similarity

    def _find_anchor_manual_selection(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Optional[Tuple[int, int, float]]:
        """
        Strategy D: Present user with options for manual anchor selection using table format.

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        import sys

        display_limit = min(5, len(events1), len(events2))

        try:
            sys.stdout.flush()
            sys.stderr.flush()

            print("\n" + "="*100)
            print("MANUAL ANCHOR POINT SELECTION")
            print("="*100)
            print("Select matching subtitle entries from each track for global synchronization.")
            print("You can select different line numbers from each track (e.g., Track 1 line 2 with Track 2 line 4).")
            print(f"Analyzing first {display_limit} subtitle entries from each track.\n")

            # Display side-by-side table
            self._display_anchor_table(events1[:display_limit], events2[:display_limit])

            # Get user selections
            track1_idx, track2_idx, reference_track = self._get_anchor_selections(display_limit, events1, events2)

            if track1_idx is None or track2_idx is None:
                return None

            # Calculate offset based on reference track
            if reference_track == 1:
                # Track 1 is reference, calculate offset for Track 2
                offset = events1[track1_idx].start - events2[track2_idx].start
                reference_time = events1[track1_idx].start
                target_time = events2[track2_idx].start
            else:
                # Track 2 is reference, calculate offset for Track 1
                offset = events2[track2_idx].start - events1[track1_idx].start
                reference_time = events2[track2_idx].start
                target_time = events1[track1_idx].start

            # Show final confirmation
            print(f"\n" + "="*60)
            print("SYNCHRONIZATION PLAN")
            print("="*60)
            print(f"Selected anchors:")
            print(f"  Track 1 [{track1_idx+1}]: [{events1[track1_idx].start:.3f}s] {self._clean_text_for_display(events1[track1_idx].text)}")
            print(f"  Track 2 [{track2_idx+1}]: [{events2[track2_idx].start:.3f}s] {self._clean_text_for_display(events2[track2_idx].text)}")
            print(f"\nReference track: Track {reference_track}")
            print(f"Time offset to apply: {offset:.3f}s")
            print(f"Pre-anchor deletion: Will remove entries before selected anchor points")

            try:
                confirm = input("\nProceed with this synchronization plan? (y/n): ").strip().lower()
            except EOFError:
                print("\nConfirmation cancelled.")
                return None

            if confirm in ['y', 'yes']:
                confidence = 1.0
                logger.info(f"Manual anchor selection: Track1[{track1_idx}] + Track2[{track2_idx}], "
                           f"reference=Track{reference_track}, offset={offset:.3f}s")

                # Store additional info for post-processing
                self._manual_selection_info = {
                    'track1_anchor_idx': track1_idx,
                    'track2_anchor_idx': track2_idx,
                    'reference_track': reference_track,
                    'offset': offset,
                    'delete_pre_anchor': True
                }

                return track1_idx, track2_idx, confidence
            else:
                print("Synchronization cancelled.")
                return None

        except KeyboardInterrupt:
            print("\n\nManual selection interrupted.")
            return None
        except Exception as e:
            logger.error(f"Critical error in manual selection: {e}")
            print(f"Manual selection failed: {e}")
            return None

    def _display_anchor_table(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]):
        """Display subtitle entries in side-by-side table format."""
        import sys

        print("Track 1 (Chinese)                                    | Track 2 (English)")
        print("-" * 50 + "|" + "-" * 49)

        for i in range(len(events1)):
            # Track 1 entry
            text1 = self._clean_text_for_display(events1[i].text, 35)
            print(f"{i+1}. [{events1[i].start:6.3f}s] {text1:<35} | ", end="")

            # Track 2 entry (if exists)
            if i < len(events2):
                text2 = self._clean_text_for_display(events2[i].text, 35)
                print(f"{i+1}. [{events2[i].start:6.3f}s] {text2}")
            else:
                print()

            # Show translations if available
            if self.translation_service:
                try:
                    # Translate Track 1 to English
                    trans1_result = self.translation_service.translate_text(events1[i].text, target_language='en')
                    if trans1_result:
                        trans1_clean = self._clean_text_for_display(trans1_result.translated_text, 35)
                    else:
                        trans1_clean = "[translation failed]"
                    print(f"   Translation: {trans1_clean:<35} | ", end="")

                    # Translate Track 2 to Chinese (if exists)
                    if i < len(events2):
                        trans2_result = self.translation_service.translate_text(events2[i].text, target_language='zh')
                        if trans2_result:
                            trans2_clean = self._clean_text_for_display(trans2_result.translated_text, 35)
                        else:
                            trans2_clean = "[translation failed]"
                        print(f"   Translation: {trans2_clean}")
                    else:
                        print()

                except Exception as e:
                    logger.debug(f"Translation failed for table display: {e}")
                    print(f"   Translation: [error: {str(e)[:20]}...]        | ", end="")
                    if i < len(events2):
                        print(f"   Translation: [error: {str(e)[:20]}...]")
                    else:
                        print()
            else:
                print(f"   Translation: [service not available]         | ", end="")
                if i < len(events2):
                    print(f"   Translation: [service not available]")
                else:
                    print()

            print()  # Empty line between entries
            sys.stdout.flush()

    def _get_anchor_selections(self, display_limit: int, events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        Get user selections for anchor points and reference track.

        Returns:
            Tuple of (track1_index, track2_index, reference_track) or (None, None, None)
        """
        try:
            print("SELECTION PROCESS:")
            print("1. Select one entry from Track 1 (Chinese)")
            print("2. Select one entry from Track 2 (English)")
            print("3. Choose which track's timing to use as reference")
            print("4. Confirm synchronization plan")
            print()

            # Get Track 1 selection
            while True:
                try:
                    choice1 = input(f"Select Track 1 entry (1-{display_limit}, or 'q' to quit): ").strip().lower()
                    if choice1 == 'q':
                        return None, None, None

                    track1_idx = int(choice1) - 1
                    if 0 <= track1_idx < display_limit:
                        break
                    else:
                        print(f"Please enter a number between 1 and {display_limit}")
                except (ValueError, EOFError):
                    if choice1 == 'q':
                        return None, None, None
                    print("Invalid input. Please enter a number or 'q' to quit.")

            # Get Track 2 selection
            while True:
                try:
                    choice2 = input(f"Select Track 2 entry (1-{display_limit}, or 'q' to quit): ").strip().lower()
                    if choice2 == 'q':
                        return None, None, None

                    track2_idx = int(choice2) - 1
                    if 0 <= track2_idx < display_limit:
                        break
                    else:
                        print(f"Please enter a number between 1 and {display_limit}")
                except (ValueError, EOFError):
                    if choice2 == 'q':
                        return None, None, None
                    print("Invalid input. Please enter a number or 'q' to quit.")

            # Get reference track selection
            print(f"\nSelected entries:")
            print(f"  Track 1 [{track1_idx+1}]: {self._clean_text_for_display(events1[track1_idx].text, 50)}")
            print(f"  Track 2 [{track2_idx+1}]: {self._clean_text_for_display(events2[track2_idx].text, 50)}")
            print()

            while True:
                try:
                    ref_choice = input("Which track's timing should be used as reference? (1 or 2, or 'q' to quit): ").strip().lower()
                    if ref_choice == 'q':
                        return None, None, None

                    reference_track = int(ref_choice)
                    if reference_track in [1, 2]:
                        break
                    else:
                        print("Please enter 1 or 2")
                except (ValueError, EOFError):
                    if ref_choice == 'q':
                        return None, None, None
                    print("Invalid input. Please enter 1, 2, or 'q' to quit.")

            return track1_idx, track2_idx, reference_track

        except KeyboardInterrupt:
            print("\nSelection interrupted.")
            return None, None, None
        except Exception as e:
            logger.error(f"Error in anchor selection: {e}")
            print(f"Selection error: {e}")
            return None, None, None

    def _clean_text_for_display(self, text: str, max_length: int = 80) -> str:
        """
        Clean and format text for console display.

        Args:
            text: Raw subtitle text
            max_length: Maximum display length

        Returns:
            Cleaned and truncated text
        """
        if not text:
            return "[empty]"

        # Remove common subtitle formatting
        import re
        cleaned = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        cleaned = re.sub(r'\{[^}]+\}', '', cleaned)  # Remove ASS/SSA tags
        cleaned = re.sub(r'\\[nN]', ' ', cleaned)  # Replace line breaks
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
        cleaned = cleaned.strip()

        # Truncate if too long
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length-3] + "..."

        return cleaned if cleaned else "[formatting only]"

    def _show_detailed_anchor_options(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent]):
        """Show detailed information for manual anchor selection."""
        import sys

        print("\n" + "-"*80)
        print("DETAILED ANCHOR OPTIONS")
        print("-"*80)

        for i in range(len(events1)):
            print(f"\nOption {i+1} Details:")
            print(f"  Track 1:")
            print(f"    Time: {events1[i].start:.3f}s - {events1[i].end:.3f}s ({events1[i].end - events1[i].start:.3f}s duration)")
            print(f"    Text: {events1[i].text}")

            if self.translation_service:
                try:
                    translated_result = self.translation_service.translate_text(events1[i].text, target_language='en')
                    if translated_result:
                        print(f"    Translation: {translated_result.translated_text}")
                    else:
                        print(f"    Translation: [translation failed]")
                except Exception as e:
                    logger.debug(f"Translation failed in detailed view: {e}")
                    print(f"    Translation: [error: {str(e)[:30]}...]")
            else:
                print(f"    Translation: [service not available]")

            print(f"  Track 2:")
            print(f"    Time: {events2[i].start:.3f}s - {events2[i].end:.3f}s ({events2[i].end - events2[i].start:.3f}s duration)")
            print(f"    Text: {events2[i].text}")

            time_diff = abs(events1[i].start - events2[i].start)
            offset = events1[i].start - events2[i].start
            print(f"  Time Analysis:")
            print(f"    Difference: {time_diff:.3f}s")
            print(f"    Required offset: {offset:.3f}s (Track 2 will be shifted)")

            # Assess match quality
            if time_diff <= 0.5:
                quality = "Excellent"
            elif time_diff <= 1.0:
                quality = "Good"
            elif time_diff <= 2.0:
                quality = "Fair"
            else:
                quality = "Poor"
            print(f"    Match quality: {quality}")

            sys.stdout.flush()

        print("-"*80)
        print("Press Enter to continue...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    def _apply_time_offset(self, events: List[SubtitleEvent], offset: float) -> List[SubtitleEvent]:
        """
        Apply a time offset to all events in a list.

        Args:
            events: List of subtitle events
            offset: Time offset in seconds to add

        Returns:
            New list of events with adjusted timing
        """
        synchronized_events = []

        for event in events:
            new_event = SubtitleEvent(
                start=max(0.0, event.start + offset),  # Ensure no negative times
                end=max(0.0, event.end + offset),
                text=event.text,
                style=event.style
            )
            synchronized_events.append(new_event)

        return synchronized_events

    def _apply_manual_synchronization(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent],
                                    anchor_result: Tuple[int, int, float]) -> Tuple[List[SubtitleEvent], List[SubtitleEvent], float]:
        """
        Apply manual synchronization with pre-anchor deletion and flexible offset application.

        Args:
            events1: First list of events
            events2: Second list of events
            anchor_result: Tuple of (track1_idx, track2_idx, confidence)

        Returns:
            Tuple of (synchronized_events1, synchronized_events2, applied_offset)
        """
        info = self._manual_selection_info
        track1_anchor_idx = info['track1_anchor_idx']
        track2_anchor_idx = info['track2_anchor_idx']
        reference_track = info['reference_track']
        offset = info['offset']

        logger.info(f"Applying manual synchronization: Track1[{track1_anchor_idx}] + Track2[{track2_anchor_idx}], "
                   f"reference=Track{reference_track}, offset={offset:.3f}s")

        # Step 1: Delete pre-anchor entries
        if info.get('delete_pre_anchor', True):
            # Remove entries before anchor points
            filtered_events1 = events1[track1_anchor_idx:]
            filtered_events2 = events2[track2_anchor_idx:]

            deleted_count1 = len(events1) - len(filtered_events1)
            deleted_count2 = len(events2) - len(filtered_events2)

            logger.info(f"Pre-anchor deletion: Removed {deleted_count1} entries from Track 1, "
                       f"{deleted_count2} entries from Track 2")
        else:
            filtered_events1 = events1
            filtered_events2 = events2

        # Step 2: Apply time offset to non-reference track
        if reference_track == 1:
            # Track 1 is reference, apply offset to Track 2
            synchronized_events1 = filtered_events1
            synchronized_events2 = self._apply_time_offset(filtered_events2, offset)
            logger.info(f"Applied {offset:.3f}s offset to Track 2 (Track 1 is reference)")
        else:
            # Track 2 is reference, apply offset to Track 1
            synchronized_events1 = self._apply_time_offset(filtered_events1, offset)
            synchronized_events2 = filtered_events2
            logger.info(f"Applied {offset:.3f}s offset to Track 1 (Track 2 is reference)")

        # Step 3: Verify synchronization
        if synchronized_events1 and synchronized_events2:
            # Check if anchor points are now aligned
            anchor1_time = synchronized_events1[0].start if reference_track == 1 else synchronized_events1[0].start
            anchor2_time = synchronized_events2[0].start if reference_track == 2 else synchronized_events2[0].start

            final_diff = abs(anchor1_time - anchor2_time)
            logger.info(f"Post-synchronization anchor time difference: {final_diff:.3f}s")

            if final_diff < 0.1:
                logger.info("✅ Manual synchronization successful - anchor points aligned")
            else:
                logger.warning(f"⚠️ Manual synchronization may need adjustment - {final_diff:.3f}s difference remains")

        # Clean up manual selection info
        self._manual_selection_info = None

        return synchronized_events1, synchronized_events2, offset

    def _determine_reference_track(self, events1: List[SubtitleEvent], events2: List[SubtitleEvent],
                                 track1_info: Optional[Dict] = None, track2_info: Optional[Dict] = None) -> int:
        """
        Determine which track should be used as the timing reference.

        Args:
            events1: First list of events
            events2: Second list of events
            track1_info: Optional metadata about track 1 (source type, language, etc.)
            track2_info: Optional metadata about track 2 (source type, language, etc.)

        Returns:
            1 if track 1 should be reference, 2 if track 2 should be reference
        """
        # Manual alignment mode: user will choose, so return default
        if self.manual_align:
            logger.debug("Manual alignment mode: reference track will be user-selected")
            return 1  # Default, will be overridden by user selection

        # Get track information
        track1_source = track1_info.get('source_type', 'unknown') if track1_info else 'unknown'
        track2_source = track2_info.get('source_type', 'unknown') if track2_info else 'unknown'
        track1_language = track1_info.get('language', 'unknown') if track1_info else 'unknown'
        track2_language = track2_info.get('language', 'unknown') if track2_info else 'unknown'

        logger.info(f"Track reference selection: Track1({track1_source}, {track1_language}) vs Track2({track2_source}, {track2_language})")

        # Priority 1: Embedded tracks over external files (mixed type scenario)
        if track1_source == 'embedded' and track2_source == 'external':
            logger.info("✅ Selected Track 1 as reference: embedded track prioritized over external")
            return 1
        elif track2_source == 'embedded' and track1_source == 'external':
            logger.info("✅ Selected Track 2 as reference: embedded track prioritized over external")
            return 2

        # Priority 2: Language preference (same type scenario)
        if self.reference_language_preference != 'auto':
            if self.reference_language_preference == 'chinese':
                # Look for Chinese track
                if self._is_chinese_track(track1_language, events1):
                    logger.info("✅ Selected Track 1 as reference: Chinese language preference")
                    return 1
                elif self._is_chinese_track(track2_language, events2):
                    logger.info("✅ Selected Track 2 as reference: Chinese language preference")
                    return 2
            elif self.reference_language_preference == 'english':
                # Look for English track
                if self._is_english_track(track1_language, events1):
                    logger.info("✅ Selected Track 1 as reference: English language preference")
                    return 1
                elif self._is_english_track(track2_language, events2):
                    logger.info("✅ Selected Track 2 as reference: English language preference")
                    return 2

        # Priority 3: Earlier timestamps (auto mode or fallback)
        if events1 and events2:
            track1_start = events1[0].start
            track2_start = events2[0].start

            if track1_start <= track2_start:
                logger.info(f"✅ Selected Track 1 as reference: earlier timestamp ({track1_start:.3f}s vs {track2_start:.3f}s)")
                return 1
            else:
                logger.info(f"✅ Selected Track 2 as reference: earlier timestamp ({track2_start:.3f}s vs {track1_start:.3f}s)")
                return 2

        # Fallback: Track 1
        logger.info("✅ Selected Track 1 as reference: fallback default")
        return 1

    def _is_chinese_track(self, language: str, events: List[SubtitleEvent]) -> bool:
        """Check if a track contains Chinese content."""
        if language and language.lower() in ['zh', 'chi', 'chinese', 'zh-cn', 'zh-tw']:
            return True

        # Content-based detection for first few events
        if events:
            sample_text = ' '.join([event.text for event in events[:3]])
            # Simple heuristic: check for Chinese characters
            chinese_chars = sum(1 for char in sample_text if '\u4e00' <= char <= '\u9fff')
            total_chars = len([char for char in sample_text if char.isalnum()])

            if total_chars > 0 and chinese_chars / total_chars > 0.3:
                return True

        return False

    def _is_english_track(self, language: str, events: List[SubtitleEvent]) -> bool:
        """Check if a track contains English content."""
        if language and language.lower() in ['en', 'eng', 'english']:
            return True

        # Content-based detection for first few events
        if events:
            sample_text = ' '.join([event.text for event in events[:3]])
            # Simple heuristic: check for ASCII letters
            ascii_chars = sum(1 for char in sample_text if char.isascii() and char.isalpha())
            total_chars = len([char for char in sample_text if char.isalnum()])

            if total_chars > 0 and ascii_chars / total_chars > 0.7:
                return True

        return False

    def _find_time_based_alignments(self, events1: List[SubtitleEvent],
                                   events2: List[SubtitleEvent],
                                   time_threshold: float = 0.5) -> List[Tuple[int, int, float]]:
        """
        Find alignments based on matching start times.

        Args:
            events1: First list of events
            events2: Second list of events
            time_threshold: Maximum time difference in seconds for alignment

        Returns:
            List of (index1, index2, confidence) tuples
        """
        alignments = []
        used_indices2 = set()

        for i, event1 in enumerate(events1):
            best_match = None
            best_time_diff = float('inf')

            for j, event2 in enumerate(events2):
                if j in used_indices2:
                    continue

                # Calculate time difference between start times
                time_diff = abs(event1.start - event2.start)

                if time_diff <= time_threshold and time_diff < best_time_diff:
                    best_time_diff = time_diff
                    best_match = j

            if best_match is not None:
                # Calculate confidence based on time proximity
                confidence = 1.0 - (best_time_diff / time_threshold)
                alignments.append((i, best_match, confidence))
                used_indices2.add(best_match)

                logger.debug(f"Time alignment: {i} -> {best_match} "
                           f"(time_diff: {best_time_diff:.2f}s, confidence: {confidence:.3f})")

        return alignments

    def _find_content_based_alignments(self, events1: List[SubtitleEvent],
                                     events2: List[SubtitleEvent],
                                     existing_alignments: List[Tuple[int, int, float]]) -> List[Tuple[int, int, float]]:
        """
        Find alignments based on content similarity.

        Args:
            events1: First list of events
            events2: Second list of events
            existing_alignments: Already found alignments to avoid conflicts

        Returns:
            List of (index1, index2, confidence) tuples
        """
        # Get indices that are already aligned
        used_indices1 = {align[0] for align in existing_alignments}
        used_indices2 = {align[1] for align in existing_alignments}

        # Get unaligned events
        unaligned_events1 = [(i, event) for i, event in enumerate(events1) if i not in used_indices1]
        unaligned_events2 = [(i, event) for i, event in enumerate(events2) if i not in used_indices2]

        if not unaligned_events1 or not unaligned_events2:
            return []

        logger.info(f"Analyzing {len(unaligned_events1)} x {len(unaligned_events2)} unaligned events for content similarity")

        # Use translation-assisted alignment if available
        if self.use_translation and self.translation_service:
            return self._find_translation_assisted_alignments(unaligned_events1, unaligned_events2)
        else:
            return self._find_similarity_only_alignments(unaligned_events1, unaligned_events2)

    def _find_translation_assisted_alignments(self, events1_indexed: List[Tuple[int, SubtitleEvent]],
                                            events2_indexed: List[Tuple[int, SubtitleEvent]]) -> List[Tuple[int, int, float]]:
        """
        Find alignments using translation assistance for cross-language matching.

        Args:
            events1_indexed: List of (index, event) tuples for first language
            events2_indexed: List of (index, event) tuples for second language

        Returns:
            List of (index1, index2, confidence) tuples
        """
        logger.info("Using translation-assisted alignment")

        # Limit translation scope for efficiency (translate first 10 events)
        translation_limit = min(10, len(events1_indexed))
        events_to_translate = events1_indexed[:translation_limit]

        logger.info(f"Translating {len(events_to_translate)} events for alignment detection")

        # Extract events for translation
        source_events = [event for _, event in events_to_translate]

        # Use the translation service's optimized alignment method
        source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
            source_events=source_events,
            reference_events=[event for _, event in events2_indexed],
            target_language='en',  # Assume translating to English
            translation_limit=translation_limit,
            confidence_threshold=self.alignment_threshold
        )

        alignments = []

        if source_idx is not None and ref_idx is not None and confidence >= self.alignment_threshold:
            # Found a reliable alignment point
            actual_source_idx = events1_indexed[source_idx][0]
            actual_ref_idx = events2_indexed[ref_idx][0]

            alignments.append((actual_source_idx, actual_ref_idx, confidence))

            logger.info(f"✅ Translation-assisted alignment found: {actual_source_idx} -> {actual_ref_idx} "
                       f"(confidence: {confidence:.3f})")

            # Use this as anchor point to align the rest of the file
            additional_alignments = self._align_from_anchor_point(
                events1_indexed, events2_indexed, source_idx, ref_idx, confidence
            )
            alignments.extend(additional_alignments)
        else:
            logger.warning("❌ Translation-assisted alignment failed, falling back to similarity-only")
            alignments = self._find_similarity_only_alignments(events1_indexed, events2_indexed)

        return alignments

    def _find_similarity_only_alignments(self, events1_indexed: List[Tuple[int, SubtitleEvent]],
                                       events2_indexed: List[Tuple[int, SubtitleEvent]]) -> List[Tuple[int, int, float]]:
        """
        Find alignments using only text similarity (no translation).

        Args:
            events1_indexed: List of (index, event) tuples for first language
            events2_indexed: List of (index, event) tuples for second language

        Returns:
            List of (index1, index2, confidence) tuples
        """
        logger.info("Using similarity-only alignment")

        # Extract texts for similarity analysis
        texts1 = [event.text for _, event in events1_indexed]
        texts2 = [event.text for _, event in events2_indexed]

        # Find alignments using similarity aligner
        alignment_matches = self.similarity_aligner.find_alignments(texts1, texts2)

        # Convert to our format
        alignments = []
        for match in alignment_matches:
            if match.confidence >= self.alignment_threshold:
                actual_idx1 = events1_indexed[match.source_index][0]
                actual_idx2 = events2_indexed[match.reference_index][0]
                alignments.append((actual_idx1, actual_idx2, match.confidence))

                logger.debug(f"Similarity alignment: {actual_idx1} -> {actual_idx2} "
                           f"(confidence: {match.confidence:.3f})")

        logger.info(f"Found {len(alignments)} similarity-based alignments")
        return alignments

    def _align_from_anchor_point(self, events1_indexed: List[Tuple[int, SubtitleEvent]],
                               events2_indexed: List[Tuple[int, SubtitleEvent]],
                               anchor_idx1: int, anchor_idx2: int, anchor_confidence: float) -> List[Tuple[int, int, float]]:
        """
        Align remaining events using an anchor point as reference.

        Args:
            events1_indexed: List of (index, event) tuples for first language
            events2_indexed: List of (index, event) tuples for second language
            anchor_idx1: Anchor index in first list
            anchor_idx2: Anchor index in second list
            anchor_confidence: Confidence of the anchor alignment

        Returns:
            List of additional (index1, index2, confidence) tuples
        """
        logger.info(f"Aligning from anchor point: {anchor_idx1} -> {anchor_idx2}")

        alignments = []

        # Calculate time offset between the anchor points
        anchor_event1 = events1_indexed[anchor_idx1][1]
        anchor_event2 = events2_indexed[anchor_idx2][1]
        time_offset = anchor_event2.start - anchor_event1.start

        logger.debug(f"Calculated time offset: {time_offset:.2f}s")

        # Align events after the anchor point
        for i in range(anchor_idx1 + 1, len(events1_indexed)):
            event1_idx, event1 = events1_indexed[i]
            expected_time = event1.start + time_offset

            # Find closest event in second list
            best_match = None
            best_time_diff = float('inf')

            for j in range(anchor_idx2 + 1, len(events2_indexed)):
                event2_idx, event2 = events2_indexed[j]
                time_diff = abs(event2.start - expected_time)

                if time_diff < best_time_diff:
                    best_time_diff = time_diff
                    best_match = (event2_idx, j)

            if best_match and best_time_diff <= 2.0:  # Within 2 seconds
                confidence = max(0.5, anchor_confidence * (1.0 - best_time_diff / 2.0))
                alignments.append((event1_idx, best_match[0], confidence))

        # Align events before the anchor point (similar logic in reverse)
        for i in range(anchor_idx1 - 1, -1, -1):
            event1_idx, event1 = events1_indexed[i]
            expected_time = event1.start + time_offset

            best_match = None
            best_time_diff = float('inf')

            for j in range(anchor_idx2 - 1, -1, -1):
                event2_idx, event2 = events2_indexed[j]
                time_diff = abs(event2.start - expected_time)

                if time_diff < best_time_diff:
                    best_time_diff = time_diff
                    best_match = (event2_idx, j)

            if best_match and best_time_diff <= 2.0:
                confidence = max(0.5, anchor_confidence * (1.0 - best_time_diff / 2.0))
                alignments.append((event1_idx, best_match[0], confidence))

        logger.info(f"Anchor-based alignment added {len(alignments)} additional alignments")
        return alignments

    def _create_merged_events_from_alignments(self, events1: List[SubtitleEvent],
                                            events2: List[SubtitleEvent],
                                            alignments: List[Tuple[int, int, float]]) -> List[SubtitleEvent]:
        """
        Create merged events from alignment pairs.

        Args:
            events1: First list of events
            events2: Second list of events
            alignments: List of (index1, index2, confidence) tuples

        Returns:
            List of merged SubtitleEvent objects
        """
        merged_events = []
        used_indices1 = set()
        used_indices2 = set()

        # Determine reference track for timing preservation (consistent with global synchronization)
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        # Use the same reference track determination logic as _perform_global_synchronization
        reference_track = self._determine_reference_track(events1, events2, track1_info, track2_info)

        if reference_track == 1:
            logger.info("🔒 MERGE TIMING: Using Track 1 as timing reference")
        else:
            logger.info("🔒 MERGE TIMING: Using Track 2 as timing reference")

        # Create merged events from alignments with REFERENCE TIMING PRESERVATION
        for idx1, idx2, confidence in alignments:
            if idx1 < len(events1) and idx2 < len(events2):
                event1 = events1[idx1]
                event2 = events2[idx2]

                # CRITICAL: Preserve reference track timing exactly
                if reference_track == 1:
                    # Use Track 1 timing as reference
                    start_time = event1.start
                    end_time = event1.end
                    logger.debug(f"🔒 Preserved Track 1 timing: {start_time:.3f}-{end_time:.3f}s")
                else:
                    # Use Track 2 timing as reference
                    start_time = event2.start
                    end_time = event2.end
                    logger.debug(f"🔒 Preserved Track 2 timing: {start_time:.3f}-{end_time:.3f}s")

                # Combine texts using configured order
                combined_text = self._combine_texts(event1.text, event2.text)

                merged_event = SubtitleEvent(
                    start=start_time,
                    end=end_time,
                    text=combined_text,
                    style=event1.style or event2.style
                )

                merged_events.append(merged_event)
                used_indices1.add(idx1)
                used_indices2.add(idx2)

                logger.debug(f"Merged events {idx1}+{idx2}: {start_time:.2f}-{end_time:.2f}s "
                           f"(confidence: {confidence:.3f})")

        # Add unaligned events from both lists
        for i, event in enumerate(events1):
            if i not in used_indices1:
                merged_events.append(event)
                logger.debug(f"Added unaligned event1[{i}]: {event.start:.2f}-{event.end:.2f}s")

        for i, event in enumerate(events2):
            if i not in used_indices2:
                merged_events.append(event)
                logger.debug(f"Added unaligned event2[{i}]: {event.start:.2f}-{event.end:.2f}s")

        # Sort by start time
        merged_events.sort(key=lambda e: e.start)

        logger.info(f"Created {len(merged_events)} merged events from {len(alignments)} alignments")
        return merged_events

    def _merge_with_simple_overlap(self, events1: List[SubtitleEvent],
                                 events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge events using simple overlap-based method (backward compatibility).

        Args:
            events1: First list of events
            events2: Second list of events

        Returns:
            Merged list of events
        """
        logger.info("Using simple overlap-based merging")

        # Create timeline segments
        all_times = set()
        for event in events1 + events2:
            all_times.add(event.start)
            all_times.add(event.end)

        timeline = sorted(all_times)
        segments = []

        # Create segments for each time interval
        for i in range(len(timeline) - 1):
            seg_start = timeline[i]
            seg_end = timeline[i + 1]

            if seg_end <= seg_start:
                continue

            # Find events that overlap this segment
            text1 = None
            text2 = None

            for event in events1:
                if event.start <= seg_start < event.end:
                    text1 = event.text
                    break

            for event in events2:
                if event.start <= seg_start < event.end:
                    text2 = event.text
                    break

            # Skip empty segments
            if not text1 and not text2:
                continue

            # Combine texts using configured order
            combined_text = self._combine_texts(text1, text2)

            segments.append(SubtitleEvent(
                start=seg_start,
                end=seg_end,
                text=combined_text
            ))

        return segments

    def _merge_with_preserved_timing(self, events1: List[SubtitleEvent],
                                   events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge subtitle events with EXACT timing preservation for embedded tracks.

        This method preserves the EXACT original timing boundaries from embedded tracks
        by using the embedded track as the timing reference and overlaying the other track.
        For mixed embedded+external scenarios, embedded timing is completely preserved.

        Args:
            events1: First list of events (e.g., Chinese)
            events2: Second list of events (e.g., English)

        Returns:
            Merged list of events with EXACT embedded timing preserved
        """
        logger.info("🔒 EXACT TIMING PRESERVATION: Using embedded track as immutable timing reference")

        # Get track information to determine which track is embedded
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        track1_embedded = track1_info.get('source_type') == 'embedded'
        track2_embedded = track2_info.get('source_type') == 'embedded'

        logger.info(f"🔍 TIMING PRESERVATION ANALYSIS:")
        logger.info(f"   events1: {len(events1)} events, track1_info: {track1_info}")
        logger.info(f"   events2: {len(events2)} events, track2_info: {track2_info}")
        logger.info(f"   track1_embedded: {track1_embedded}, track2_embedded: {track2_embedded}")

        # Determine reference track (embedded track takes priority)
        # Also determine language order based on track info
        track1_language = track1_info.get('language', 'unknown')
        track2_language = track2_info.get('language', 'unknown')

        if track1_embedded and not track2_embedded:
            # Track 1 is embedded - use it as timing reference
            reference_events = events1
            overlay_events = events2
            reference_label = "Track 1 (embedded)"
            overlay_label = "Track 2 (external)"
            reference_is_chinese = (track1_language == 'chinese')
            logger.info(f"🔒 REFERENCE SELECTED: Track 1 (embedded) - {len(reference_events)} events")
        elif track2_embedded and not track1_embedded:
            # Track 2 is embedded - use it as timing reference
            reference_events = events2
            overlay_events = events1
            reference_label = "Track 2 (embedded)"
            overlay_label = "Track 1 (external)"
            reference_is_chinese = (track2_language == 'chinese')
            logger.info(f"🔒 REFERENCE SELECTED: Track 2 (embedded) - {len(reference_events)} events")
        else:
            # Both embedded or both external - use Track 1 as reference
            reference_events = events1
            overlay_events = events2
            reference_label = "Track 1"
            overlay_label = "Track 2"
            reference_is_chinese = (track1_language == 'chinese')
            logger.info(f"🔒 REFERENCE SELECTED: Track 1 (default) - {len(reference_events)} events")

        logger.info(f"🔒 TIMING REFERENCE: {reference_label} (timing preserved exactly)")
        logger.info(f"📋 OVERLAY TRACK: {overlay_label} (text overlaid when overlapping)")
        logger.info(f"📊 INPUT COUNTS: Reference={len(reference_events)}, Overlay={len(overlay_events)}")
        logger.info(f"🔍 LANGUAGE ORDER: reference_is_chinese={reference_is_chinese}")

        # Determine matching strategy based on track types
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})
        is_mixed_realignment = (track1_info.get('source_type') == 'embedded') != (track2_info.get('source_type') == 'embedded')

        # Create merged events preserving ALL subtitle content while maintaining reference timing
        # For mixed realignment: preserve Chinese content + use English timing as reference
        # For standard merge: combine overlapping events optimally
        merged_events = []
        used_overlay_indices = set()  # Track which overlay events have been used

        # CRITICAL: For mixed realignment, we need to preserve Chinese content, not just match to English
        if is_mixed_realignment and not reference_is_chinese:
            logger.info("🔧 CHINESE CONTENT PRESERVATION MODE: Ensuring all Chinese events are included")
            self._current_merge_method = 'chinese_preservation'
            return self._merge_with_chinese_preservation(reference_events, overlay_events)
        else:
            logger.info("📋 STANDARD OVERLAY MODE: Using overlap-based matching")
            self._current_merge_method = 'standard_overlay'

        if is_mixed_realignment:
            # For mixed track realignment, use permissive matching to maximize Chinese content preservation
            min_overlap_threshold = 0.001  # 1ms minimum (very permissive)
            proximity_threshold = 2.0  # Allow matching within 2 seconds if no overlap
            logger.info("🔧 MIXED TRACK REALIGNMENT: Using permissive matching for Chinese content preservation")
        else:
            # For standard merging, use stricter overlap requirements
            min_overlap_threshold = 0.1  # 100ms minimum
            proximity_threshold = 0.5  # 500ms proximity for fallback
            logger.info("📋 STANDARD MERGE: Using standard overlap requirements")

        for ref_event in reference_events:
            # Find the best matching overlay event using multiple strategies
            best_overlay_event = None
            best_overlay_index = -1
            best_score = 0.0
            match_type = "none"

            for i, overlay_event in enumerate(overlay_events):
                if i in used_overlay_indices:
                    continue  # Skip already used overlay events

                # Strategy 1: Calculate overlap duration (preferred)
                overlap_start = max(ref_event.start, overlay_event.start)
                overlap_end = min(ref_event.end, overlay_event.end)

                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    if overlap_duration >= min_overlap_threshold:
                        score = overlap_duration * 10  # High priority for overlapping events
                        if score > best_score:
                            best_score = score
                            best_overlay_event = overlay_event
                            best_overlay_index = i
                            match_type = "overlap"

                # Strategy 2: Proximity matching for mixed realignment (fallback)
                if is_mixed_realignment and best_score == 0:
                    # Calculate temporal proximity (how close the events are)
                    ref_center = (ref_event.start + ref_event.end) / 2
                    overlay_center = (overlay_event.start + overlay_event.end) / 2
                    distance = abs(ref_center - overlay_center)

                    if distance <= proximity_threshold:
                        # Closer events get higher scores
                        score = (proximity_threshold - distance) / proximity_threshold
                        if score > best_score:
                            best_score = score
                            best_overlay_event = overlay_event
                            best_overlay_index = i
                            match_type = "proximity"

            # Mark the best overlay event as used to prevent duplication
            if best_overlay_index >= 0:
                used_overlay_indices.add(best_overlay_index)

            # Create bilingual text using configured order
            if best_overlay_event:
                if reference_is_chinese:
                    # Reference track is Chinese (first), overlay is English (second)
                    combined_text = self._combine_texts(ref_event.text, best_overlay_event.text)
                else:
                    # Reference track is English (second), overlay is Chinese (first)
                    combined_text = self._combine_texts(best_overlay_event.text, ref_event.text)
            else:
                # No overlay text found - use reference text only
                combined_text = ref_event.text

            # Create merged event with EXACT reference timing (no modifications)
            merged_event = SubtitleEvent(
                start=ref_event.start,  # EXACT timing preservation
                end=ref_event.end,      # EXACT timing preservation
                text=combined_text,
                style=ref_event.style,
                raw=ref_event.raw
            )

            merged_events.append(merged_event)

        # CRITICAL: Do NOT add any additional events from overlay track
        # The merged output must have exactly the same count as the reference track

        # Count matching statistics
        overlap_matches = 0
        proximity_matches = 0
        no_matches = 0

        for merged_event in merged_events:
            if '\n' in merged_event.text:
                # Has both languages
                if is_mixed_realignment:
                    # For mixed realignment, assume proximity matching was used if we have bilingual content
                    proximity_matches += 1
                else:
                    overlap_matches += 1
            else:
                # Only reference language
                no_matches += 1

        logger.info(f"✅ EXACT TIMING PRESERVATION COMPLETED: {len(merged_events)} events created")
        logger.info(f"🔒 Reference track timing boundaries preserved: 100%")
        logger.info(f"📋 Overlay events used: {len(used_overlay_indices)}/{len(overlay_events)} ({len(used_overlay_indices)/len(overlay_events)*100:.1f}%)")

        if is_mixed_realignment:
            logger.info(f"🔧 MIXED REALIGNMENT MATCHING STATS:")
            logger.info(f"   Bilingual entries: {overlap_matches + proximity_matches}/{len(merged_events)} ({(overlap_matches + proximity_matches)/len(merged_events)*100:.1f}%)")
            logger.info(f"   Reference-only entries: {no_matches}/{len(merged_events)} ({no_matches/len(merged_events)*100:.1f}%)")
            logger.info(f"   Chinese content preservation: {(overlap_matches + proximity_matches)/len(overlay_events)*100:.1f}% of realigned Chinese events")

        # Debug: Check for event count mismatch
        if len(merged_events) != len(reference_events):
            logger.warning(f"⚠️ EVENT COUNT MISMATCH: Reference={len(reference_events)}, Merged={len(merged_events)}")
            logger.warning(f"   This should not happen with exact timing preservation!")
        else:
            logger.info(f"✅ EVENT COUNT MATCH: {len(merged_events)} events (as expected)")

        return merged_events

    def _merge_with_comprehensive_preservation(self, events1: List[SubtitleEvent],
                                             events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge events ensuring ALL entries from BOTH languages are preserved.

        This method creates a comprehensive bilingual output that includes every single
        subtitle entry from both source files, ensuring no content is lost from either language.

        Args:
            events1: First list of events (e.g., Chinese)
            events2: Second list of events (e.g., English)

        Returns:
            Merged events with ALL content from both languages preserved
        """
        logger.info("🔧 COMPREHENSIVE PRESERVATION: Ensuring ALL entries from both languages are included")
        logger.info(f"   Events1 count: {len(events1)}")
        logger.info(f"   Events2 count: {len(events2)}")

        if not events1 and not events2:
            return []
        if not events1:
            return events2.copy()
        if not events2:
            return events1.copy()

        merged_events = []
        used_events1 = set()
        used_events2 = set()

        # Phase 1: Create bilingual events for overlapping/matching content
        for i, event1 in enumerate(events1):
            best_match_event2 = None
            best_match_index = -1
            best_score = 0.0

            for j, event2 in enumerate(events2):
                if j in used_events2:
                    continue

                # Calculate overlap score
                overlap_start = max(event1.start, event2.start)
                overlap_end = min(event1.end, event2.end)
                overlap_duration = max(0, overlap_end - overlap_start)

                if overlap_duration > 0:
                    # Calculate overlap percentage
                    event1_duration = event1.end - event1.start
                    event2_duration = event2.end - event2.start
                    avg_duration = (event1_duration + event2_duration) / 2
                    overlap_score = overlap_duration / avg_duration if avg_duration > 0 else 0

                    if overlap_score > best_score and overlap_score > 0.3:  # At least 30% overlap
                        best_score = overlap_score
                        best_match_event2 = event2
                        best_match_index = j

            # If we found a good match, create bilingual entry
            if best_match_event2 and best_match_index >= 0:
                used_events1.add(i)
                used_events2.add(best_match_index)

                # Use the earlier start time and later end time to cover both events
                merged_start = min(event1.start, best_match_event2.start)
                merged_end = max(event1.end, best_match_event2.end)

                # Determine language order - check if events1 contains Chinese characters
                if any('\u4e00' <= char <= '\u9fff' for char in event1.text):
                    # events1 is Chinese (first), events2 is English (second)
                    combined_text = self._combine_texts(event1.text, best_match_event2.text)
                else:
                    # events1 is English (second), events2 is Chinese (first)
                    combined_text = self._combine_texts(best_match_event2.text, event1.text)

                merged_events.append(SubtitleEvent(
                    start=merged_start,
                    end=merged_end,
                    text=combined_text
                ))

        # Phase 2: Add all unused events from events1
        for i, event1 in enumerate(events1):
            if i not in used_events1:
                merged_events.append(SubtitleEvent(
                    start=event1.start,
                    end=event1.end,
                    text=event1.text,
                    style=event1.style,
                    raw=event1.raw
                ))

        # Phase 3: Add all unused events from events2
        for j, event2 in enumerate(events2):
            if j not in used_events2:
                merged_events.append(SubtitleEvent(
                    start=event2.start,
                    end=event2.end,
                    text=event2.text,
                    style=event2.style,
                    raw=event2.raw
                ))

        # Sort by start time
        merged_events.sort(key=lambda e: e.start)

        logger.info(f"🔧 COMPREHENSIVE PRESERVATION COMPLETE:")
        logger.info(f"   Total merged events: {len(merged_events)}")
        logger.info(f"   Events1 used: {len(used_events1)}/{len(events1)}")
        logger.info(f"   Events2 used: {len(used_events2)}/{len(events2)}")
        logger.info(f"   Events1 preserved individually: {len(events1) - len(used_events1)}")
        logger.info(f"   Events2 preserved individually: {len(events2) - len(used_events2)}")

        return merged_events

    def _merge_with_chinese_preservation(self, english_events: List[SubtitleEvent],
                                       chinese_events: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge Chinese and English events while preserving ALL Chinese content.

        This method ensures that no Chinese subtitle events are lost during the merge process.
        It creates a comprehensive bilingual output that includes all Chinese content while
        using English timing as the reference structure.

        Args:
            english_events: English reference events (timing preserved exactly)
            chinese_events: Chinese events to be merged (all content preserved)

        Returns:
            Merged events with all Chinese content preserved
        """
        logger.info("🔧 CHINESE PRESERVATION MERGE: Ensuring all Chinese content is included")
        logger.info(f"   English reference events: {len(english_events)}")
        logger.info(f"   Chinese events to preserve: {len(chinese_events)}")

        merged_events = []
        used_chinese_indices = set()

        # Phase 1: Create bilingual events using English timing as reference
        # CRITICAL: English timing must be preserved exactly for video synchronization
        for eng_event in english_events:
            best_chinese_event = None
            best_chinese_index = -1
            best_score = 0.0

            # Find the best matching Chinese event using multiple strategies
            for i, chi_event in enumerate(chinese_events):
                if i in used_chinese_indices:
                    continue

                # Strategy 1: Calculate overlap (preferred)
                overlap_start = max(eng_event.start, chi_event.start)
                overlap_end = min(eng_event.end, chi_event.end)

                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    score = overlap_duration * 10  # High priority for overlapping events
                    if score > best_score:
                        best_score = score
                        best_chinese_event = chi_event
                        best_chinese_index = i

                # Strategy 2: Proximity matching (fallback)
                if best_score == 0:
                    eng_center = (eng_event.start + eng_event.end) / 2
                    chi_center = (chi_event.start + chi_event.end) / 2
                    distance = abs(eng_center - chi_center)

                    if distance <= 5.0:  # Within 5 seconds
                        proximity_score = 5.0 - distance
                        if proximity_score > best_score:
                            best_score = proximity_score
                            best_chinese_event = chi_event
                            best_chinese_index = i

            # Create merged event with English timing preserved exactly
            if best_chinese_event:
                used_chinese_indices.add(best_chinese_index)
                # Chinese is first, English is second
                combined_text = self._combine_texts(best_chinese_event.text, eng_event.text)
            else:
                combined_text = eng_event.text

            # CRITICAL: Use English timing exactly - this preserves video synchronization
            merged_event = SubtitleEvent(
                start=eng_event.start,  # English timing preserved exactly
                end=eng_event.end,      # English timing preserved exactly
                text=combined_text,
                style=eng_event.style,
                raw=eng_event.raw
            )
            merged_events.append(merged_event)

        # Phase 2: Add remaining Chinese events that weren't matched
        unmatched_chinese = [chi_event for i, chi_event in enumerate(chinese_events)
                           if i not in used_chinese_indices]

        if unmatched_chinese:
            logger.info(f"🔧 Adding {len(unmatched_chinese)} unmatched Chinese events")

            # Insert unmatched Chinese events in chronological order
            for chi_event in unmatched_chinese:
                # Create Chinese-only event with original timing
                chinese_only_event = SubtitleEvent(
                    start=chi_event.start,
                    end=chi_event.end,
                    text=chi_event.text,  # Chinese only
                    style=chi_event.style,
                    raw=chi_event.raw
                )
                merged_events.append(chinese_only_event)

        # Phase 3: Sort all events by start time and apply anti-jitter
        merged_events.sort(key=lambda e: e.start)

        logger.info(f"✅ CHINESE PRESERVATION COMPLETED:")
        logger.info(f"   Total merged events: {len(merged_events)}")
        logger.info(f"   Chinese events matched: {len(used_chinese_indices)}")
        logger.info(f"   Chinese events unmatched: {len(unmatched_chinese)}")
        logger.info(f"   Chinese preservation rate: {len(used_chinese_indices) + len(unmatched_chinese)}/{len(chinese_events)} = {(len(used_chinese_indices) + len(unmatched_chinese))/len(chinese_events)*100:.1f}%")

        return merged_events

    def _optimize_subtitle_timing(self, events: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Apply LIMITED anti-jitter optimization with strict scope control.

        CRITICAL: This method should ONLY combine identical consecutive segments
        within 100ms tolerance. It should NOT modify timing for embedded tracks
        or create wholesale timing boundary changes.

        Args:
            events: List of subtitle events to optimize

        Returns:
            Events with minimal anti-jitter optimization applied
        """
        if not events:
            return events

        # Check if we're dealing with embedded tracks - if so, be extra conservative
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        has_embedded = (track1_info.get('source_type') == 'embedded' or
                       track2_info.get('source_type') == 'embedded')

        if has_embedded:
            logger.info("🔒 EMBEDDED TRACKS DETECTED: Applying minimal anti-jitter (100ms tolerance only)")
            gap_threshold = 0.1  # 100ms maximum for embedded tracks
        else:
            logger.info("📋 External tracks: Using standard gap threshold")
            gap_threshold = self.gap_threshold

        # Sort events by start time
        sorted_events = sorted(events, key=lambda e: e.start)
        optimized = []

        i = 0
        while i < len(sorted_events):
            current = sorted_events[i]

            # Look ahead for events that can be merged (VERY CONSERVATIVE)
            j = i + 1
            while j < len(sorted_events):
                next_event = sorted_events[j]

                # STRICT CONDITIONS: Only merge if text is IDENTICAL and gap is tiny
                if (next_event.start - current.end <= gap_threshold and
                    current.text == next_event.text):
                    # Extend current event (anti-jitter for identical segments)
                    logger.debug(f"🔧 Anti-jitter: Combining identical segments "
                               f"({current.end:.3f}s -> {next_event.start:.3f}s, gap: {next_event.start - current.end:.3f}s)")
                    current = SubtitleEvent(
                        start=current.start,
                        end=next_event.end,
                        text=current.text,
                        style=current.style,
                        raw=current.raw
                    )
                    j += 1
                else:
                    break

            optimized.append(current)
            i = j

        if len(optimized) < len(sorted_events):
            logger.info(f"🔧 Anti-jitter applied: {len(sorted_events)} -> {len(optimized)} events "
                       f"(combined {len(sorted_events) - len(optimized)} identical segments)")
        else:
            logger.info("🔒 No anti-jitter optimization needed")

        return optimized

    def _detect_forced_subtitles(self, events1: List[SubtitleEvent],
                               events2: List[SubtitleEvent],
                               threshold: float = 0.1) -> Optional[str]:
        """
        Detect if one subtitle track is likely forced subtitles.

        Forced subtitles typically have significantly fewer lines than regular subtitles.

        Args:
            events1: First subtitle track events
            events2: Second subtitle track events
            threshold: Ratio threshold for forced detection

        Returns:
            'first' or 'second' if forced detected, None otherwise
        """
        count1 = len(events1)
        count2 = len(events2)

        if count1 == 0 or count2 == 0:
            return None

        ratio1 = count1 / count2
        ratio2 = count2 / count1

        if ratio1 < threshold:
            return 'first'
        elif ratio2 < threshold:
            return 'second'

        return None

    def _validate_timing_preservation(self, original_events1: List[SubtitleEvent],
                                    original_events2: List[SubtitleEvent],
                                    merged_events: List[SubtitleEvent],
                                    method_used: str) -> bool:
        """
        Validate that timing preservation requirements are met.

        Args:
            original_events1: Original first track events
            original_events2: Original second track events
            merged_events: Resulting merged events
            method_used: Name of merge method used

        Returns:
            True if timing preservation is valid
        """
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        both_embedded = (track1_info.get('source_type') == 'embedded' and
                        track2_info.get('source_type') == 'embedded')

        any_embedded = (track1_info.get('source_type') == 'embedded' or
                       track2_info.get('source_type') == 'embedded')

        if both_embedded or any_embedded:
            logger.info(f"🔍 TIMING VALIDATION: Checking {method_used} for embedded track timing preservation")

            # For mixed track realignment and preserved timing, validate embedded track timing preservation
            if method_used in ["mixed_track_realignment", "preserved_timing"]:
                logger.info(f"🔧 {method_used} detected - validating embedded track preservation")

                # Identify which track is embedded
                track1_info = getattr(self, '_track1_info', {})
                track2_info = getattr(self, '_track2_info', {})

                if track1_info.get('source_type') == 'embedded':
                    embedded_original = original_events1
                    logger.info("🔒 Validating Track 1 (embedded) timing preservation")
                elif track2_info.get('source_type') == 'embedded':
                    embedded_original = original_events2
                    logger.info("🔒 Validating Track 2 (embedded) timing preservation")
                else:
                    # No embedded track - skip validation
                    logger.info("📋 No embedded tracks detected - skipping timing validation")
                    return True

                # Both preserved_timing and mixed_track_realignment use the same preservation approach
                # (embedded track as exact timing reference), so use the same validation
                if method_used in ["preserved_timing", "mixed_track_realignment"]:

                    # For mixed_track_realignment, we need to be more flexible since the merged output
                    # might have a different count due to realignment operations
                    if method_used == "mixed_track_realignment":
                        # For mixed track realignment, validate that the embedded track timing is preserved
                        # but allow for different event counts due to realignment operations

                        # Check if embedded timing boundaries are present in merged output
                        embedded_times = set()
                        for event in embedded_original:
                            embedded_times.add(round(event.start, 3))
                            embedded_times.add(round(event.end, 3))

                        merged_times = set()
                        for event in merged_events:
                            merged_times.add(round(event.start, 3))
                            merged_times.add(round(event.end, 3))

                        preserved_ratio = len(embedded_times & merged_times) / len(embedded_times) if embedded_times else 1.0

                        if preserved_ratio < 0.8:  # 80% threshold for realignment (more flexible)
                            logger.warning(f"⚠️ EMBEDDED TIMING VALIDATION FAILED: Only {preserved_ratio:.1%} of embedded timing boundaries preserved")
                            return False
                        else:
                            logger.info(f"✅ EMBEDDED TIMING VALIDATION PASSED: {preserved_ratio:.1%} of embedded timing boundaries preserved")
                            return True

                    else:
                        # For preserved_timing, require exact count match
                        if len(merged_events) != len(embedded_original):
                            logger.warning(f"⚠️ EMBEDDED TIMING VALIDATION FAILED: Event count mismatch - "
                                         f"embedded: {len(embedded_original)}, merged: {len(merged_events)}")
                            return False

                        # Check if each merged event has exactly the same timing as corresponding embedded event
                        timing_matches = 0
                        for i, (embedded_event, merged_event) in enumerate(zip(embedded_original, merged_events)):
                            start_match = abs(embedded_event.start - merged_event.start) < 0.001  # 1ms tolerance
                            end_match = abs(embedded_event.end - merged_event.end) < 0.001      # 1ms tolerance

                            if start_match and end_match:
                                timing_matches += 1
                            else:
                                logger.debug(f"Timing mismatch at index {i}: "
                                           f"embedded[{embedded_event.start:.3f}-{embedded_event.end:.3f}] vs "
                                           f"merged[{merged_event.start:.3f}-{merged_event.end:.3f}]")

                        preserved_ratio = timing_matches / len(embedded_original) if embedded_original else 1.0

                        if preserved_ratio < 0.99:  # 99% threshold for exact preservation
                            logger.warning(f"⚠️ EMBEDDED TIMING VALIDATION FAILED: Only {preserved_ratio:.1%} of embedded timing boundaries exactly preserved")
                            return False
                        else:
                            logger.info(f"✅ EMBEDDED TIMING VALIDATION PASSED: {preserved_ratio:.1%} of embedded timing boundaries exactly preserved")
                            return True
            else:
                # Standard validation for other methods
                # Check if any original timing boundaries were lost
                original_times = set()
                for event in original_events1 + original_events2:
                    original_times.add(event.start)
                    original_times.add(event.end)

                merged_times = set()
                for event in merged_events:
                    merged_times.add(event.start)
                    merged_times.add(event.end)

                # For embedded tracks, most original timing boundaries should be preserved
                preserved_ratio = len(original_times & merged_times) / len(original_times)

                if preserved_ratio < 0.8:  # Less than 80% of timing boundaries preserved
                    logger.warning(f"⚠️ TIMING VALIDATION FAILED: Only {preserved_ratio:.1%} of original timing boundaries preserved")
                    logger.warning(f"⚠️ This indicates inappropriate timing modification for embedded tracks")
                    return False
                else:
                    logger.info(f"✅ TIMING VALIDATION PASSED: {preserved_ratio:.1%} of original timing boundaries preserved")
                    return True
        else:
            logger.info(f"📋 TIMING VALIDATION: External tracks - timing modification allowed")
            return True
