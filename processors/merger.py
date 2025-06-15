"""
Bilingual subtitle merging processor.

This module provides functionality for merging Chinese and English subtitles
into a single bilingual track with intelligent timing optimization.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Dict
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
                 enable_mixed_realignment: bool = False):
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

        self.video_handler = VideoContainerHandler()
        self.pgsrip_wrapper = get_pgsrip_wrapper() if not no_pgs else None

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
                   f"threshold={alignment_threshold}")

    
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

            # Initialize track information for reference selection
            self._track1_info = {'source_type': 'unknown', 'language': 'unknown'}
            self._track2_info = {'source_type': 'unknown', 'language': 'unknown'}

            if chinese_path:
                chinese_sub = SubtitleFormatFactory.parse_file(chinese_path)
                chinese_events = chinese_sub.events
                logger.info(f"Loaded {len(chinese_events)} Chinese events")

                # Determine source type and language for track 1
                self._track1_info = {
                    'source_type': 'external',  # File-based subtitles are external
                    'language': 'chinese',
                    'path': str(chinese_path)
                }

            if english_path:
                english_sub = SubtitleFormatFactory.parse_file(english_path)
                english_events = english_sub.events
                logger.info(f"Loaded {len(english_events)} English events")

                # Determine source type and language for track 2
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
            if not chinese_sub:
                chinese_sub, chinese_source_type = self._find_or_extract_subtitle_with_info(
                    video_path, is_chinese=True, prefer_external=prefer_external,
                    prefer_embedded=prefer_embedded, track_id=chinese_track,
                    remap_lang=remap_chinese, temp_files=temp_files
                )
                self._track1_info = {
                    'source_type': chinese_source_type,
                    'language': 'chinese',
                    'path': str(chinese_sub) if chinese_sub else None
                }
            else:
                # User-provided Chinese subtitle (external)
                self._track1_info = {
                    'source_type': 'external',
                    'language': 'chinese',
                    'path': str(chinese_sub)
                }

            # Find/Extract English subtitles
            if not english_sub:
                english_sub, english_source_type = self._find_or_extract_subtitle_with_info(
                    video_path, is_chinese=False, prefer_external=prefer_external,
                    prefer_embedded=prefer_embedded, track_id=english_track,
                    remap_lang=remap_english, temp_files=temp_files
                )
                self._track2_info = {
                    'source_type': english_source_type,
                    'language': 'english',
                    'path': str(english_sub) if english_sub else None
                }
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
            if not output_path:
                lang1, lang2 = self._detect_subtitle_languages(chinese_sub, english_sub)
                output_path = self._generate_output_filename(video_path, lang1, lang2, output_format)
            
            # Merge subtitles
            success = self.merge_subtitle_files(chinese_sub, english_sub, output_path, output_format)
            
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

            if major_misalignment and self.enable_mixed_realignment:
                logger.warning("🚨 MAJOR TIMING MISALIGNMENT DETECTED (>5s difference)")
                logger.warning("🚨 Mixed embedded + external tracks with significant timing offset")
                logger.info("🔧 Enhanced mixed track realignment is ENABLED")

                # Apply enhanced realignment for mixed tracks
                merged_events = self._handle_mixed_track_realignment(events1, events2)
                method_used = "mixed_track_realignment"
            elif major_misalignment and not self.enable_mixed_realignment:
                logger.warning("🚨 MAJOR TIMING MISALIGNMENT DETECTED (>5s difference)")
                logger.warning("🚨 Mixed embedded + external tracks with significant timing offset")
                logger.warning("⚠️ Enhanced mixed track realignment is DISABLED")
                logger.warning("⚠️ Use --enable-mixed-realignment flag to enable enhanced realignment")
                logger.info("🔒 Falling back to timing preservation (may result in poor alignment)")
                merged_events = self._merge_with_preserved_timing(events1, events2)
                method_used = "preserved_timing"
            else:
                logger.info("🔒 MIXED EMBEDDED+EXTERNAL (synchronized): Using timing preservation")
                merged_events = self._merge_with_preserved_timing(events1, events2)
                method_used = "preserved_timing"
        elif self.auto_align or self.manual_align or self.use_translation:
            logger.info("⚙️ Enhanced alignment requested - checking synchronization status")
            # Only use enhanced alignment for massively misaligned subtitles (>1s differences)
            if not self._tracks_are_well_synchronized(events1, events2):
                logger.warning("⚠️ MASSIVE MISALIGNMENT DETECTED: Using enhanced alignment (timing will be modified)")
                logger.warning("⚠️ This should only be used for external files with major timing issues")
                merged_events = self._merge_with_enhanced_alignment(events1, events2)
                method_used = "enhanced_alignment"
            else:
                logger.info("✅ Tracks are synchronized - using simple overlap with timing preservation")
                merged_events = self._merge_with_simple_overlap(events1, events2)
                method_used = "simple_overlap"
        else:
            logger.info("📋 Using simple overlap method (default - preserves timing)")
            merged_events = self._merge_with_simple_overlap(events1, events2)
            method_used = "simple_overlap"

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

    def _tracks_are_well_synchronized(self, events1: List[SubtitleEvent],
                                    events2: List[SubtitleEvent],
                                    threshold: float = 0.5) -> bool:
        """
        Check if two embedded tracks are already well-synchronized.

        This determines whether tracks need realignment or just timing preservation.
        Realignment features should ONLY be used for massively misaligned subtitles
        (different timing by seconds), not for minor timing differences.

        Args:
            events1: First list of events
            events2: Second list of events
            threshold: Maximum timing difference in seconds to consider "well-synchronized"

        Returns:
            True if tracks are well-synchronized (minor differences <500ms),
            False if they need realignment (major differences >500ms)
        """
        if not events1 or not events2:
            return False

        # Sample first 10 events to check synchronization
        sample_size = min(10, len(events1), len(events2))
        timing_differences = []

        for i in range(sample_size):
            time_diff = abs(events1[i].start - events2[i].start)
            timing_differences.append(time_diff)

        # Calculate average timing difference
        avg_diff = sum(timing_differences) / len(timing_differences)
        max_diff = max(timing_differences)

        is_synchronized = avg_diff < threshold and max_diff < threshold * 2

        logger.info(f"Synchronization check: avg_diff={avg_diff:.3f}s, max_diff={max_diff:.3f}s, "
                   f"threshold={threshold}s, synchronized={is_synchronized}")

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

        # Step 1: Identify embedded vs external tracks
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        if track1_info.get('source_type') == 'embedded':
            embedded_events = events1
            external_events = events2
            embedded_track_num = 1
            external_track_num = 2
            embedded_lang = track1_info.get('language', 'unknown')
            external_lang = track2_info.get('language', 'unknown')
        else:
            embedded_events = events2
            external_events = events1
            embedded_track_num = 2
            external_track_num = 1
            embedded_lang = track2_info.get('language', 'unknown')
            external_lang = track1_info.get('language', 'unknown')

        logger.info(f"🎯 REFERENCE TRACK: Track {embedded_track_num} (embedded {embedded_lang}) - timing will be preserved")
        logger.info(f"🔄 TARGET TRACK: Track {external_track_num} (external {external_lang}) - will be realigned")

        # Step 2: Find semantic alignment anchor point
        anchor_result = self._find_semantic_alignment_anchor(embedded_events, external_events)

        if not anchor_result:
            logger.error("❌ Failed to find semantic alignment anchor point")
            logger.warning("⚠️ Falling back to timing preservation without realignment")
            return self._merge_with_preserved_timing(events1, events2)

        embedded_anchor_idx, external_anchor_idx, confidence, time_offset = anchor_result

        # Step 3: User confirmation for major timing shifts
        if not self._confirm_major_timing_shift(embedded_events, external_events,
                                              embedded_anchor_idx, external_anchor_idx,
                                              time_offset, embedded_lang, external_lang):
            logger.info("🚫 User cancelled realignment - using timing preservation")
            return self._merge_with_preserved_timing(events1, events2)

        # Step 4: Apply realignment to external track
        realigned_external_events = self._apply_mixed_track_realignment(
            external_events, external_anchor_idx, time_offset)

        # Step 5: Merge using timing preservation (embedded track as reference)
        if embedded_track_num == 1:
            merged_events = self._merge_with_preserved_timing(embedded_events, realigned_external_events)
        else:
            merged_events = self._merge_with_preserved_timing(realigned_external_events, embedded_events)

        logger.info(f"✅ MIXED TRACK REALIGNMENT COMPLETED: {len(merged_events)} events created")
        logger.info(f"🔒 Embedded track timing preserved, external track realigned by {time_offset:.3f}s")

        return merged_events

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

        # Limit search to first 20 events to find early anchor point
        search_limit_embedded = min(20, len(embedded_events))
        search_limit_external = min(20, len(external_events))

        best_match = None
        best_confidence = 0.0

        # Try translation-assisted matching first if available
        if self.use_translation and self.translation_service:
            logger.info("🌐 Using translation-assisted semantic matching")

            try:
                # Use translation service to find alignment point
                source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
                    source_events=external_events[:search_limit_external],
                    reference_events=embedded_events[:search_limit_embedded],
                    target_language='en',  # Translate to English for comparison
                    translation_limit=min(10, search_limit_external),
                    confidence_threshold=0.6  # Lower threshold for anchor finding
                )

                if source_idx is not None and ref_idx is not None and confidence >= 0.6:
                    time_offset = embedded_events[ref_idx].start - external_events[source_idx].start
                    best_match = (ref_idx, source_idx, confidence, time_offset)
                    logger.info(f"🎯 Translation-assisted anchor found: embedded[{ref_idx}] ↔ external[{source_idx}] "
                               f"(confidence: {confidence:.3f}, offset: {time_offset:.3f}s)")

            except Exception as e:
                logger.warning(f"Translation-assisted anchor search failed: {e}")

        # Fallback to similarity-only matching
        if not best_match:
            logger.info("📝 Using similarity-only semantic matching")

            for i in range(search_limit_embedded):
                embedded_text = embedded_events[i].text.strip()
                if len(embedded_text) < 5:  # Skip very short texts
                    continue

                for j in range(search_limit_external):
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

                    if confidence > best_confidence and confidence >= 0.5:  # Minimum threshold
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
            logger.warning("   Minimum confidence threshold (0.5) not met")
            return None

    def _confirm_major_timing_shift(self, embedded_events: List[SubtitleEvent],
                                  external_events: List[SubtitleEvent],
                                  embedded_anchor_idx: int, external_anchor_idx: int,
                                  time_offset: float, embedded_lang: str, external_lang: str) -> bool:
        """
        Get user confirmation for major timing shifts in mixed track realignment.

        Args:
            embedded_events: Embedded track events
            external_events: External track events
            embedded_anchor_idx: Anchor index in embedded track
            external_anchor_idx: Anchor index in external track
            time_offset: Calculated time offset
            embedded_lang: Embedded track language
            external_lang: External track language

        Returns:
            True if user confirms the realignment
        """
        import sys

        try:
            sys.stdout.flush()
            sys.stderr.flush()

            print("\n" + "="*80)
            print("🚨 MAJOR TIMING REALIGNMENT REQUIRED")
            print("="*80)
            print(f"Mixed track scenario detected:")
            print(f"  📺 Embedded {embedded_lang} track: Properly synchronized with video")
            print(f"  📄 External {external_lang} track: Major timing offset detected")
            print()
            print(f"Proposed realignment:")
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
            print("⚠️  This will modify the external track timing to match the embedded track.")
            print("⚠️  The embedded track timing will remain unchanged.")
            print("⚠️  This is recommended for external files with incorrect timing.")
            print()

            # Get user confirmation
            while True:
                try:
                    response = input("Proceed with realignment? (y/n): ").strip().lower()
                    if response in ['y', 'yes']:
                        logger.info("✅ User confirmed major timing realignment")
                        return True
                    elif response in ['n', 'no']:
                        logger.info("🚫 User declined major timing realignment")
                        return False
                    else:
                        print("Please enter 'y' for yes or 'n' for no.")
                except EOFError:
                    logger.info("🚫 User input cancelled")
                    return False

        except KeyboardInterrupt:
            print("\n🚫 Realignment cancelled by user")
            logger.info("🚫 User cancelled realignment with Ctrl+C")
            return False
        except Exception as e:
            logger.error(f"Error in user confirmation: {e}")
            return False

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
        merged_events = self._create_merged_events_from_alignments(sync_events1, sync_events2, all_alignments)

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

        Returns:
            Tuple of (index1, index2, confidence) or None
        """
        if not self.translation_service:
            logger.warning("Translation service not available, falling back to scan strategy")
            return self._find_anchor_scan_forward(events1, events2)

        scan_limit = min(10, len(events1), len(events2))

        # Extract texts for translation
        texts1 = [events1[i].text for i in range(scan_limit)]
        texts2 = [events2[i].text for i in range(scan_limit)]

        logger.info(f"Strategy C (translation): Analyzing {scan_limit} entries from each track")

        try:
            # Use the translation service's alignment method
            source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
                source_events=events1[:scan_limit],
                reference_events=events2[:scan_limit],
                target_language='en',  # Assume translating to English for comparison
                translation_limit=scan_limit,
                confidence_threshold=self.alignment_threshold
            )

            if source_idx is not None and ref_idx is not None and confidence >= self.alignment_threshold:
                logger.info(f"Strategy C (translation): Found semantic anchor at positions ({source_idx}, {ref_idx}) "
                           f"with confidence {confidence:.3f}")
                return source_idx, ref_idx, confidence
            else:
                logger.info("Strategy C (translation): No suitable semantic matches found, falling back to scan")
                return self._find_anchor_scan_forward(events1, events2)

        except Exception as e:
            logger.warning(f"Translation-assisted anchor finding failed: {e}, falling back to scan")
            return self._find_anchor_scan_forward(events1, events2)

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

        # Determine reference track for timing preservation
        track1_info = getattr(self, '_track1_info', {})
        track2_info = getattr(self, '_track2_info', {})

        # Prioritize embedded tracks as timing reference
        if track1_info.get('source_type') == 'embedded':
            reference_track = 1
            logger.info("🔒 Using Track 1 (embedded) as timing reference")
        elif track2_info.get('source_type') == 'embedded':
            reference_track = 2
            logger.info("🔒 Using Track 2 (embedded) as timing reference")
        else:
            # For external tracks, use the first track as reference
            reference_track = 1
            logger.info("📋 Using Track 1 as timing reference (both external)")

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

                # Combine texts
                combined_text = f"{event1.text}\n{event2.text}"

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

            # Combine texts
            if text1 and text2:
                combined_text = f"{text1}\n{text2}"
            else:
                combined_text = text1 if text1 else text2

            segments.append(SubtitleEvent(
                start=seg_start,
                end=seg_end,
                text=combined_text
            ))

        return segments

    def _merge_with_preserved_timing(self, events1: List[SubtitleEvent],
                                   events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
        """
        Merge embedded subtitle events with TRUE timing preservation.

        This method preserves the EXACT original timing boundaries from embedded tracks
        by keeping all original events intact and only combining text when events overlap.
        NO segmentation or timing modifications are applied.

        Args:
            events1: First list of events (e.g., Chinese)
            events2: Second list of events (e.g., English)

        Returns:
            Merged list of events with EXACT original timing preserved
        """
        logger.info("Using EXACT originalscript.py timing preservation logic")

        # Convert SubtitleEvent objects to the format expected by original algorithm
        chinese_events = []
        english_events = []

        for event in events1:
            chinese_events.append({
                "start": event.start,
                "end": event.end,
                "text": event.text
            })

        for event in events2:
            english_events.append({
                "start": event.start,
                "end": event.end,
                "text": event.text
            })

        # EXACT COPY of originalscript.py merge_events_srt logic (lines 178-291)

        # First, create all possible segment boundaries
        times = sorted({ev["start"] for ev in (chinese_events + english_events)} |
                       {ev["end"]   for ev in (chinese_events + english_events)})

        # Generate initial segments
        segments = []
        for i in range(len(times)-1):
            seg_start = times[i]
            seg_end = times[i+1]
            if seg_end <= seg_start:
                continue

            cn_text = en_text = None
            # Find any CN event that covers seg_start
            for ev in chinese_events:
                if ev["start"] <= seg_start < ev["end"]:
                    cn_text = ev["text"]
                    break
            # Find any EN event that covers seg_start
            for ev in english_events:
                if ev["start"] <= seg_start < ev["end"]:
                    en_text = ev["text"]
                    break

            if not cn_text and not en_text:
                continue

            if cn_text and en_text:
                merged_text = f"{cn_text}\n{en_text}"
            else:
                merged_text = cn_text if cn_text else en_text

            segments.append({
                "start": seg_start,
                "end": seg_end,
                "text": merged_text,
                "cn_text": cn_text,
                "en_text": en_text
            })

        # First pass: combine segments with identical text (EXACT original logic)
        combined = []
        for seg in segments:
            if (combined and
                seg["text"] == combined[-1]["text"] and
                abs(seg["start"] - combined[-1]["end"]) < 0.1):  # 100ms tolerance (EXACT original)
                combined[-1]["end"] = seg["end"]
            else:
                combined.append(seg.copy())

        # Convert back to SubtitleEvent format
        merged_events = []
        for seg in combined:
            merged_events.append(SubtitleEvent(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"]
            ))

        logger.info(f"EXACT originalscript.py timing preservation completed: {len(merged_events)} events")
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

            # For mixed track realignment, only validate embedded track timing preservation
            if method_used == "mixed_track_realignment":
                logger.info("🔧 Mixed track realignment detected - validating embedded track preservation only")

                # Identify which track is embedded
                track1_info = getattr(self, '_track1_info', {})
                track2_info = getattr(self, '_track2_info', {})

                if track1_info.get('source_type') == 'embedded':
                    embedded_original = original_events1
                    logger.info("🔒 Validating Track 1 (embedded) timing preservation")
                else:
                    embedded_original = original_events2
                    logger.info("🔒 Validating Track 2 (embedded) timing preservation")

                # Check if embedded track timing boundaries are preserved
                embedded_times = set()
                for event in embedded_original:
                    embedded_times.add(event.start)
                    embedded_times.add(event.end)

                merged_times = set()
                for event in merged_events:
                    merged_times.add(event.start)
                    merged_times.add(event.end)

                # For mixed track realignment, embedded timing should be well preserved
                preserved_ratio = len(embedded_times & merged_times) / len(embedded_times)

                if preserved_ratio < 0.7:  # Lower threshold for mixed scenarios
                    logger.warning(f"⚠️ EMBEDDED TIMING VALIDATION FAILED: Only {preserved_ratio:.1%} of embedded timing boundaries preserved")
                    return False
                else:
                    logger.info(f"✅ EMBEDDED TIMING VALIDATION PASSED: {preserved_ratio:.1%} of embedded timing boundaries preserved")
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
