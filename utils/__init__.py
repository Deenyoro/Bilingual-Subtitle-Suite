"""
Utility modules.

This package contains shared utility functions and configurations:
- File I/O operations and backup utilities
- Logging configuration
- Shared constants and configurations
"""

from .file_operations import FileHandler
from .logging_config import setup_logging
from .constants import (
    SubtitleFormat,
    VIDEO_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    CHINESE_CODES,
    ENGLISH_CODES,
    CHINESE_PATTERNS,
    ENGLISH_PATTERNS,
    ENCODING_PRIORITY,
    CHINESE_ENCODINGS,
    UTF8_BOM,
    DEFAULT_GAP_THRESHOLD,
    DEFAULT_FFMPEG_TIMEOUT,
    FORCED_SUBTITLE_THRESHOLD,
    FFMPEG_CODEC_MAP,
    DEFAULT_OUTPUT_FORMAT,
    BACKUP_DIR_NAME,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_DATE_FORMAT,
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
)

__all__ = [
    'FileHandler',
    'setup_logging',
    'SubtitleFormat',
    'VIDEO_EXTENSIONS',
    'SUBTITLE_EXTENSIONS',
    'CHINESE_CODES',
    'ENGLISH_CODES',
    'CHINESE_PATTERNS',
    'ENGLISH_PATTERNS',
    'ENCODING_PRIORITY',
    'CHINESE_ENCODINGS',
    'UTF8_BOM',
    'DEFAULT_GAP_THRESHOLD',
    'DEFAULT_FFMPEG_TIMEOUT',
    'FORCED_SUBTITLE_THRESHOLD',
    'FFMPEG_CODEC_MAP',
    'DEFAULT_OUTPUT_FORMAT',
    'BACKUP_DIR_NAME',
    'DEFAULT_LOG_FORMAT',
    'DEFAULT_LOG_DATE_FORMAT',
    'APP_NAME',
    'APP_VERSION',
    'APP_DESCRIPTION',
]
