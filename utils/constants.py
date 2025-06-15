"""
Shared constants and configurations for the subtitle processing application.

This module contains all the constants used across different modules including:
- Supported file formats and extensions
- Language code mappings
- Encoding detection priorities
- Default configuration values
"""

from enum import Enum
from typing import Set, List, Dict

# ============================================================================
# FILE FORMAT CONSTANTS
# ============================================================================

class SubtitleFormat(Enum):
    """Supported subtitle formats."""
    SRT = "srt"
    ASS = "ass"
    SSA = "ssa"
    VTT = "vtt"
    
    @classmethod
    def from_extension(cls, ext: str) -> 'SubtitleFormat':
        """
        Get format from file extension.
        
        Args:
            ext: File extension (with or without dot)
            
        Returns:
            SubtitleFormat enum value
            
        Raises:
            ValueError: If extension is not supported
        """
        ext = ext.lower().lstrip('.')
        for format_type in cls:
            if format_type.value == ext:
                return format_type
        raise ValueError(f"Unsupported subtitle format: {ext}")

# Supported video container formats
VIDEO_EXTENSIONS: Set[str] = {
    '.mkv', '.mp4', '.m4v', '.mov', '.avi', '.flv', 
    '.ts', '.webm', '.mpg', '.mpeg'
}

# Supported subtitle file extensions
SUBTITLE_EXTENSIONS: Set[str] = {'.srt', '.ass', '.ssa', '.vtt'}

# ============================================================================
# LANGUAGE DETECTION CONSTANTS
# ============================================================================

# Language code mappings for detection
CHINESE_CODES: Set[str] = {
    'chi', 'zho', 'chs', 'cht', 'zh', 'chinese', 'cn', 
    'cmn', 'yue', 'hak', 'nan'
}

ENGLISH_CODES: Set[str] = {
    'eng', 'en', 'english', 'enm', 'ang'
}

# Language detection patterns for external subtitle files
CHINESE_PATTERNS: List[str] = [
    '.zh', '.chi', '.chs', '.cht', '.cn', '.chinese',
    '_zh', '_chi', '_chs', '_cht', '_cn', '_chinese'
]

ENGLISH_PATTERNS: List[str] = [
    '.en', '.eng', '.english',
    '_en', '_eng', '_english'
]

# ============================================================================
# ENCODING DETECTION CONSTANTS
# ============================================================================

# Subtitle file encoding detection order (most likely first)
ENCODING_PRIORITY: List[str] = [
    'utf-8-sig', 'utf-8', 'utf-16', 'latin-1', 'cp1252', 
    'gbk', 'gb18030', 'big5', 'shift-jis'
]

# Extended list of Chinese encodings to try
CHINESE_ENCODINGS: List[str] = [
    'gb18030',    # Comprehensive Chinese encoding (superset of GB2312 and GBK)
    'gbk',        # Simplified Chinese (Windows)
    'gb2312',     # Simplified Chinese (older standard)
    'big5',       # Traditional Chinese
    'big5-hkscs', # Hong Kong variant of Big5
    'cp950',      # Windows Traditional Chinese
    'hz-gb-2312', # HZ encoding
]

# UTF-8 BOM marker
UTF8_BOM: bytes = b"\xef\xbb\xbf"

# ============================================================================
# TIMING AND PROCESSING CONSTANTS
# ============================================================================

# Default gap threshold for subtitle timing optimization (seconds)
DEFAULT_GAP_THRESHOLD: float = 0.1

# Default timeout for FFmpeg operations (seconds)
DEFAULT_FFMPEG_TIMEOUT: int = 900  # 15 minutes

# Default forced subtitle detection threshold
FORCED_SUBTITLE_THRESHOLD: float = 0.1

# ============================================================================
# FFMPEG CONSTANTS
# ============================================================================

# FFmpeg codec name mappings
FFMPEG_CODEC_MAP: Dict[str, str] = {
    '.srt': 'srt',
    '.ass': 'ass',
    '.ssa': 'ssa',
    '.vtt': 'webvtt'
}

# ============================================================================
# DEFAULT CONFIGURATION VALUES
# ============================================================================

# Default output format for merged subtitles
DEFAULT_OUTPUT_FORMAT: str = "srt"

# Default backup directory name
BACKUP_DIR_NAME: str = "subtitle_backups"

# Default log format
DEFAULT_LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'

# Application metadata
APP_NAME: str = "Bilingual Subtitle Suite"
APP_VERSION: str = "2.0.0"
APP_DESCRIPTION: str = """
A comprehensive tool for processing subtitle files with support for:
- Bilingual subtitle merging (Chinese-English, Japanese-English, Korean-English, etc.)
- Encoding conversion and detection
- Subtitle realignment and timing adjustment
- Video container subtitle extraction
- Batch processing operations
"""
