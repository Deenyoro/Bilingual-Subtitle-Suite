"""
PGSRip Integration Wrapper

This module provides a clean interface for integrating PGSRip functionality
into the unified subtitle processor. It handles PGS subtitle detection,
extraction, and conversion to SRT format.

Features:
- PGS subtitle detection in video containers
- Automatic OCR language detection
- Batch processing support
- Integration with existing subtitle workflows
- Clean error handling and logging
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.video_containers import VideoContainerHandler
from core.subtitle_formats import SubtitleTrack
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PGSRipNotInstalledError(Exception):
    """Raised when PGSRip is not properly installed."""
    pass


@dataclass
class PGSTrack:
    """Represents a PGS/image-based subtitle track."""
    track_id: str
    language: str = ""
    title: str = ""
    is_default: bool = False
    is_forced: bool = False
    ffmpeg_index: str = ""
    estimated_language: str = ""  # OCR language estimation
    track_type: str = "pgs"  # 'pgs', 'dvdsub', or 'dvbsub'


class PGSRipWrapper:
    """Wrapper for PGSRip functionality integration."""
    
    def __init__(self):
        """Initialize the PGSRip wrapper."""
        self.third_party_dir = Path(__file__).parent
        self.install_dir = self.third_party_dir / "pgsrip_install"
        self.config_file = self.install_dir / "pgsrip_config.json"
        
        self.config = self._load_config()
        self.is_installed = self._check_installation()
        
        if self.is_installed:
            self._setup_environment()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load PGSRip configuration."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load PGSRip config: {e}")
        
        return {}
    
    def _check_installation(self) -> bool:
        """Check if PGSRip is properly installed or bundled."""
        # Check for PGSRip library (either in install_dir or importable)
        has_pgsrip = (self.install_dir / "pgsrip").exists()
        if not has_pgsrip:
            try:
                import pgsrip
                has_pgsrip = True
            except ImportError:
                pass
        if not has_pgsrip:
            return False

        # Check for tessdata (bundled or in install_dir)
        tessdata = self._get_tessdata_path()
        if not tessdata:
            return False

        # Check if tesseract is available (bundled, PATH, or common locations)
        self._tesseract_path = self._find_tesseract()
        if not self._tesseract_path:
            return False

        # Check if mkvextract is available
        try:
            result = subprocess.run(['mkvextract', '--version'],
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return False
        except FileNotFoundError:
            return False

        return True

    def _find_tesseract(self) -> Optional[str]:
        """Find tesseract executable, checking bundled, PATH, and common install locations."""
        candidates = []

        # 1. Check bundled Tesseract next to the executable (PyInstaller build)
        exe_dir = Path(sys.executable).parent
        if sys.platform == 'win32':
            bundled = exe_dir / "tesseract" / "tesseract.exe"
        else:
            bundled = exe_dir / "tesseract" / "tesseract"
        if bundled.exists():
            candidates.append(str(bundled))

        # 2. Check PyInstaller _MEIPASS temporary directory
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            meipass_path = Path(meipass)
            if sys.platform == 'win32':
                candidates.append(str(meipass_path / "tesseract" / "tesseract.exe"))
            else:
                candidates.append(str(meipass_path / "tesseract" / "tesseract"))

        # 3. Check stored path from setup
        stored_path_file = self.install_dir / "tesseract" / "tesseract_path.txt"
        if stored_path_file.exists():
            try:
                candidates.append(stored_path_file.read_text().strip())
            except Exception:
                pass

        # 4. Check PATH
        candidates.append("tesseract")

        # 5. Check common OS install locations
        if sys.platform == 'win32':
            candidates.extend([
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\tools\tesseract\tesseract.exe",
                r"C:\ProgramData\chocolatey\lib\tesseract\tools\tesseract.exe",
            ])
        else:
            candidates.extend([
                "/usr/bin/tesseract",
                "/usr/local/bin/tesseract",
                "/opt/homebrew/bin/tesseract",
            ])

        for candidate in candidates:
            try:
                result = subprocess.run([candidate, '--version'],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    return candidate
            except (FileNotFoundError, OSError):
                continue
        return None

    def _setup_environment(self):
        """Setup environment variables for PGSRip."""
        # Check for bundled tessdata first (PyInstaller build), then install_dir
        tessdata_dir = None
        exe_dir = Path(sys.executable).parent
        bundled_tessdata = exe_dir / "tessdata"
        meipass = getattr(sys, '_MEIPASS', None)
        meipass_tessdata = Path(meipass) / "tessdata" if meipass else None

        if bundled_tessdata.exists():
            tessdata_dir = bundled_tessdata
        elif meipass_tessdata and meipass_tessdata.exists():
            tessdata_dir = meipass_tessdata
        elif (self.install_dir / "tessdata").exists():
            tessdata_dir = self.install_dir / "tessdata"

        if tessdata_dir:
            os.environ['TESSDATA_PREFIX'] = str(tessdata_dir)

        python_packages_dir = self.install_dir / "python_packages"
        if python_packages_dir.exists():
            python_packages_path = str(python_packages_dir)
            if python_packages_path not in sys.path:
                sys.path.insert(0, python_packages_path)
    
    def _get_tessdata_path(self) -> Optional[Path]:
        """Get the best available tessdata directory path."""
        exe_dir = Path(sys.executable).parent
        candidates = [
            exe_dir / "tessdata",  # Bundled next to exe
        ]
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(Path(meipass) / "tessdata")
        candidates.append(self.install_dir / "tessdata")

        for candidate in candidates:
            if candidate.exists() and any(candidate.glob("*.traineddata")):
                return candidate
        return None

    def is_available(self) -> bool:
        """Check if PGSRip is available for use."""
        return self.is_installed
    
    def get_installation_status(self) -> Dict[str, Any]:
        """Get detailed installation status."""
        if not self.is_installed:
            return {
                'installed': False,
                'error': 'PGSRip is not installed. Run: python third_party/setup_pgsrip.py install'
            }
        
        return {
            'installed': True,
            'config': self.config,
            'languages': self.get_supported_languages()
        }
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported OCR languages."""
        if not self.is_installed:
            return []

        tessdata_path = self._get_tessdata_path()
        if not tessdata_path or not tessdata_path.exists():
            return []

        # Find all .traineddata files
        language_files = list(tessdata_path.glob("*.traineddata"))
        languages = [f.stem for f in language_files]
        
        return sorted(languages)
    
    def detect_pgs_tracks(self, video_path: Path) -> List[PGSTrack]:
        """
        Detect PGS subtitle tracks in a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of PGS tracks found
            
        Raises:
            PGSRipNotInstalledError: If PGSRip is not installed
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")
        
        logger.info(f"Detecting PGS tracks in: {video_path.name}")
        
        # Get all subtitle tracks
        all_tracks = VideoContainerHandler.list_subtitle_tracks(video_path)
        
        # Codec-to-track-type mapping for image-based subtitle formats
        codec_type_map = {
            'hdmv_pgs_subtitle': 'pgs', 'pgs': 'pgs', 'sup': 'pgs',
            'dvd_subtitle': 'dvdsub', 'dvb_subtitle': 'dvbsub',
        }

        # Filter for PGS and other image-based subtitle tracks
        pgs_tracks = []
        for track in all_tracks:
            codec_lower = track.codec.lower()
            track_type = codec_type_map.get(codec_lower)
            if track_type:
                pgs_track = PGSTrack(
                    track_id=track.track_id,
                    language=track.language,
                    title=track.title,
                    is_default=track.is_default,
                    is_forced=track.is_forced,
                    ffmpeg_index=track.ffmpeg_index,
                    estimated_language=self._estimate_language(track),
                    track_type=track_type,
                )
                pgs_tracks.append(pgs_track)
        
        logger.info(f"Found {len(pgs_tracks)} PGS tracks")
        return pgs_tracks
    
    def _estimate_language(self, track: SubtitleTrack) -> str:
        """
        Estimate OCR language for a PGS track.
        
        Args:
            track: Subtitle track information
            
        Returns:
            Estimated language code for OCR
        """
        # Language code mapping
        language_mapping = {
            'zh': 'chi_sim',
            'zho': 'chi_sim',
            'chi': 'chi_sim',
            'chs': 'chi_sim',
            'cht': 'chi_tra',
            'zh-cn': 'chi_sim',
            'zh-tw': 'chi_tra',
            'zh-hk': 'chi_tra',
            'en': 'eng',
            'eng': 'eng',
            'english': 'eng',
            'ja': 'jpn',
            'jpn': 'jpn',
            'japanese': 'jpn',
            'ko': 'kor',
            'kor': 'kor',
            'korean': 'kor',
        }
        
        # Check track language
        if track.language:
            lang_lower = track.language.lower()
            if lang_lower in language_mapping:
                return language_mapping[lang_lower]
        
        # Check track title for language hints
        if track.title:
            title_lower = track.title.lower()
            for lang_hint, ocr_lang in language_mapping.items():
                if lang_hint in title_lower:
                    return ocr_lang
        
        # Default to English
        return 'eng'
    
    def convert_pgs_track(self, video_path: Path, track: PGSTrack, 
                         output_path: Path, ocr_language: Optional[str] = None) -> bool:
        """
        Convert a PGS track to SRT format.
        
        Args:
            video_path: Path to the video file
            track: PGS track to convert
            output_path: Output SRT file path
            ocr_language: OCR language to use (auto-detected if None)
            
        Returns:
            True if conversion successful
            
        Raises:
            PGSRipNotInstalledError: If PGSRip is not installed
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")
        
        if ocr_language is None:
            ocr_language = track.estimated_language
        
        logger.info(f"Converting PGS track {track.track_id} to SRT using {ocr_language} OCR")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Extract PGS subtitle to SUP file
                sup_file = temp_path / f"track_{track.track_id}.sup"
                if not self._extract_pgs_to_sup(video_path, track, sup_file):
                    return False
                
                # Convert SUP to SRT using PGSRip
                if not self._convert_sup_to_srt(sup_file, output_path, ocr_language):
                    return False
                
                logger.info(f"✅ Successfully converted PGS track to: {output_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to convert PGS track: {e}")
            return False
    
    def convert_subtitle_file(self, input_path: Path, output_path: Path,
                              language: Optional[str] = None) -> bool:
        """
        Convert a standalone subtitle file (.sup, .idx+.sub) to SRT via OCR.

        Args:
            input_path: Path to .sup, .idx, or .sub file
            output_path: Output SRT file path
            language: OCR language (default: eng)

        Returns:
            True if conversion successful
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")

        ocr_language = language or 'eng'
        ext = input_path.suffix.lower()

        if ext == '.sup':
            # Direct OCR on SUP file
            return self._convert_sup_to_srt(input_path, output_path, ocr_language)
        elif ext in ('.idx', '.sub'):
            # VobSub .idx+.sub pair: convert to .sup via ffmpeg, then OCR
            idx_file = input_path.with_suffix('.idx')
            sub_file = input_path.with_suffix('.sub')
            if not idx_file.exists() or not sub_file.exists():
                logger.error(f"VobSub requires both .idx and .sub files: {input_path}")
                return False

            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                sup_file = Path(temp_dir) / f"{input_path.stem}.sup"
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(idx_file),
                    '-c:s', 'copy',
                    str(sup_file)
                ]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0 or not sup_file.exists():
                        logger.error(f"Failed to convert VobSub to SUP: {result.stderr}")
                        return False
                except FileNotFoundError:
                    logger.error("ffmpeg not found for VobSub conversion")
                    return False

                return self._convert_sup_to_srt(sup_file, output_path, ocr_language)
        else:
            logger.error(f"Unsupported subtitle file format: {ext}")
            return False

    def _extract_pgs_to_sup(self, video_path: Path, track: PGSTrack,
                           output_path: Path) -> bool:
        """Extract PGS track to SUP file, trying ffmpeg first then mkvextract.

        ffmpeg is often faster for large files. No hard timeout is imposed
        since UHD remux files (28GB+) can take a very long time to demux.
        """
        # Determine ffmpeg stream index: subtitle streams are indexed relative
        # to other subtitle streams, so we need the position among subtitle tracks.
        ffmpeg_sub_index = self._get_ffmpeg_subtitle_index(video_path, track.track_id)

        # Try ffmpeg first (often faster for large containers)
        if ffmpeg_sub_index is not None:
            try:
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(video_path),
                    '-map', f'0:s:{ffmpeg_sub_index}',
                    '-c', 'copy',
                    str(output_path)
                ]
                logger.info(f"Extracting PGS track {track.track_id} via ffmpeg (stream s:{ffmpeg_sub_index})...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    logger.info(f"Extracted PGS track via ffmpeg: {output_path} ({output_path.stat().st_size} bytes)")
                    return True
                else:
                    logger.debug(f"ffmpeg extraction failed, falling back to mkvextract: {result.stderr[:200] if result.stderr else 'no output'}")
            except FileNotFoundError:
                logger.debug("ffmpeg not found, falling back to mkvextract")
            except Exception as e:
                logger.debug(f"ffmpeg extraction error: {e}, falling back to mkvextract")

        # Fallback to mkvextract (no timeout - large files need time)
        try:
            cmd = [
                'mkvextract',
                str(video_path),
                'tracks',
                f"{track.track_id}:{output_path}"
            ]
            logger.info(f"Extracting PGS track {track.track_id} via mkvextract...")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and output_path.exists():
                logger.info(f"Extracted PGS track via mkvextract: {output_path}")
                return True
            else:
                logger.error(f"Failed to extract PGS track: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"PGS extraction failed: {e}")
            return False

    def _get_ffmpeg_subtitle_index(self, video_path: Path, mkvextract_track_id: str) -> Optional[int]:
        """Get the ffmpeg subtitle stream index for a given MKV track ID.

        ffmpeg uses relative indices per stream type (s:0, s:1, etc.),
        while MKV uses absolute track IDs. This maps between them.
        """
        try:
            all_tracks = VideoContainerHandler.list_subtitle_tracks(video_path)
            for idx, t in enumerate(all_tracks):
                if t.track_id == str(mkvextract_track_id):
                    return idx
            return None
        except Exception:
            return None
    
    def _convert_sup_to_srt(self, sup_file: Path, srt_file: Path,
                           ocr_language: str) -> bool:
        """Convert SUP file to SRT using PGSRip."""
        try:
            # Import PGSRip (should be available after setup)
            try:
                # Add PGSRip to path dynamically based on install_dir
                pgsrip_path = self.install_dir / "pgsrip"
                if str(pgsrip_path) not in sys.path:
                    sys.path.insert(0, str(pgsrip_path))

                from pgsrip import api
                from pgsrip.options import Options
                from pgsrip.sup import Sup
            except ImportError as e:
                logger.error(f"Failed to import PGSRip: {e}")
                # Fallback to command-line PGSRip
                return self._convert_sup_to_srt_cli(sup_file, srt_file, ocr_language)

            # Configure PGSRip options
            options = Options()
            options.language = ocr_language

            # Set tessdata environment variable (prefer bundled, fallback to install_dir)
            tessdata_path = self._get_tessdata_path() or self.install_dir / "tessdata"
            os.environ['TESSDATA_PREFIX'] = str(tessdata_path)

            # Set output directory
            options.output_dir = str(srt_file.parent)

            # Create SUP media object
            sup_media = Sup(str(sup_file))

            # Run PGSRip conversion
            result = api.rip(sup_media, options)

            # PGSRip API names its output after the input SUP stem
            expected_srt = srt_file.parent / f"{sup_file.stem}.srt"
            if expected_srt.exists() and expected_srt != srt_file:
                expected_srt.rename(srt_file)

            if srt_file.exists():
                logger.debug(f"Converted SUP to SRT: {srt_file}")
                return True
            else:
                logger.error("PGSRip conversion failed - no output file")
                return False

        except Exception as e:
            logger.error(f"SUP to SRT conversion failed: {e}")
            # Fallback to command-line PGSRip if available
            return self._convert_sup_to_srt_cli(sup_file, srt_file, ocr_language)
    
    def _convert_sup_to_srt_cli(self, sup_file: Path, srt_file: Path,
                               ocr_language: str) -> bool:
        """Fallback: Convert SUP to SRT using command-line PGSRip."""
        try:
            # Add PGSRip to Python path dynamically
            pgsrip_packages_path = self.install_dir / "python_packages"

            cmd = [
                sys.executable, '-m', 'pgsrip',
                str(sup_file),
                '--language', ocr_language,
                '--output-dir', str(srt_file.parent)
            ]

            # Set environment for tessdata and Python path
            env = os.environ.copy()
            tessdata_path = self._get_tessdata_path() or self.install_dir / "tessdata"
            env['TESSDATA_PREFIX'] = str(tessdata_path)
            env['PYTHONPATH'] = str(pgsrip_packages_path) + os.pathsep + env.get('PYTHONPATH', '')

            logger.debug(f"Running PGSRip CLI: {' '.join(cmd)}")
            logger.debug(f"TESSDATA_PREFIX: {env['TESSDATA_PREFIX']}")

            result = subprocess.run(cmd, capture_output=True, text=True,
                                  env=env, cwd=str(srt_file.parent))

            logger.debug(f"PGSRip CLI stdout: {result.stdout}")
            if result.stderr:
                logger.debug(f"PGSRip CLI stderr: {result.stderr}")

            # Check for output file (PGSRip creates its own filename)
            expected_srt = srt_file.parent / f"{sup_file.stem}.srt"
            if expected_srt.exists():
                # Rename to desired output name if different
                if expected_srt != srt_file:
                    expected_srt.rename(srt_file)
                logger.debug(f"Converted SUP to SRT via CLI: {srt_file}")
                return True
            elif result.returncode == 0:
                logger.debug(f"PGSRip CLI completed but no output file found")
                return False
            else:
                logger.error(f"CLI PGSRip conversion failed (code {result.returncode}): {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"CLI PGSRip conversion failed: {e}")
            return False

    def batch_convert_pgs(self, video_files: List[Path],
                         output_dir: Optional[Path] = None,
                         ocr_language: Optional[str] = None) -> Dict[str, Any]:
        """
        Batch convert PGS subtitles from multiple video files.

        Args:
            video_files: List of video file paths
            output_dir: Output directory (default: same as video files)
            ocr_language: OCR language to use (auto-detect if None)

        Returns:
            Dictionary with conversion results

        Raises:
            PGSRipNotInstalledError: If PGSRip is not installed
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")

        logger.info(f"Batch converting PGS subtitles from {len(video_files)} videos")

        results = {
            'total_videos': len(video_files),
            'videos_with_pgs': 0,
            'successful_conversions': 0,
            'failed_conversions': 0,
            'converted_files': [],
            'errors': []
        }

        for video_path in video_files:
            try:
                logger.info(f"Processing: {video_path.name}")

                # Detect PGS tracks
                pgs_tracks = self.detect_pgs_tracks(video_path)

                if not pgs_tracks:
                    logger.debug(f"No PGS tracks found in: {video_path.name}")
                    continue

                results['videos_with_pgs'] += 1

                # Convert each PGS track
                for track in pgs_tracks:
                    # Determine output path
                    if output_dir:
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_path = output_dir / f"{video_path.stem}.track_{track.track_id}.srt"
                    else:
                        output_path = video_path.parent / f"{video_path.stem}.track_{track.track_id}.srt"

                    # Use specified language or track's estimated language
                    lang = ocr_language or track.estimated_language

                    success = self.convert_pgs_track(video_path, track, output_path, lang)

                    if success:
                        results['successful_conversions'] += 1
                        results['converted_files'].append(str(output_path))
                        logger.info(f"✅ Converted track {track.track_id}: {output_path.name}")
                    else:
                        results['failed_conversions'] += 1
                        error_msg = f"Failed to convert track {track.track_id} from {video_path.name}"
                        results['errors'].append(error_msg)
                        logger.error(f"✗ {error_msg}")

            except Exception as e:
                results['failed_conversions'] += 1
                error_msg = f"Error processing {video_path.name}: {e}"
                results['errors'].append(error_msg)
                logger.error(f"✗ {error_msg}")

        return results

    def get_pgs_info(self, video_path: Path) -> Dict[str, Any]:
        """
        Get detailed information about PGS tracks in a video.

        Args:
            video_path: Path to the video file

        Returns:
            Dictionary with PGS track information

        Raises:
            PGSRipNotInstalledError: If PGSRip is not installed
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")

        pgs_tracks = self.detect_pgs_tracks(video_path)

        return {
            'video_file': str(video_path),
            'pgs_track_count': len(pgs_tracks),
            'tracks': [
                {
                    'track_id': track.track_id,
                    'language': track.language,
                    'title': track.title,
                    'is_default': track.is_default,
                    'is_forced': track.is_forced,
                    'estimated_ocr_language': track.estimated_language
                }
                for track in pgs_tracks
            ],
            'supported_ocr_languages': self.get_supported_languages()
        }

    def convert_pgs_for_merging(self, video_path: Path,
                               target_language: str = 'chinese') -> Optional[Path]:
        """
        Convert PGS tracks for use in bilingual subtitle merging.

        Args:
            video_path: Path to the video file
            target_language: Target language ('chinese' or 'english')

        Returns:
            Path to converted SRT file or None if no suitable track found

        Raises:
            PGSRipNotInstalledError: If PGSRip is not installed
        """
        if not self.is_installed:
            raise PGSRipNotInstalledError("PGSRip is not installed")

        pgs_tracks = self.detect_pgs_tracks(video_path)

        if not pgs_tracks:
            return None

        # Find best matching track for target language
        target_ocr_languages = {
            'chinese': ['chi_sim', 'chi_tra'],
            'english': ['eng']
        }

        preferred_langs = target_ocr_languages.get(target_language, ['eng'])

        # Find track with matching estimated language
        best_track = None
        for track in pgs_tracks:
            if track.estimated_language in preferred_langs:
                best_track = track
                break

        # If no exact match, use first track
        if not best_track:
            best_track = pgs_tracks[0]
            logger.warning(f"No {target_language} PGS track found, using track {best_track.track_id}")

        # Convert track
        output_path = video_path.parent / f".{video_path.stem}.pgs_{target_language}.srt"

        success = self.convert_pgs_track(
            video_path, best_track, output_path,
            best_track.estimated_language
        )

        return output_path if success else None

    def cleanup_temp_files(self, video_path: Path):
        """
        Clean up temporary PGS conversion files.

        Args:
            video_path: Path to the video file
        """
        # Clean up temporary PGS files
        temp_patterns = [
            f".{video_path.stem}.pgs_*.srt",
            f"{video_path.stem}.track_*.srt"
        ]

        for pattern in temp_patterns:
            for temp_file in video_path.parent.glob(pattern):
                try:
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {temp_file}: {e}")

    def get_conversion_summary(self, results: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of batch conversion results.

        Args:
            results: Results dictionary from batch_convert_pgs

        Returns:
            Formatted summary string
        """
        summary_lines = [
            "PGS Conversion Summary:",
            f"  Total videos processed: {results['total_videos']}",
            f"  Videos with PGS tracks: {results['videos_with_pgs']}",
            f"  Successful conversions: {results['successful_conversions']}",
            f"  Failed conversions: {results['failed_conversions']}"
        ]

        if results['converted_files']:
            summary_lines.append(f"  Output files: {len(results['converted_files'])}")

        if results['errors']:
            summary_lines.append(f"  Errors: {len(results['errors'])}")

        return '\n'.join(summary_lines)


# Convenience functions for easy integration
def is_pgsrip_available() -> bool:
    """Check if PGSRip is available."""
    try:
        wrapper = PGSRipWrapper()
        return wrapper.is_available()
    except Exception:
        return False


def get_pgsrip_wrapper() -> Optional[PGSRipWrapper]:
    """Get PGSRip wrapper instance if available."""
    try:
        wrapper = PGSRipWrapper()
        if wrapper.is_available():
            return wrapper
    except Exception:
        pass
    return None
