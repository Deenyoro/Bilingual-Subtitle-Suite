"""
Core subtitle processing modules.

This package contains the fundamental components for subtitle processing:
- Subtitle format handlers (SRT, ASS, VTT)
- Video container operations with FFmpeg
- Encoding and language detection utilities
- Timing manipulation functions
"""

from .subtitle_formats import SubtitleFormat, SubtitleEvent, SubtitleTrack, SubtitleFile, SubtitleFormatFactory
from .video_containers import VideoContainerHandler
from .encoding_detection import EncodingDetector
from .language_detection import LanguageDetector
from .timing_utils import TimeConverter
from .similarity_alignment import MultiAnchorAligner, ProperNounExtractor, AnchorPair

__all__ = [
    'SubtitleFormat',
    'SubtitleEvent',
    'SubtitleTrack',
    'SubtitleFile',
    'SubtitleFormatFactory',
    'VideoContainerHandler',
    'EncodingDetector',
    'LanguageDetector',
    'TimeConverter',
    'MultiAnchorAligner',
    'ProperNounExtractor',
    'AnchorPair',
]
