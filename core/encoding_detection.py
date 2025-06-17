"""
Encoding detection utilities for subtitle files.

This module provides comprehensive encoding detection with special focus on
Chinese encodings and automatic fallback mechanisms.
"""

from pathlib import Path
from typing import Optional, Tuple
from utils.constants import ENCODING_PRIORITY, CHINESE_ENCODINGS, UTF8_BOM
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Try to import charset detection libraries
CHARSET_NORMALIZER_AVAILABLE = False
CHARDET_AVAILABLE = False

try:
    from charset_normalizer import from_path as detect_charset_normalizer
    CHARSET_NORMALIZER_AVAILABLE = True
except ImportError:
    try:
        from chardet.universaldetector import UniversalDetector
        CHARDET_AVAILABLE = True
    except ImportError:
        pass


class EncodingDetector:
    """Handles encoding detection for subtitle files with Chinese support."""
    
    @staticmethod
    def detect_encoding(file_path: Path) -> Optional[str]:
        """
        Detect the encoding of a text file using multiple methods.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            Detected encoding name or None if detection failed
            
        Example:
            >>> encoding = EncodingDetector.detect_encoding(Path("subtitle.srt"))
            >>> print(f"Detected encoding: {encoding}")
        """
        # First try automatic detection if available
        detected = EncodingDetector._auto_detect_encoding(file_path)
        if detected:
            logger.debug(f"Auto-detected encoding for {file_path.name}: {detected}")
            return detected.lower()
        
        # Fallback to manual detection
        logger.debug(f"Auto-detection failed for {file_path.name}, trying manual detection")
        return EncodingDetector._manual_detect_encoding(file_path)
    
    @staticmethod
    def _auto_detect_encoding(file_path: Path) -> Optional[str]:
        """
        Use automatic encoding detection libraries.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detected encoding or None
        """
        if CHARSET_NORMALIZER_AVAILABLE:
            try:
                result = detect_charset_normalizer(file_path)
                if result and result.best():
                    return result.best().encoding
            except Exception as e:
                logger.debug(f"charset-normalizer detection failed: {e}")
        
        if CHARDET_AVAILABLE:
            try:
                detector = UniversalDetector()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        detector.feed(chunk)
                        if detector.done:
                            break
                detector.close()
                result = detector.result
                if result and result["encoding"] and result["confidence"] > 0.7:
                    return result["encoding"]
            except Exception as e:
                logger.debug(f"chardet detection failed: {e}")
        
        return None
    
    @staticmethod
    def _manual_detect_encoding(file_path: Path) -> Optional[str]:
        """
        Manually detect encoding by trying different encodings with BOM priority.

        Args:
            file_path: Path to the file

        Returns:
            Detected encoding or None
        """
        # CRITICAL FIX: Check for BOM first and prioritize utf-8-sig
        if EncodingDetector.has_bom(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    f.read()
                logger.debug(f"Manual detection successful for {file_path.name}: utf-8-sig (BOM detected)")
                return 'utf-8-sig'
            except UnicodeDecodeError:
                logger.warning(f"BOM detected but utf-8-sig failed for {file_path.name}")

        # Try UTF-8 variants
        utf_encodings = ['utf-8', 'utf-8-sig']
        for encoding in utf_encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read()
                logger.debug(f"Manual detection successful for {file_path.name}: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
        
        # Try Chinese encodings
        for encoding in CHINESE_ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    # Basic validation - check if we have reasonable Chinese content
                    if EncodingDetector._has_chinese_characters(content):
                        logger.debug(f"Manual detection successful for {file_path.name}: {encoding}")
                        return encoding
            except (UnicodeDecodeError, LookupError):
                continue
        
        # Try remaining encodings from priority list
        remaining_encodings = [enc for enc in ENCODING_PRIORITY 
                             if enc not in utf_encodings and enc not in CHINESE_ENCODINGS]
        
        for encoding in remaining_encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read()
                logger.debug(f"Manual detection successful for {file_path.name}: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
        
        logger.warning(f"Could not detect encoding for {file_path}")
        return None
    
    @staticmethod
    def _has_chinese_characters(text: str) -> bool:
        """
        Check if text contains Chinese characters.
        
        Args:
            text: Text to analyze
            
        Returns:
            True if Chinese characters are found
        """
        # Unicode ranges for Chinese characters
        chinese_ranges = [
            (0x4E00, 0x9FFF),   # CJK Unified Ideographs
            (0x3400, 0x4DBF),   # CJK Extension A
            (0x20000, 0x2A6DF), # CJK Extension B
            (0x2A700, 0x2B73F), # CJK Extension C
            (0x2B740, 0x2B81F), # CJK Extension D
            (0x2B820, 0x2CEAF), # CJK Extension E
            (0x3000, 0x303F),   # CJK Symbols and Punctuation
            (0xFF00, 0xFFEF),   # Halfwidth and Fullwidth Forms
        ]
        
        for char in text:
            char_code = ord(char)
            for start, end in chinese_ranges:
                if start <= char_code <= end:
                    return True
        return False
    
    @staticmethod
    def read_file_with_encoding(file_path: Path) -> Tuple[str, str]:
        """
        Read a file with automatic encoding detection and proper BOM handling.

        Args:
            file_path: Path to the file to read

        Returns:
            Tuple of (file_content, encoding_used)

        Raises:
            IOError: If file cannot be read with any encoding

        Example:
            >>> content, encoding = EncodingDetector.read_file_with_encoding(Path("subtitle.srt"))
            >>> print(f"Read file with {encoding} encoding")
        """
        # CRITICAL FIX: Check for UTF-8 BOM first to prevent parsing issues
        if EncodingDetector.has_bom(file_path):
            logger.debug(f"UTF-8 BOM detected in {file_path.name}, using utf-8-sig encoding")
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                return content, 'utf-8-sig'
            except Exception as e:
                logger.warning(f"Failed to read BOM file with utf-8-sig: {e}, falling back to detection")

        # Standard encoding detection for files without BOM
        encoding = EncodingDetector.detect_encoding(file_path)

        if not encoding:
            # Last resort - try with errors='replace'
            encoding = 'utf-8'
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()
                logger.warning(f"Failed to detect encoding for {file_path}, using UTF-8 with error replacement")
                return content, encoding
            except Exception as e:
                raise IOError(f"Cannot read file {file_path}: {e}")

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except Exception as e:
            raise IOError(f"Cannot read file {file_path} with encoding {encoding}: {e}")
    
    @staticmethod
    def has_bom(file_path: Path) -> bool:
        """
        Check if file has UTF-8 BOM.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file has UTF-8 BOM
            
        Example:
            >>> has_bom = EncodingDetector.has_bom(Path("subtitle.srt"))
            >>> print(f"File has BOM: {has_bom}")
        """
        try:
            with open(file_path, 'rb') as f:
                return f.read(len(UTF8_BOM)) == UTF8_BOM
        except Exception:
            return False
    
    @staticmethod
    def get_detection_info() -> dict:
        """
        Get information about available encoding detection libraries.
        
        Returns:
            Dictionary with detection library availability
            
        Example:
            >>> info = EncodingDetector.get_detection_info()
            >>> print(f"charset-normalizer available: {info['charset_normalizer']}")
        """
        return {
            'charset_normalizer': CHARSET_NORMALIZER_AVAILABLE,
            'chardet': CHARDET_AVAILABLE,
            'manual_fallback': True
        }
