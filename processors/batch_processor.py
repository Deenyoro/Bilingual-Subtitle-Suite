"""
Batch processing operations for subtitle files.

This module provides functionality for processing multiple subtitle files
and videos in batch operations with progress tracking and error handling.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logging_config import get_logger
from utils.file_operations import FileHandler
from .merger import BilingualMerger
from .converter import EncodingConverter
from .realigner import SubtitleRealigner

logger = get_logger(__name__)


class BatchProcessor:
    """Handles batch processing operations for subtitle files."""

    def __init__(self, max_workers: int = 4, auto_confirm: bool = False):
        """
        Initialize the batch processor.

        Args:
            max_workers: Maximum number of worker threads for parallel processing
            auto_confirm: Skip interactive confirmations for fully automated processing
        """
        self.max_workers = max_workers
        self.auto_confirm = auto_confirm
        self.merger = BilingualMerger()
        self.converter = EncodingConverter()
        self.realigner = SubtitleRealigner()
    
    def process_videos_batch(self, video_paths: List[Path], 
                           operation: str = "merge",
                           **kwargs) -> Dict[str, Any]:
        """
        Process multiple video files in batch.
        
        Args:
            video_paths: List of video file paths
            operation: Operation to perform ('merge', 'convert', 'realign')
            **kwargs: Additional arguments for the operation
            
        Returns:
            Dictionary with processing results
            
        Example:
            >>> processor = BatchProcessor()
            >>> results = processor.process_videos_batch(
            ...     [Path("movie1.mkv"), Path("movie2.mkv")], "merge"
            ... )
        """
        logger.info(f"Starting batch {operation} for {len(video_paths)} videos")
        
        results = {
            'total': len(video_paths),
            'successful': 0,
            'failed': 0,
            'errors': [],
            'processed_files': []
        }
        
        # Process videos sequentially for now (FFmpeg operations can be resource-intensive)
        for i, video_path in enumerate(video_paths, 1):
            logger.info(f"Processing video {i}/{len(video_paths)}: {video_path.name}")
            
            try:
                if operation == "merge":
                    success = self.merger.process_video(video_path, **kwargs)
                else:
                    logger.warning(f"Unsupported operation for videos: {operation}")
                    success = False
                
                if success:
                    results['successful'] += 1
                    results['processed_files'].append(str(video_path))
                    logger.info(f"✓ Successfully processed: {video_path.name}")
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Failed to process: {video_path.name}")
                    logger.error(f"✗ Failed to process: {video_path.name}")
                    
            except Exception as e:
                results['failed'] += 1
                error_msg = f"Error processing {video_path.name}: {e}"
                results['errors'].append(error_msg)
                logger.error(f"✗ {error_msg}")
        
        return results
    
    def process_subtitles_batch(self, subtitle_paths: List[Path],
                               operation: str = "convert",
                               parallel: bool = True,
                               **kwargs) -> Dict[str, Any]:
        """
        Process multiple subtitle files in batch.
        
        Args:
            subtitle_paths: List of subtitle file paths
            operation: Operation to perform ('convert', 'realign')
            parallel: Whether to use parallel processing
            **kwargs: Additional arguments for the operation
            
        Returns:
            Dictionary with processing results
            
        Example:
            >>> processor = BatchProcessor()
            >>> results = processor.process_subtitles_batch(
            ...     [Path("sub1.srt"), Path("sub2.srt")], "convert"
            ... )
        """
        logger.info(f"Starting batch {operation} for {len(subtitle_paths)} subtitle files")
        
        results = {
            'total': len(subtitle_paths),
            'successful': 0,
            'failed': 0,
            'unchanged': 0,
            'errors': [],
            'processed_files': []
        }
        
        if operation == "convert":
            if parallel:
                return self._process_convert_parallel(subtitle_paths, results, **kwargs)
            else:
                return self._process_convert_sequential(subtitle_paths, results, **kwargs)
        elif operation == "realign":
            # Realignment requires pairs, handle differently
            logger.warning("Realignment requires subtitle pairs, use process_realign_batch instead")
            return results
        else:
            logger.error(f"Unsupported operation: {operation}")
            return results
    
    def process_realign_batch(self, directory: Path, source_ext: str, 
                             reference_ext: str, **kwargs) -> Dict[str, Any]:
        """
        Process subtitle realignment in batch for matching pairs.
        
        Args:
            directory: Directory containing subtitle pairs
            source_ext: Source file extension
            reference_ext: Reference file extension
            **kwargs: Additional arguments for realignment
            
        Returns:
            Dictionary with processing results
            
        Example:
            >>> processor = BatchProcessor()
            >>> results = processor.process_realign_batch(
            ...     Path("/media"), ".zh.srt", ".en.srt"
            ... )
        """
        logger.info(f"Finding subtitle pairs in: {directory}")
        
        pairs = self.realigner.find_matching_pairs(directory, source_ext, reference_ext)
        
        if not pairs:
            logger.warning("No matching subtitle pairs found")
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'errors': [],
                'processed_files': []
            }
        
        logger.info(f"Found {len(pairs)} subtitle pairs")
        
        success_count, failure_count = self.realigner.batch_align(pairs, **kwargs)
        
        return {
            'total': len(pairs),
            'successful': success_count,
            'failed': failure_count,
            'errors': [],  # Detailed errors are logged by realigner
            'processed_files': [str(pair[0]) for pair in pairs[:success_count]]
        }
    
    def _process_convert_parallel(self, subtitle_paths: List[Path], 
                                 results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Process encoding conversion in parallel.
        
        Args:
            subtitle_paths: List of subtitle file paths
            results: Results dictionary to update
            **kwargs: Additional arguments for conversion
            
        Returns:
            Updated results dictionary
        """
        def convert_file(file_path: Path) -> Tuple[Path, bool, Optional[str]]:
            """Convert a single file and return result."""
            try:
                modified = self.converter.convert_file(file_path, **kwargs)
                return file_path, modified, None
            except Exception as e:
                return file_path, False, str(e)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(convert_file, path): path 
                for path in subtitle_paths
            }
            
            # Process completed tasks
            for future in as_completed(future_to_path):
                file_path, modified, error = future.result()
                
                if error:
                    results['failed'] += 1
                    error_msg = f"Error converting {file_path.name}: {error}"
                    results['errors'].append(error_msg)
                    logger.error(f"✗ {error_msg}")
                elif modified:
                    results['successful'] += 1
                    results['processed_files'].append(str(file_path))
                    logger.info(f"✓ Converted: {file_path.name}")
                else:
                    results['unchanged'] += 1
                    logger.debug(f"- Unchanged: {file_path.name}")
        
        return results
    
    def _process_convert_sequential(self, subtitle_paths: List[Path],
                                   results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Process encoding conversion sequentially.
        
        Args:
            subtitle_paths: List of subtitle file paths
            results: Results dictionary to update
            **kwargs: Additional arguments for conversion
            
        Returns:
            Updated results dictionary
        """
        for i, file_path in enumerate(subtitle_paths, 1):
            logger.debug(f"Processing {i}/{len(subtitle_paths)}: {file_path.name}")
            
            try:
                modified = self.converter.convert_file(file_path, **kwargs)
                
                if modified:
                    results['successful'] += 1
                    results['processed_files'].append(str(file_path))
                    logger.info(f"✓ Converted: {file_path.name}")
                else:
                    results['unchanged'] += 1
                    logger.debug(f"- Unchanged: {file_path.name}")
                    
            except Exception as e:
                results['failed'] += 1
                error_msg = f"Error converting {file_path.name}: {e}"
                results['errors'].append(error_msg)
                logger.error(f"✗ {error_msg}")
        
        return results
    
    def get_processing_summary(self, results: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of processing results.
        
        Args:
            results: Results dictionary from batch processing
            
        Returns:
            Formatted summary string
            
        Example:
            >>> processor = BatchProcessor()
            >>> summary = processor.get_processing_summary(results)
            >>> print(summary)
        """
        total = results.get('total', 0)
        successful = results.get('successful', 0)
        failed = results.get('failed', 0)
        unchanged = results.get('unchanged', 0)
        
        summary_lines = [
            f"Batch Processing Summary:",
            f"  Total files: {total}",
            f"  Successful: {successful}",
        ]
        
        if unchanged > 0:
            summary_lines.append(f"  Unchanged: {unchanged}")
        
        if failed > 0:
            summary_lines.append(f"  Failed: {failed}")
        
        if results.get('errors'):
            summary_lines.append(f"  Errors: {len(results['errors'])}")
        
        return '\n'.join(summary_lines)

    def process_directory_interactive(self, directory: Path, pattern: str = "*.mkv",
                                    merger_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process video files in directory with interactive confirmation for each file.

        Args:
            directory: Directory containing video files
            pattern: File pattern to match (default: "*.mkv")
            merger_options: Options to pass to BilingualMerger

        Returns:
            Dictionary with processing results
        """
        import time
        from core.video_containers import VideoContainerHandler

        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return {'total': 0, 'successful': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        # Find video files
        video_files = list(directory.glob(pattern))
        if not video_files:
            logger.warning(f"No video files found matching pattern '{pattern}' in {directory}")
            return {'total': 0, 'successful': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        logger.info(f"Found {len(video_files)} video files in {directory}")

        results = {
            'total': len(video_files),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'processed_files': []
        }

        # Initialize video handler for analysis
        video_handler = VideoContainerHandler()

        # Process each file with interactive confirmation
        for i, video_file in enumerate(video_files, 1):
            print(f"\n{'='*80}")
            print(f"BATCH PROCESSING: FILE {i}/{len(video_files)}")
            print(f"{'='*80}")
            print(f"Current file: {video_file.name}")
            print(f"Path: {video_file}")

            # Analyze video file
            try:
                print("\nAnalyzing video file...")
                start_time = time.time()

                # Get subtitle tracks info
                subtitle_tracks = video_handler.list_subtitle_tracks(video_file)

                if subtitle_tracks:
                    print(f"Detected subtitle tracks:")
                    for track in subtitle_tracks:
                        lang = track.language or 'unknown'
                        codec = track.codec or 'unknown'
                        title = track.title or 'N/A'
                        print(f"  - Track {track.track_id}: {lang} ({codec}) - {title}")
                else:
                    print("  No embedded subtitle tracks found")

                # Check for external subtitle files
                external_subs = self._find_external_subtitles(video_file)
                if external_subs:
                    print(f"External subtitle files:")
                    for sub_file in external_subs:
                        print(f"  - {sub_file.name}")
                else:
                    print("  No external subtitle files found")

                # Estimate processing time
                analysis_time = time.time() - start_time
                estimated_time = max(10, analysis_time * 5)  # Rough estimate
                print(f"\nEstimated processing time: ~{estimated_time:.0f} seconds")

            except Exception as e:
                logger.error(f"Error analyzing {video_file.name}: {e}")
                print(f"⚠️ Error analyzing file: {e}")

            # Interactive confirmation (unless auto-confirm is enabled)
            if self.auto_confirm:
                choice = 'y'
                print(f"Auto-confirm enabled: Processing file...")
            else:
                print(f"\nOptions:")
                print(f"  y = Yes, process this file")
                print(f"  n = No, skip this file")
                print(f"  s = Show manual alignment interface for this file")
                print(f"  q = Quit batch processing")

                try:
                    choice = input(f"\nProcess this file? (y/n/s/q): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print(f"\nBatch processing interrupted by user")
                    break

            # Handle user choice
            if choice == 'q':
                print(f"Batch processing stopped by user")
                break
            elif choice == 'n':
                print(f"⏭️ Skipping {video_file.name}")
                results['skipped'] += 1
                continue
            elif choice == 's':
                # Enable manual alignment for this file
                manual_options = merger_options.copy() if merger_options else {}
                manual_options.update({
                    'auto_align': True,
                    'manual_align': True
                })
                success = self._process_single_video(video_file, manual_options)
            elif choice == 'y':
                # Process with standard options
                success = self._process_single_video(video_file, merger_options)
            else:
                print(f"Invalid choice '{choice}', skipping file")
                results['skipped'] += 1
                continue

            # Update results
            if success:
                results['successful'] += 1
                results['processed_files'].append(str(video_file))
                print(f"✅ Successfully processed: {video_file.name}")
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed to process: {video_file.name}")
                print(f"❌ Failed to process: {video_file.name}")

        return results

    def _find_external_subtitles(self, video_file: Path) -> List[Path]:
        """Find external subtitle files for a video file."""
        base_name = video_file.stem
        subtitle_extensions = ['.srt', '.ass', '.ssa', '.vtt', '.zh.srt', '.en.srt']

        external_subs = []
        for ext in subtitle_extensions:
            sub_file = video_file.parent / f"{base_name}{ext}"
            if sub_file.exists():
                external_subs.append(sub_file)

        return external_subs

    def _process_single_video(self, video_file: Path, merger_options: Optional[Dict[str, Any]] = None) -> bool:
        """Process a single video file with the given options."""
        try:
            # Create merger with specified options
            if merger_options:
                merger = BilingualMerger(**merger_options)
            else:
                merger = self.merger

            # Process the video
            result = merger.process_video(video_file)
            return result

        except Exception as e:
            logger.error(f"Error processing {video_file.name}: {e}")
            return False
