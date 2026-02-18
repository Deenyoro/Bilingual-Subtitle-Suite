"""
Subtitle realignment processor.

This module provides functionality for realigning subtitle files with multiple modes:
- Automatic mode: Aligns based on earliest start times
- Interactive mode: Allows manual selection of alignment points
"""

from pathlib import Path
from typing import List, Tuple, Optional
from core.subtitle_formats import SubtitleEvent, SubtitleFile, SubtitleFormatFactory
from core.timing_utils import TimeConverter
from core.translation_service import get_translation_service, TranslationResult
from core.similarity_alignment import SimilarityAligner, AlignmentMatch, MultiAnchorAligner
from core.language_detection import LanguageDetector
from utils.logging_config import get_logger
from utils.file_operations import FileHandler

logger = get_logger(__name__)


class SubtitleRealigner:
    """Handles subtitle realignment operations."""
    
    def __init__(self, use_translation: bool = False, auto_align: bool = False,
                 translation_api_key: Optional[str] = None):
        """
        Initialize the subtitle realigner.

        Args:
            use_translation: Enable Google Cloud Translation for cross-language alignment
            auto_align: Enable automatic alignment using similarity analysis
            translation_api_key: Google Cloud Translation API key
        """
        self.use_translation = use_translation
        self.auto_align = auto_align

        # Initialize translation service if requested
        self.translation_service = None
        if use_translation:
            self.translation_service = get_translation_service(translation_api_key)
            if self.translation_service:
                logger.info("Translation service initialized for cross-language alignment")
            else:
                logger.warning("Translation service initialization failed")
                self.use_translation = False

        # Initialize similarity aligner if requested
        self.similarity_aligner = None
        if auto_align:
            self.similarity_aligner = SimilarityAligner(min_confidence=0.6)
            logger.info("Automatic similarity alignment enabled")
    
    def align_subtitles(self, source_path: Path, reference_path: Path,
                       output_path: Optional[Path] = None,
                       source_align_idx: Optional[int] = None, ref_align_idx: Optional[int] = None,
                       create_backup: bool = True, use_auto_align: Optional[bool] = None,
                       use_translation: Optional[bool] = None) -> bool:
        """
        Align source subtitle to reference at specified event indices.

        Args:
            source_path: Path to source subtitle file to be aligned
            reference_path: Path to reference subtitle file
            output_path: Output path (if None, overwrites source)
            source_align_idx: Index of source event to align (None for auto-detection)
            ref_align_idx: Index of reference event to align to (None for auto-detection)
            create_backup: Whether to create backup before overwriting
            use_auto_align: Override instance auto_align setting
            use_translation: Override instance use_translation setting

        Returns:
            True if alignment was successful

        Example:
            >>> realigner = SubtitleRealigner(auto_align=True)
            >>> success = realigner.align_subtitles(
            ...     Path("source.srt"), Path("reference.srt")
            ... )
        """
        try:
            # Determine which features to use
            auto_align_enabled = use_auto_align if use_auto_align is not None else self.auto_align
            translation_enabled = use_translation if use_translation is not None else self.use_translation

            # If translation is requested, use translation-assisted alignment
            if translation_enabled and source_align_idx is None and ref_align_idx is None:
                logger.info("Using translation-assisted alignment")
                return self.align_with_translation(source_path, reference_path, output_path)

            # Load subtitle files
            logger.info(f"Loading source: {source_path.name}")
            source = SubtitleFormatFactory.parse_file(source_path)

            logger.info(f"Loading reference: {reference_path.name}")
            reference = SubtitleFormatFactory.parse_file(reference_path)

            if not source.events or not reference.events:
                logger.error("One or both files have no events")
                return False

            # Auto-detect alignment indices if not provided
            if source_align_idx is None or ref_align_idx is None:
                if auto_align_enabled:
                    logger.info("Auto-detecting alignment indices using similarity analysis")
                    matches = self.find_automatic_alignments(source_path, reference_path)

                    if matches:
                        best_match = matches[0]
                        source_align_idx = best_match.source_index
                        ref_align_idx = best_match.reference_index
                        logger.info(f"Auto-detected alignment: source[{source_align_idx}] -> reference[{ref_align_idx}] (confidence: {best_match.confidence:.3f})")
                    else:
                        logger.warning("Auto-alignment failed, using default indices (0, 0)")
                        source_align_idx = 0
                        ref_align_idx = 0
                else:
                    # Use default values if not provided
                    source_align_idx = source_align_idx or 0
                    ref_align_idx = ref_align_idx or 0

            # Validate alignment indices
            if source_align_idx >= len(source.events):
                logger.error(f"Source align index {source_align_idx} out of range")
                return False
            if ref_align_idx >= len(reference.events):
                logger.error(f"Reference align index {ref_align_idx} out of range")
                return False
            
            # Perform alignment
            aligned_events = self._align_events(
                source.events, reference.events, source_align_idx, ref_align_idx
            )
            
            # Create aligned subtitle file
            aligned_subtitle = SubtitleFile(
                path=output_path or source_path,
                format=source.format,
                events=aligned_events,
                encoding=source.encoding,
                styles=source.styles,
                script_info=source.script_info
            )
            
            # Write output
            output_file = output_path or source_path
            SubtitleFormatFactory.write_file(aligned_subtitle, output_file)
            
            logger.info(f"Successfully aligned and saved: {output_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to align subtitles: {e}")
            return False
    
    def find_matching_pairs(self, directory: Path, source_ext: str, 
                           reference_ext: str) -> List[Tuple[Path, Path]]:
        """
        Find matching subtitle pairs in a directory.
        
        Args:
            directory: Directory to search
            source_ext: Source file extension (e.g., '.zh.srt')
            reference_ext: Reference file extension (e.g., '.en.srt')
            
        Returns:
            List of (source_path, reference_path) tuples
            
        Example:
            >>> realigner = SubtitleRealigner()
            >>> pairs = realigner.find_matching_pairs(
            ...     Path("/media"), ".zh.srt", ".en.srt"
            ... )
        """
        return FileHandler.find_matching_pairs(directory, source_ext, reference_ext)
    
    def batch_align(self, pairs: List[Tuple[Path, Path]], 
                   output_suffix: str = "", create_backup: bool = True,
                   auto_align: bool = True) -> Tuple[int, int]:
        """
        Align multiple subtitle pairs in batch.
        
        Args:
            pairs: List of (source_path, reference_path) tuples
            output_suffix: Suffix to add to output files
            create_backup: Whether to create backups
            auto_align: Use automatic alignment (earliest events)
            
        Returns:
            Tuple of (success_count, failure_count)
            
        Example:
            >>> realigner = SubtitleRealigner()
            >>> success, failed = realigner.batch_align(pairs, ".aligned")
        """
        logger.info(f"Processing {len(pairs)} subtitle pairs")
        
        success_count = 0
        failure_count = 0
        
        for i, (source_path, reference_path) in enumerate(pairs, 1):
            logger.info(f"Processing pair {i}/{len(pairs)}")
            logger.info(f"  Source: {source_path.name}")
            logger.info(f"  Reference: {reference_path.name}")
            
            try:
                # Determine output path
                if output_suffix:
                    output_path = source_path.with_stem(source_path.stem + output_suffix)
                else:
                    output_path = source_path
                
                # Use automatic alignment (earliest events)
                if auto_align:
                    source_idx = 0
                    ref_idx = 0
                else:
                    # For batch processing, we'll use automatic alignment
                    # Interactive alignment would need to be handled separately
                    source_idx = 0
                    ref_idx = 0
                
                success = self.align_subtitles(
                    source_path, reference_path, output_path,
                    source_idx, ref_idx, create_backup
                )
                
                if success:
                    success_count += 1
                    logger.info(f"✓ Successfully aligned: {output_path.name}")
                else:
                    failure_count += 1
                    logger.error(f"✗ Failed to align: {source_path.name}")
                    
            except Exception as e:
                failure_count += 1
                logger.error(f"✗ Error processing {source_path.name}: {e}")
        
        return success_count, failure_count
    
    def _align_events(self, source_events: List[SubtitleEvent], 
                     reference_events: List[SubtitleEvent],
                     source_align_idx: int, ref_align_idx: int) -> List[SubtitleEvent]:
        """
        Align source events to reference at specified indices.
        
        Args:
            source_events: Source subtitle events
            reference_events: Reference subtitle events
            source_align_idx: Index of source event to align
            ref_align_idx: Index of reference event to align to
            
        Returns:
            Aligned list of subtitle events
        """
        # Get alignment points
        source_event = source_events[source_align_idx]
        ref_event = reference_events[ref_align_idx]
        
        # Calculate shift needed
        shift_seconds = ref_event.start - source_event.start
        
        logger.info(f"Aligning at:")
        logger.info(f"  Source: Event {source_align_idx + 1} - {source_event.format_time_range()}")
        logger.info(f"  Reference: Event {ref_align_idx + 1} - {ref_event.format_time_range()}")
        logger.info(f"  Shift: {shift_seconds:+.3f} seconds")
        
        # Remove events before alignment point
        aligned_events = source_events[source_align_idx:]
        logger.info(f"  Removing {source_align_idx} events from source before alignment point")
        
        # Apply shift to all remaining events
        for event in aligned_events:
            event.start += shift_seconds
            event.end += shift_seconds
            
            # Ensure no negative times
            if event.start < 0:
                logger.debug(f"Adjusted negative start time for event: {event.text[:30]}...")
                event.start = 0
            if event.end < 0:
                logger.debug(f"Adjusted negative end time for event: {event.text[:30]}...")
                event.end = 0
        
        return aligned_events
    
    def get_alignment_preview(self, source_path: Path, reference_path: Path,
                             context_events: int = 5) -> dict:
        """
        Get a preview of events for alignment selection.
        
        Args:
            source_path: Path to source subtitle file
            reference_path: Path to reference subtitle file
            context_events: Number of events to show for context
            
        Returns:
            Dictionary with preview information
            
        Example:
            >>> realigner = SubtitleRealigner()
            >>> preview = realigner.get_alignment_preview(
            ...     Path("source.srt"), Path("reference.srt")
            ... )
        """
        try:
            source = SubtitleFormatFactory.parse_file(source_path)
            reference = SubtitleFormatFactory.parse_file(reference_path)
            
            # Get first few events from both files
            source_preview = []
            for i, event in enumerate(source.events[:context_events]):
                source_preview.append({
                    'index': i,
                    'time_range': event.format_time_range(),
                    'text': event.text[:100] + ('...' if len(event.text) > 100 else '')
                })
            
            reference_preview = []
            for i, event in enumerate(reference.events[:context_events]):
                reference_preview.append({
                    'index': i,
                    'time_range': event.format_time_range(),
                    'text': event.text[:100] + ('...' if len(event.text) > 100 else '')
                })
            
            return {
                'source': {
                    'path': source_path.name,
                    'total_events': len(source.events),
                    'preview': source_preview
                },
                'reference': {
                    'path': reference_path.name,
                    'total_events': len(reference.events),
                    'preview': reference_preview
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get alignment preview: {e}")
            return {}

    def find_automatic_alignments(self, source_path: Path, reference_path: Path,
                                 progress_callback: Optional[callable] = None) -> List[AlignmentMatch]:
        """
        Find automatic alignments using similarity analysis.

        Args:
            source_path: Path to source subtitle file
            reference_path: Path to reference subtitle file
            progress_callback: Optional callback for progress updates

        Returns:
            List of AlignmentMatch objects
        """
        if not self.similarity_aligner:
            logger.warning("Similarity aligner not initialized")
            return []

        try:
            # Load subtitle files
            source = SubtitleFormatFactory.parse_file(source_path)
            reference = SubtitleFormatFactory.parse_file(reference_path)

            if not source.events or not reference.events:
                logger.error("One or both files have no events")
                return []

            # --- Try multi-anchor alignment first (much faster than N*M) ---
            try:
                # Detect if same language
                src_sample = ' '.join(e.text for e in source.events[:10])
                ref_sample = ' '.join(e.text for e in reference.events[:10])
                src_lang = LanguageDetector.detect_language(src_sample)
                ref_lang = LanguageDetector.detect_language(ref_sample)
                same_language = (src_lang == ref_lang and src_lang != 'unknown')

                ma_aligner = MultiAnchorAligner(min_anchors=3)
                anchors = ma_aligner.find_anchors(
                    source.events, reference.events, same_language=same_language)

                if anchors:
                    # Convert AnchorPair results to AlignmentMatch format
                    ma_matches = []
                    for anchor in anchors:
                        ma_matches.append(AlignmentMatch(
                            source_index=anchor.source_index,
                            reference_index=anchor.reference_index,
                            confidence=anchor.confidence,
                            similarity_score=anchor.confidence,
                            method=f"multi_anchor_{anchor.match_method}",
                            source_text=source.events[anchor.source_index].text,
                            reference_text=reference.events[anchor.reference_index].text,
                        ))
                    logger.info(f"Multi-anchor alignment found {len(ma_matches)} matches")
                    if ma_matches:
                        return ma_matches
            except Exception as e:
                logger.warning(f"Multi-anchor alignment failed in realigner: {e}")

            # --- Fall through to existing N*M similarity analysis ---
            # Extract text content
            source_texts = [event.text for event in source.events]
            reference_texts = [event.text for event in reference.events]

            logger.info(f"Finding automatic alignments between {len(source_texts)} source and {len(reference_texts)} reference events")

            # Find alignments using similarity analysis
            matches = self.similarity_aligner.find_alignments(
                source_texts, reference_texts, progress_callback
            )

            logger.info(f"Found {len(matches)} automatic alignment matches")
            return matches

        except Exception as e:
            logger.error(f"Failed to find automatic alignments: {e}")
            return []

    def align_with_translation(self, source_path: Path, reference_path: Path,
                              output_path: Optional[Path] = None,
                              target_language: str = "en",
                              progress_callback: Optional[callable] = None,
                              translation_limit: int = 10,
                              confidence_threshold: float = 0.7) -> bool:
        """
        Align subtitles using optimized translation assistance for cross-language alignment.

        This method implements an efficient approach:
        1. Translates only the first N source events (default: 10) to reduce API costs
        2. Finds the best alignment point using similarity analysis
        3. Uses this point to synchronize the entire file
        4. Removes all subtitle entries before the alignment point for clean output

        Args:
            source_path: Path to source subtitle file
            reference_path: Path to reference subtitle file
            output_path: Output path (if None, overwrites source)
            target_language: Target language for translation
            progress_callback: Optional callback for progress updates
            translation_limit: Number of source events to translate for alignment detection
            confidence_threshold: Minimum confidence for reliable alignment point

        Returns:
            True if alignment was successful
        """
        if not self.translation_service:
            logger.error("Translation service not available")
            return False

        try:
            # Load subtitle files
            logger.info(f"Loading files for optimized translation-assisted alignment")
            source = SubtitleFormatFactory.parse_file(source_path)
            reference = SubtitleFormatFactory.parse_file(reference_path)

            if not source.events or not reference.events:
                logger.error("One or both files have no events")
                return False

            logger.info(f"Source file: {len(source.events)} events")
            logger.info(f"Reference file: {len(reference.events)} events")

            # Step 1: Use optimized alignment point detection
            source_idx, ref_idx, confidence = self.translation_service.find_alignment_point_with_translation(
                source.events,
                reference.events,
                target_language=target_language,
                translation_limit=translation_limit,
                confidence_threshold=confidence_threshold
            )

            if source_idx is None or ref_idx is None:
                logger.error(f"Failed to find reliable alignment point (confidence: {confidence:.3f})")
                return False

            logger.info(f"✅ Found alignment point: source[{source_idx}] -> reference[{ref_idx}] "
                       f"(confidence: {confidence:.3f})")

            # Step 2: Perform alignment using the detected synchronization point
            success = self.align_subtitles(
                source_path, reference_path, output_path,
                source_idx, ref_idx,
                create_backup=False
            )

            if success:
                logger.info("✅ Translation-assisted alignment completed successfully")

                # Step 3: Post-process to clean up pre-alignment entries if needed
                if output_path and output_path.exists() and source_idx > 0:
                    self._cleanup_pre_alignment_entries(output_path, source_idx)

            return success

        except Exception as e:
            logger.error(f"Translation-assisted alignment failed: {e}")
            return False

    def _cleanup_pre_alignment_entries(self, output_path: Path, alignment_start_index: int):
        """
        Remove subtitle entries that occur before the alignment point for cleaner output.

        Args:
            output_path: Path to the aligned subtitle file
            alignment_start_index: Index of the first aligned subtitle
        """
        try:
            if alignment_start_index <= 0:
                return  # No cleanup needed

            logger.info(f"Cleaning up {alignment_start_index} pre-alignment entries")

            # Load the aligned file
            aligned_file = SubtitleFormatFactory.parse_file(output_path)
            if not aligned_file or not aligned_file.events:
                return

            # Keep only events from the alignment point onwards
            cleaned_events = aligned_file.events[alignment_start_index:]

            if cleaned_events:
                # Renumber the events starting from 1
                for i, event in enumerate(cleaned_events):
                    event.index = i + 1

                # Create new subtitle file with cleaned events
                cleaned_file = SubtitleFile(
                    path=output_path,
                    events=cleaned_events,
                    format=aligned_file.format,
                    encoding=aligned_file.encoding
                )

                # Save the cleaned file
                SubtitleFormatFactory.save_subtitle_file(cleaned_file, output_path)
                logger.info(f"✅ Cleaned output: {len(cleaned_events)} events remaining")
            else:
                logger.warning("No events remaining after cleanup")

        except Exception as e:
            logger.warning(f"Failed to cleanup pre-alignment entries: {e}")

    def _translate_texts(self, texts: List[str], target_language: str,
                        progress_callback: Optional[callable] = None) -> Optional[List[str]]:
        """
        Translate a list of texts to the target language.

        Note: This method is kept for backward compatibility but the new optimized
        approach uses limited translation in find_alignment_point_with_translation.

        Args:
            texts: List of texts to translate
            target_language: Target language code
            progress_callback: Optional callback for progress updates

        Returns:
            List of translated texts or None if translation fails
        """
        if not self.translation_service:
            return None

        try:
            # Use the new subtitle events translation method
            # Convert texts to mock events for compatibility
            mock_events = [type('Event', (), {'text': text}) for text in texts]

            results = self.translation_service.translate_subtitle_events(
                mock_events, target_language, progress_callback=progress_callback
            )

            # Extract translated texts
            translated_texts = []
            for result in results:
                if result:
                    translated_texts.append(result.translated_text)
                else:
                    # Use original text if translation failed
                    translated_texts.append(texts[len(translated_texts)])

            successful = sum(1 for r in results if r is not None)
            logger.info(f"Translation completed: {successful}/{len(texts)} successful")

            return translated_texts

        except Exception as e:
            logger.error(f"Batch translation failed: {e}")
            return None
