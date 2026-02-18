"""
Video container operations and FFmpeg integration.

This module provides:
- Video file analysis and metadata extraction
- Embedded subtitle track detection and extraction
- FFmpeg command execution with proper error handling
- Subtitle track filtering and selection
"""

import json
import os
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from utils.constants import VIDEO_EXTENSIONS, FFMPEG_CODEC_MAP
from utils.logging_config import get_logger
from core.subtitle_formats import SubtitleTrack
from core.track_analyzer import SubtitleTrackAnalyzer

logger = get_logger(__name__)


class VideoContainerHandler:
    """Handles video container operations and FFmpeg integration."""
    
    @staticmethod
    def is_video_container(file_path: Path) -> bool:
        """
        Check if a file is a supported video container.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is a supported video container
            
        Example:
            >>> is_video = VideoContainerHandler.is_video_container(Path("movie.mkv"))
            >>> print(f"Is video: {is_video}")
        """
        return file_path.suffix.lower() in VIDEO_EXTENSIONS
    
    @staticmethod
    def run_command(cmd: List[str], capture_output: bool = True,
                   timeout: int = None) -> subprocess.CompletedProcess:
        """
        Run a command with proper error handling and optional timeout.

        Args:
            cmd: Command and arguments as list
            capture_output: Whether to capture stdout/stderr
            timeout: Command timeout in seconds (None = no timeout)

        Returns:
            CompletedProcess instance

        Example:
            >>> result = VideoContainerHandler.run_command(["ffprobe", "-version"])
            >>> print(f"Return code: {result.returncode}")
        """
        try:
            logger.debug(f"Running command: {' '.join(cmd[:3])}...")  # Show only first 3 args
            
            if capture_output:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=timeout
                )
            else:
                result = subprocess.run(cmd, timeout=timeout)

            if result.returncode != 0:
                logger.debug(f"Command failed with return code {result.returncode}")
                if hasattr(result, 'stderr') and result.stderr:
                    logger.debug(f"Command stderr: {result.stderr[:500]}...")

            return result
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s: {' '.join(cmd[:3])}...")
            # Create a dummy result
            class TimeoutResult:
                def __init__(self):
                    self.returncode = -1
                    self.stdout = ""
                    self.stderr = f"Command execution timed out after {timeout} seconds"
            return TimeoutResult()
            
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd[:3])}... - {e}")
            # Create a dummy result
            class ErrorResult:
                def __init__(self, error):
                    self.returncode = 1
                    self.stdout = ""
                    self.stderr = f"Command execution failed: {error}"
            return ErrorResult(str(e))
    
    @staticmethod
    def probe_video_file(video_path: Path) -> Dict[str, Any]:
        """
        Use ffprobe to get detailed information about a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Dictionary containing video metadata
            
        Example:
            >>> metadata = VideoContainerHandler.probe_video_file(Path("movie.mkv"))
            >>> print(f"Duration: {metadata.get('format', {}).get('duration')}")
        """
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        
        result = VideoContainerHandler.run_command(cmd, timeout=60)
        
        if result.returncode != 0:
            logger.error(f"ffprobe failed for {video_path.name}: {result.stderr}")
            return {}
        
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse ffprobe output for {video_path.name}")
            return {}
    
    @staticmethod
    def list_subtitle_tracks(video_path: Path) -> List[SubtitleTrack]:
        """
        List all subtitle tracks in a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of SubtitleTrack objects
            
        Example:
            >>> tracks = VideoContainerHandler.list_subtitle_tracks(Path("movie.mkv"))
            >>> print(f"Found {len(tracks)} subtitle tracks")
        """
        logger.info(f"Analyzing subtitle tracks in: {video_path.name}")
        
        # Try ffprobe first for detailed information
        probe_data = VideoContainerHandler.probe_video_file(video_path)
        
        if probe_data and 'streams' in probe_data:
            tracks = []
            subtitle_index = 0
            
            # For MKV files, get the mkvextract track IDs
            mkv_track_mapping = {}
            if video_path.suffix.lower() == '.mkv':
                mkv_track_mapping = VideoContainerHandler._get_mkvinfo_track_mapping(video_path)
            
            for stream in probe_data['streams']:
                if stream.get('codec_type') == 'subtitle':
                    # Get mkvextract track ID if available
                    mkv_track_id = mkv_track_mapping.get(subtitle_index, '')
                    
                    track = SubtitleTrack(
                        track_id=str(stream['index']),
                        codec=stream.get('codec_name', 'unknown'),
                        language=stream.get('tags', {}).get('language', ''),
                        title=stream.get('tags', {}).get('title', ''),
                        is_default=stream.get('disposition', {}).get('default', 0) == 1,
                        is_forced=stream.get('disposition', {}).get('forced', 0) == 1,
                        ffmpeg_index=f"0:{stream['index']}",
                        mkvextract_track_id=mkv_track_id
                    )
                    tracks.append(track)
                    subtitle_index += 1
            
            logger.info(f"Found {len(tracks)} subtitle tracks")
            return tracks
        
        # Fallback to parsing ffmpeg output
        return VideoContainerHandler._parse_ffmpeg_streams(video_path)
    
    @staticmethod
    def _parse_ffmpeg_streams(video_path: Path) -> List[SubtitleTrack]:
        """
        Parse subtitle streams from ffmpeg output (fallback method).
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of SubtitleTrack objects
        """
        cmd = ["ffmpeg", "-hide_banner", "-i", str(video_path)]
        result = VideoContainerHandler.run_command(cmd)
        
        tracks = []
        
        # Parse stream information from stderr
        stream_pattern = re.compile(
            r"Stream #(\d+):(\d+)(?:\((\w+)\))?: Subtitle: ([^,\n]+)([^\n]*)",
            re.IGNORECASE
        )
        
        for line in result.stderr.splitlines():
            match = stream_pattern.search(line)
            if match:
                file_idx = match.group(1)
                stream_idx = match.group(2)
                lang = match.group(3) or ""
                codec = match.group(4).strip()
                extra = match.group(5) or ""
                
                # Extract title if present
                title = ""
                title_match = re.search(r"title\s*:\s*([^,\n]+)", extra, re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).strip()
                
                # Check for default/forced flags
                is_default = "(default)" in extra.lower()
                is_forced = "(forced)" in extra.lower()
                
                track = SubtitleTrack(
                    track_id=stream_idx,
                    codec=codec,
                    language=lang.lower(),
                    title=title,
                    is_default=is_default,
                    is_forced=is_forced,
                    ffmpeg_index=f"{file_idx}:{stream_idx}"
                )
                tracks.append(track)
        
        logger.info(f"Found {len(tracks)} subtitle tracks")
        return tracks

    @staticmethod
    def _get_mkvinfo_track_mapping(video_path: Path) -> dict:
        """
        Get mapping of subtitle track indices to mkvextract track IDs using mkvinfo.
        
        Args:
            video_path: Path to the MKV file
            
        Returns:
            Dict mapping track language+index to mkvextract track ID
        """
        try:
            result = subprocess.run(
                ['mkvinfo', str(video_path)],
                capture_output=True,
                timeout=60
            )
            if result.returncode != 0:
                return {}
            
            mkvinfo_output = result.stdout.decode('utf-8', errors='replace')
        except (subprocess.SubprocessError, FileNotFoundError):
            return {}
        
        # Parse mkvinfo output to get track IDs for subtitle tracks
        # Returns dict: {subtitle_index: mkvextract_track_id}
        track_mapping = {}
        current_track_id = None
        subtitle_count = 0
        
        for line in mkvinfo_output.split('\n'):
            # Look for track ID line
            match = re.search(r'Track number: \d+ \(track ID for mkvmerge & mkvextract: (\d+)\)', line)
            if match:
                current_track_id = match.group(1)
            
            # Look for track type
            if current_track_id and 'Track type: subtitles' in line:
                track_mapping[subtitle_count] = current_track_id
                subtitle_count += 1
                current_track_id = None
        
        logger.debug(f"mkvinfo track mapping: {track_mapping}")
        return track_mapping

    @staticmethod
    def _check_mkvextract_available() -> bool:
        """Check if mkvextract is available on the system."""
        try:
            result = subprocess.run(
                ["mkvextract", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @staticmethod
    def _extract_with_mkvextract(video_path: Path, track: SubtitleTrack,
                                  output_path: Path) -> Optional[Path]:
        """
        Extract subtitle using mkvextract (much faster for MKV files).

        Args:
            video_path: Path to the MKV file
            track: SubtitleTrack to extract
            output_path: Output path for subtitle

        Returns:
            Path to extracted subtitle or None if failed
        """
        # Use mkvextract_track_id if available, otherwise try track_id
        mkv_track_id = track.mkvextract_track_id if track.mkvextract_track_id else track.track_id
        logger.debug(f"Using mkvextract for fast extraction of track {mkv_track_id}")

        cmd = [
            "mkvextract", str(video_path),
            "tracks", f"{mkv_track_id}:{output_path}"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"Successfully extracted subtitle to {output_path.name} (using mkvextract)")
                return output_path
            else:
                if result.stderr:
                    logger.debug(f"mkvextract stderr: {result.stderr}")
                return None

        except Exception as e:
            logger.debug(f"mkvextract failed: {e}")
            return None

    @staticmethod
    def extract_subtitle_track(video_path: Path, track: SubtitleTrack,
                              output_path: Path) -> Optional[Path]:
        """
        Extract a subtitle track from a video file.

        Args:
            video_path: Path to the video file
            track: SubtitleTrack object to extract
            output_path: Desired output path

        Returns:
            Path to extracted subtitle file or None if extraction failed

        Example:
            >>> extracted = VideoContainerHandler.extract_subtitle_track(
            ...     Path("movie.mkv"), track, Path("subtitle.srt")
            ... )
        """
        logger.info(f"Extracting subtitle track {track.track_id} ({track.language}) "
                   f"to {output_path.name}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine output format from extension
        output_ext = output_path.suffix.lower()

        # Determine appropriate extension based on codec
        if track.codec.lower() in ['subrip', 'srt']:
            copy_ext = '.srt'
        elif track.codec.lower() in ['ass', 'ssa']:
            copy_ext = '.ass'
        elif track.codec.lower() in ['webvtt', 'vtt']:
            copy_ext = '.vtt'
        else:
            copy_ext = '.srt'  # Default fallback

        # Adjust output path if needed
        if output_ext != copy_ext:
            output_path = output_path.with_suffix(copy_ext)

        # For MKV files, try mkvextract first (much faster)
        if video_path.suffix.lower() == '.mkv' and VideoContainerHandler._check_mkvextract_available():
            result = VideoContainerHandler._extract_with_mkvextract(video_path, track, output_path)
            if result:
                return result
            logger.debug("mkvextract failed, falling back to ffmpeg")

        # Fallback to ffmpeg
        logger.info("Using ffmpeg for extraction (this may take a while for large files)...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"subtitle{copy_ext}"

            # CRITICAL: Do NOT use -avoid_negative_ts make_zero as it shifts timing to start from 0
            # This would break video synchronization for embedded subtitles
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                "-fflags", "+genpts",
                "-i", str(video_path),
                "-map", track.ffmpeg_index,
                "-c:s", "copy",
                str(tmp_path)
            ]

            result = VideoContainerHandler.run_command(cmd)

            if result.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
                try:
                    shutil.copy2(tmp_path, output_path)
                    logger.info(f"Successfully extracted subtitle to {output_path.name}")
                    return output_path
                except Exception as e:
                    logger.error(f"Failed to copy extracted subtitle: {e}")
                    return None

            # If direct copy failed, try format conversion only if necessary
            if output_ext and output_ext != copy_ext:
                logger.debug(f"Direct copy failed, trying format conversion to {output_ext}")

                output_format = FFMPEG_CODEC_MAP.get(output_ext, 'srt')
                tmp_path_converted = Path(tmp_dir) / f"subtitle_converted{output_ext}"

                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
                    "-map", track.ffmpeg_index,
                    "-c:s", output_format,
                    str(tmp_path_converted)
                ]

                result = VideoContainerHandler.run_command(cmd)

                if (result.returncode == 0 and tmp_path_converted.exists() and
                    tmp_path_converted.stat().st_size > 0):
                    try:
                        shutil.copy2(tmp_path_converted, output_path)
                        logger.info(f"Successfully extracted and converted subtitle to {output_path.name}")
                        return output_path
                    except Exception as e:
                        logger.error(f"Failed to copy converted subtitle: {e}")
                        return None

        logger.error(f"Failed to extract subtitle track {track.track_id}")
        return None

    @staticmethod
    def find_subtitle_track(tracks: List[SubtitleTrack],
                           language_codes: set,
                           prefer_track: Optional[str] = None,
                           remap_lang: Optional[str] = None) -> Optional[SubtitleTrack]:
        """
        Find the best matching subtitle track based on language preferences.

        Args:
            tracks: List of available subtitle tracks
            language_codes: Set of language codes to match
            prefer_track: Specific track ID to prefer
            remap_lang: Language code to treat as target language

        Returns:
            Best matching SubtitleTrack or None

        Example:
            >>> track = VideoContainerHandler.find_subtitle_track(
            ...     tracks, {'en', 'eng'}, prefer_track="2"
            ... )
        """
        if not tracks:
            return None

        # If specific track requested, find it
        if prefer_track is not None:
            for track in tracks:
                if track.track_id == str(prefer_track):
                    logger.info(f"Using preferred track: {track.track_id}")
                    return track

        # Check for remapped language
        if remap_lang:
            for track in tracks:
                if track.language.lower() == remap_lang.lower():
                    logger.info(f"Found remapped language track: {track.track_id} ({remap_lang})")
                    return track

        # Find tracks matching language codes
        matching_tracks = []
        for track in tracks:
            # Check language code
            if track.language.lower() in language_codes:
                matching_tracks.append(track)
                continue

            # Check title for language hints
            title_lower = track.title.lower()
            if any(code in title_lower for code in language_codes):
                matching_tracks.append(track)

        if not matching_tracks:
            return None

        # Prefer non-forced tracks
        non_forced = [t for t in matching_tracks if not t.is_forced]
        if non_forced:
            matching_tracks = non_forced

        # Prefer default track
        default_tracks = [t for t in matching_tracks if t.is_default]
        if default_tracks:
            return default_tracks[0]

        # Return first matching track
        return matching_tracks[0]

    @staticmethod
    def find_best_english_dialogue_track(tracks: List[SubtitleTrack],
                                        video_path: Optional[Path] = None,
                                        prefer_track: Optional[str] = None) -> Optional[SubtitleTrack]:
        """
        Find the best English dialogue track using intelligent analysis.

        This method uses advanced heuristics to identify the main dialogue track
        while avoiding signs, songs, and forced tracks.

        Args:
            tracks: List of available subtitle tracks
            video_path: Optional path to video file for content analysis
            prefer_track: Specific track ID to prefer (overrides analysis)

        Returns:
            Best English dialogue track or None if no suitable track found

        Example:
            >>> track = VideoContainerHandler.find_best_english_dialogue_track(tracks, video_path)
            >>> if track:
            ...     print(f"Selected dialogue track: {track.track_id} - {track.title}")
        """
        if not tracks:
            logger.warning("No subtitle tracks available for analysis")
            return None

        # If specific track requested, find and return it
        if prefer_track is not None:
            for track in tracks:
                if track.track_id == str(prefer_track):
                    logger.info(f"Using user-specified track: {track.track_id}")
                    return track
            logger.warning(f"Preferred track {prefer_track} not found, using intelligent selection")

        # Filter for English tracks
        english_codes = {'en', 'eng', 'english'}
        english_tracks = []

        for track in tracks:
            # Check language code
            if track.language.lower() in english_codes:
                english_tracks.append(track)
                continue

            # Check title for English hints
            title_lower = track.title.lower()
            if any(code in title_lower for code in english_codes):
                english_tracks.append(track)
                continue

            # If no language specified, assume it might be English
            if not track.language and not track.title:
                english_tracks.append(track)

        if not english_tracks:
            logger.warning("No English subtitle tracks found")
            return None

        if len(english_tracks) == 1:
            logger.info(f"Only one English track found: {english_tracks[0].track_id}")
            return english_tracks[0]

        # Multiple English tracks - use intelligent analysis
        logger.info(f"Found {len(english_tracks)} English tracks, analyzing for best dialogue track...")

        # Convert tracks to analysis format
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

        # Select best dialogue track
        best_score = analyzer.select_best_dialogue_track(scores)

        if best_score:
            # Find the corresponding SubtitleTrack object
            for track in english_tracks:
                if track.track_id == best_score.track_id:
                    logger.info(f"✅ Selected English dialogue track: {track.track_id} '{track.title}' "
                              f"(Score: {best_score.total_score:.3f})")
                    return track

        # Fallback: return first English track
        logger.warning("Intelligent analysis failed, using first English track as fallback")
        return english_tracks[0]
