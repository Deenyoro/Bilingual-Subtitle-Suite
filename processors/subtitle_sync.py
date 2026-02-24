"""
Subtitle sync processor for auto-aligning external subtitles to embedded video tracks.

Uses ffprobe packet reading to extract embedded subtitle timestamps (near-instant,
no temp files) and compares them against external SRT timestamps to auto-detect
and apply timing offsets.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SyncResult:
    """Result of a subtitle sync operation."""
    video: Path
    subtitle: Path
    offset_ms: int
    shift_applied_ms: int  # -offset_ms (the correction applied)
    match_count: int
    total_compared: int
    track_used: str  # e.g. "s:5 chi Chinese (Simplified)"
    success: bool
    message: str = ""


class SubtitleSync:
    """Auto-align external subtitles to embedded video subtitle tracks.

    Uses ffprobe -show_packets -read_intervals for near-instant timestamp
    extraction from embedded tracks, then compares against external SRT
    timestamps to detect and apply timing offsets.
    """

    # Text-based subtitle codecs that can be timestamp-compared
    TEXT_CODECS = {'subrip', 'ass', 'ssa', 'webvtt', 'srt', 'mov_text'}

    def list_subtitle_tracks(self, video_path: Path) -> List[dict]:
        """List subtitle tracks in a video file.

        Args:
            video_path: Path to the video file

        Returns:
            List of track dicts with keys:
                rel_index, abs_index, codec, lang, title, is_text
        """
        cmd = [
            'ffprobe', '-v', 'quiet', '-select_streams', 's',
            '-show_entries', 'stream=index,codec_name:stream_tags=language,title',
            '-print_format', 'json', str(video_path)
        ]

        result = self._run_command(cmd, timeout=30)
        if result.returncode != 0:
            logger.error(f"ffprobe failed for {video_path.name}: {getattr(result, 'stderr', '')}")
            return []

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, AttributeError):
            logger.error(f"Failed to parse ffprobe output for {video_path.name}")
            return []

        tracks = []
        for rel_idx, stream in enumerate(data.get('streams', [])):
            codec = stream.get('codec_name', 'unknown')
            tags = stream.get('tags', {})
            # Normalize tag keys to lowercase
            tags_lower = {k.lower(): v for k, v in tags.items()}
            track = {
                'rel_index': rel_idx,
                'abs_index': stream.get('index', rel_idx),
                'codec': codec,
                'lang': tags_lower.get('language', ''),
                'title': tags_lower.get('title', ''),
                'is_text': codec.lower() in self.TEXT_CODECS,
            }
            tracks.append(track)

        logger.info(f"Found {len(tracks)} subtitle tracks in {video_path.name} "
                    f"({sum(1 for t in tracks if t['is_text'])} text-based)")
        return tracks

    def get_embedded_timestamps(self, video_path: Path, sub_stream_index: int,
                                duration_secs: int = 120) -> List[int]:
        """Get subtitle packet timestamps from an embedded track.

        Uses ffprobe -show_packets with -read_intervals for near-instant
        extraction without temp files.

        Args:
            video_path: Path to the video file
            sub_stream_index: Relative subtitle stream index (e.g. 5 for s:5)
            duration_secs: How many seconds from start to read (default 120)

        Returns:
            List of start timestamps in milliseconds, sorted
        """
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-select_streams', f's:{sub_stream_index}',
            '-show_entries', 'packet=pts_time',
            '-read_intervals', f'%+{duration_secs}',
            '-print_format', 'json', str(video_path)
        ]

        result = self._run_command(cmd, timeout=60)
        if result.returncode != 0:
            logger.error(f"ffprobe packet read failed for s:{sub_stream_index}: "
                        f"{getattr(result, 'stderr', '')}")
            return []

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, AttributeError):
            logger.error("Failed to parse ffprobe packet output")
            return []

        timestamps = []
        for packet in data.get('packets', []):
            pts_time = packet.get('pts_time')
            if pts_time is not None:
                try:
                    ms = int(float(pts_time) * 1000)
                    timestamps.append(ms)
                except (ValueError, TypeError):
                    continue

        # Deduplicate and sort
        timestamps = sorted(set(timestamps))
        logger.debug(f"Got {len(timestamps)} embedded timestamps from s:{sub_stream_index} "
                    f"(first {duration_secs}s)")
        return timestamps

    def get_srt_timestamps(self, srt_path: Path, count: int = 15) -> List[int]:
        """Get start timestamps from an external SRT file.

        Args:
            srt_path: Path to the SRT file
            count: Maximum number of timestamps to return

        Returns:
            List of start timestamps in milliseconds
        """
        timestamps = []

        try:
            # Try common encodings
            content = None
            for encoding in ['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'latin-1']:
                try:
                    content = srt_path.read_text(encoding=encoding)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if content is None:
                logger.error(f"Could not read {srt_path.name} with any encoding")
                return []

            # Parse SRT timestamps: "00:01:23,456 --> 00:01:25,789"
            pattern = re.compile(
                r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->'
            )

            for match in pattern.finditer(content):
                h, m, s, ms = match.groups()
                total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
                timestamps.append(total_ms)
                if len(timestamps) >= count:
                    break

        except Exception as e:
            logger.error(f"Failed to read SRT timestamps from {srt_path.name}: {e}")

        logger.debug(f"Got {len(timestamps)} SRT timestamps from {srt_path.name}")
        return timestamps

    def calculate_offset(self, ext_timestamps: List[int],
                        emb_timestamps: List[int]) -> Tuple[int, int, str]:
        """Calculate the timing offset between external and embedded timestamps.

        Uses sliding window matching: tries all starting point combinations
        and counts matching pairs within tolerance.

        Args:
            ext_timestamps: Timestamps from external subtitle (ms)
            emb_timestamps: Timestamps from embedded track (ms)

        Returns:
            Tuple of (offset_ms, match_count, info_str)
            offset_ms: The detected offset (external - embedded timing)
            match_count: Number of timestamp pairs that matched
            info_str: Human-readable description
        """
        if not ext_timestamps or not emb_timestamps:
            return 0, 0, "No timestamps to compare"

        tolerance_ms = 200  # Allow 200ms tolerance for matching
        best_offset = 0
        best_matches = 0
        best_info = ""

        # Try each combination of external[i] vs embedded[j] as anchor
        for i, ext_t in enumerate(ext_timestamps):
            for j, emb_t in enumerate(emb_timestamps):
                candidate_offset = ext_t - emb_t
                matches = 0

                # Count how many other pairs match at this offset
                for ext_ts in ext_timestamps:
                    expected_emb = ext_ts - candidate_offset
                    # Binary-ish search: check if any embedded ts is close
                    for emb_ts in emb_timestamps:
                        if abs(emb_ts - expected_emb) <= tolerance_ms:
                            matches += 1
                            break

                if matches > best_matches:
                    best_matches = matches
                    best_offset = candidate_offset
                    best_info = (f"offset={best_offset:+d}ms, "
                               f"{best_matches}/{len(ext_timestamps)} matches "
                               f"(anchor: ext[{i}]={ext_t}ms vs emb[{j}]={emb_t}ms)")

        logger.info(f"Offset detection: {best_info}")
        return best_offset, best_matches, best_info

    def detect_offset(self, video_path: Path, srt_path: Path,
                     track_index: Optional[int] = None,
                     track_lang: Optional[str] = None) -> SyncResult:
        """Detect timing offset between external SRT and embedded track.

        Args:
            video_path: Path to the video file
            srt_path: Path to the external SRT file
            track_index: Specific subtitle stream relative index (e.g. 5)
            track_lang: Language code to match (e.g. 'chi', 'eng')

        Returns:
            SyncResult with offset information (no changes applied)
        """
        # List available tracks
        tracks = self.list_subtitle_tracks(video_path)
        text_tracks = [t for t in tracks if t['is_text']]

        if not text_tracks:
            return SyncResult(
                video=video_path, subtitle=srt_path,
                offset_ms=0, shift_applied_ms=0,
                match_count=0, total_compared=0,
                track_used="none", success=False,
                message="No text-based subtitle tracks found in video"
            )

        # Select track
        selected_track = None

        if track_index is not None:
            # Use specified track index
            selected_track = next(
                (t for t in text_tracks if t['rel_index'] == track_index), None
            )
            if not selected_track:
                return SyncResult(
                    video=video_path, subtitle=srt_path,
                    offset_ms=0, shift_applied_ms=0,
                    match_count=0, total_compared=0,
                    track_used=f"s:{track_index}", success=False,
                    message=f"Track s:{track_index} not found or not text-based"
                )
        elif track_lang:
            # Find first text track matching language
            selected_track = next(
                (t for t in text_tracks if t['lang'].lower().startswith(track_lang.lower())),
                None
            )
            if not selected_track:
                return SyncResult(
                    video=video_path, subtitle=srt_path,
                    offset_ms=0, shift_applied_ms=0,
                    match_count=0, total_compared=0,
                    track_used=f"lang:{track_lang}", success=False,
                    message=f"No text track with language '{track_lang}' found"
                )
        else:
            # Auto-pick: try to detect external SRT language and match
            selected_track = self._auto_select_track(srt_path, text_tracks)

        if not selected_track:
            return SyncResult(
                video=video_path, subtitle=srt_path,
                offset_ms=0, shift_applied_ms=0,
                match_count=0, total_compared=0,
                track_used="none", success=False,
                message="Could not auto-select a matching track"
            )

        track_desc = self._track_description(selected_track)
        logger.info(f"Using track: {track_desc}")

        # Get timestamps
        emb_timestamps = self.get_embedded_timestamps(
            video_path, selected_track['rel_index']
        )
        ext_timestamps = self.get_srt_timestamps(srt_path)

        if not emb_timestamps:
            return SyncResult(
                video=video_path, subtitle=srt_path,
                offset_ms=0, shift_applied_ms=0,
                match_count=0, total_compared=len(ext_timestamps),
                track_used=track_desc, success=False,
                message="No timestamps found in embedded track"
            )

        if not ext_timestamps:
            return SyncResult(
                video=video_path, subtitle=srt_path,
                offset_ms=0, shift_applied_ms=0,
                match_count=0, total_compared=0,
                track_used=track_desc, success=False,
                message="No timestamps found in external SRT"
            )

        # Calculate offset
        offset_ms, match_count, info = self.calculate_offset(
            ext_timestamps, emb_timestamps
        )

        return SyncResult(
            video=video_path, subtitle=srt_path,
            offset_ms=offset_ms, shift_applied_ms=-offset_ms,
            match_count=match_count, total_compared=len(ext_timestamps),
            track_used=track_desc, success=True,
            message=info
        )

    def sync_file(self, video_path: Path, srt_path: Path,
                 track_index: Optional[int] = None,
                 track_lang: Optional[str] = None,
                 backup: bool = True,
                 dry_run: bool = False) -> SyncResult:
        """Detect offset and apply correction to an external SRT file.

        Args:
            video_path: Path to the video file
            srt_path: Path to the external SRT file
            track_index: Specific subtitle stream relative index
            track_lang: Language code to match
            backup: Whether to create a backup before modifying
            dry_run: If True, detect offset but don't apply changes

        Returns:
            SyncResult with offset and operation details
        """
        result = self.detect_offset(video_path, srt_path, track_index, track_lang)

        if not result.success:
            return result

        if result.offset_ms == 0:
            result.message = "No offset detected - subtitles appear to be in sync"
            return result

        if dry_run:
            result.message = (f"[DRY RUN] Would shift by {result.shift_applied_ms:+d}ms "
                            f"(detected offset: {result.offset_ms:+d}ms, "
                            f"{result.match_count}/{result.total_compared} matches)")
            return result

        # Apply the shift
        from processors.timing_adjuster import TimingAdjuster

        adjuster = TimingAdjuster(create_backup=backup)
        shift_ms = -result.offset_ms  # Negate: if ext is +5000ms ahead, shift by -5000ms

        success = adjuster.adjust_by_offset(srt_path, shift_ms)

        if success:
            result.message = (f"Shifted by {shift_ms:+d}ms "
                            f"(offset was {result.offset_ms:+d}ms, "
                            f"{result.match_count}/{result.total_compared} matches)")
            logger.info(f"Synced {srt_path.name}: {result.message}")
        else:
            result.success = False
            result.message = f"Failed to apply timing shift of {shift_ms:+d}ms"

        return result

    def sync_directory(self, directory: Path,
                      track_index: Optional[int] = None,
                      track_lang: Optional[str] = None,
                      backup: bool = True,
                      dry_run: bool = False) -> List[SyncResult]:
        """Sync all matching MKV + SRT pairs in a directory.

        Finds all MKV files and matches each to a .srt file by stem name
        (supports suffix patterns like .zh-en.srt, .zh.srt, etc.).

        Args:
            directory: Directory containing video and subtitle files
            track_index: Subtitle stream relative index for all files
            track_lang: Language code to match for all files
            backup: Whether to create backups
            dry_run: If True, detect offsets without applying

        Returns:
            List of SyncResult for each processed pair
        """
        from utils.file_operations import FileHandler

        results = []

        # Find all MKV files
        video_files = sorted(directory.glob('*.mkv'))
        if not video_files:
            # Also check for other video formats
            video_files = FileHandler.find_video_files(directory, recursive=False)

        if not video_files:
            logger.warning(f"No video files found in {directory}")
            return results

        # Find all SRT files
        srt_files = sorted(directory.glob('*.srt'))
        if not srt_files:
            logger.warning(f"No SRT files found in {directory}")
            return results

        # Match video to SRT by stem
        for video_path in video_files:
            video_stem = video_path.stem.lower()
            matched_srt = None

            for srt_path in srt_files:
                # SRT stem should start with the video stem
                # e.g. "Movie.zh-en.srt" matches "Movie.mkv"
                srt_stem = srt_path.stem.lower()
                # Check if srt name starts with video stem, or vice versa
                # Handle: Movie.srt, Movie.zh.srt, Movie.zh-en.srt
                if srt_stem == video_stem or srt_stem.startswith(video_stem + '.'):
                    matched_srt = srt_path
                    break

            if not matched_srt:
                logger.debug(f"No matching SRT for {video_path.name}")
                continue

            logger.info(f"Matched: {video_path.name} <-> {matched_srt.name}")

            result = self.sync_file(
                video_path, matched_srt,
                track_index=track_index,
                track_lang=track_lang,
                backup=backup,
                dry_run=dry_run
            )
            results.append(result)

        return results

    def _auto_select_track(self, srt_path: Path, text_tracks: List[dict]) -> Optional[dict]:
        """Auto-select the best matching embedded track for an external SRT.

        Tries to detect the external SRT's language and pick a matching track.
        Falls back to the first text track if detection fails.
        """
        if not text_tracks:
            return None

        # Try to detect language from SRT content
        srt_lang = self._detect_srt_language(srt_path)

        if srt_lang:
            # Map detected language to ffprobe language codes
            lang_map = {
                'zh': ['chi', 'zho', 'zh'],
                'ja': ['jpn', 'ja'],
                'ko': ['kor', 'ko'],
                'en': ['eng', 'en'],
            }

            codes = lang_map.get(srt_lang, [])
            if codes:
                for track in text_tracks:
                    track_lang = track['lang'].lower()
                    if any(track_lang.startswith(c) for c in codes):
                        logger.info(f"Auto-selected track by language match: "
                                  f"{self._track_description(track)}")
                        return track

        # Fallback: use the first text track
        logger.info(f"Auto-selecting first text track: "
                   f"{self._track_description(text_tracks[0])}")
        return text_tracks[0]

    def _detect_srt_language(self, srt_path: Path) -> Optional[str]:
        """Detect language of an SRT file from filename patterns and content."""
        name_lower = srt_path.name.lower()

        # Check filename patterns
        if any(p in name_lower for p in ['.zh.', '.chi.', '.chs.', '.cht.',
                                          '.zh-', '.chinese.']):
            return 'zh'
        if any(p in name_lower for p in ['.ja.', '.jpn.', '.japanese.']):
            return 'ja'
        if any(p in name_lower for p in ['.ko.', '.kor.', '.korean.']):
            return 'ko'
        if any(p in name_lower for p in ['.en.', '.eng.', '.english.']):
            return 'en'

        # Check content for CJK characters
        try:
            content = None
            for enc in ['utf-8', 'utf-8-sig', 'gb18030', 'latin-1']:
                try:
                    content = srt_path.read_text(encoding=enc)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if content:
                # Count CJK characters in first 2000 chars
                sample = content[:2000]
                cjk_count = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff'
                               or '\u3040' <= c <= '\u309f'
                               or '\u30a0' <= c <= '\u30ff'
                               or '\uac00' <= c <= '\ud7af')
                if cjk_count > 10:
                    # Distinguish Chinese vs Japanese vs Korean
                    jp_kana = sum(1 for c in sample if '\u3040' <= c <= '\u30ff')
                    kr_chars = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
                    if kr_chars > jp_kana and kr_chars > cjk_count * 0.3:
                        return 'ko'
                    elif jp_kana > cjk_count * 0.1:
                        return 'ja'
                    return 'zh'
        except Exception:
            pass

        return None

    @staticmethod
    def _track_description(track: dict) -> str:
        """Format a human-readable track description."""
        parts = [f"s:{track['rel_index']}"]
        if track['lang']:
            parts.append(track['lang'])
        if track['title']:
            parts.append(track['title'])
        parts.append(f"({track['codec']})")
        return ' '.join(parts)

    @staticmethod
    def _run_command(cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a subprocess command with error handling."""
        try:
            return subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s: {' '.join(cmd[:3])}...")

            class TimeoutResult:
                def __init__(self):
                    self.returncode = -1
                    self.stdout = ""
                    self.stderr = f"Command timed out after {timeout}s"
            return TimeoutResult()
        except FileNotFoundError:
            logger.error("ffprobe not found. Please install FFmpeg and ensure it's in PATH.")

            class NotFoundResult:
                def __init__(self):
                    self.returncode = -1
                    self.stdout = ""
                    self.stderr = "ffprobe not found"
            return NotFoundResult()
        except Exception as e:
            logger.error(f"Command failed: {e}")

            class ErrorResult:
                def __init__(self):
                    self.returncode = -1
                    self.stdout = ""
                    self.stderr = str(e)
            return ErrorResult()
