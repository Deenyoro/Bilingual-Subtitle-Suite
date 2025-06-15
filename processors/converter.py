"""
Encoding conversion processor for subtitle files.

This module provides functionality for converting subtitle file encodings
with special focus on Chinese encodings and Plex compatibility.
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from core.encoding_detection import EncodingDetector
from utils.constants import UTF8_BOM
from utils.logging_config import get_logger
from utils.file_operations import FileHandler

logger = get_logger(__name__)


class EncodingConverter:
    """Handles encoding conversion for subtitle files with Chinese support."""
    
    def __init__(self):
        """Initialize the encoding converter."""
        self.detector = EncodingDetector()
    
    def convert_file(self, file_path: Path, keep_backup: bool = False, 
                    force_conversion: bool = False, target_encoding: str = 'utf-8') -> bool:
        """
        Convert a single subtitle file to the target encoding without BOM.
        
        Args:
            file_path: Path to the subtitle file
            keep_backup: Whether to keep a backup of the original file
            force_conversion: Force conversion even if file appears to be target encoding
            target_encoding: Target encoding (default: utf-8)
            
        Returns:
            True if the file was modified, False otherwise
            
        Example:
            >>> converter = EncodingConverter()
            >>> modified = converter.convert_file(Path("subtitle.srt"))
            >>> print(f"File modified: {modified}")
        """
        try:
            raw_data = file_path.read_bytes()
            logger.debug(f"Processing {file_path.name} ({len(raw_data)} bytes)")

            # Check for UTF-8 BOM
            has_bom = raw_data.startswith(UTF8_BOM)
            if has_bom:
                logger.debug("UTF-8 BOM detected, will be removed")
                text = raw_data[len(UTF8_BOM):].decode("utf-8", "strict")
            else:
                # Try to decode as target encoding first
                try:
                    text = raw_data.decode(target_encoding, "strict")
                    if not force_conversion:
                        # Validate the content even if it's already target encoding
                        is_valid, format_type = self._validate_subtitle_format(text, file_path)
                        if is_valid:
                            logger.debug(f"File is already valid {target_encoding}, no conversion needed")
                            return False
                        else:
                            logger.info(f"File is {target_encoding} but has format issues, will normalize")
                    else:
                        logger.debug(f"Force conversion enabled, will process {target_encoding} file")
                except UnicodeDecodeError:
                    # Not target encoding, need to detect encoding
                    logger.debug(f"File is not {target_encoding}, detecting encoding")
                    encoding = self.detector.detect_encoding(file_path)
                    if not encoding:
                        # Last resort fallback
                        encoding = "gb18030"
                        logger.warning(f"Could not detect encoding, using fallback: {encoding}")

                    try:
                        text = raw_data.decode(encoding, "strict")
                        logger.info(f"Successfully decoded using {encoding}")
                    except UnicodeDecodeError as e:
                        logger.error(f"Failed to decode {file_path} with {encoding}: {e}")
                        return False

            # Normalize line endings
            text = self._normalize_line_endings(text)

            # Validate subtitle format
            is_valid, format_type = self._validate_subtitle_format(text, file_path)
            if not is_valid:
                logger.warning(f"Subtitle format validation failed for {file_path}")

            # Create backup if requested
            if keep_backup:
                FileHandler.create_backup(file_path)

            # Write the converted file
            FileHandler.safe_write(file_path, text, target_encoding, create_backup=False)
            logger.debug(f"Successfully wrote {target_encoding} file: {file_path}")

            return True

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False
    
    def convert_directory(self, directory: Path, recursive: bool = True,
                         keep_backup: bool = False, force_conversion: bool = False,
                         target_encoding: str = 'utf-8') -> Tuple[int, int, int]:
        """
        Convert all subtitle files in a directory.
        
        Args:
            directory: Directory to process
            recursive: Whether to process subdirectories
            keep_backup: Whether to keep backup files
            force_conversion: Force conversion even if files appear to be target encoding
            target_encoding: Target encoding
            
        Returns:
            Tuple of (converted_count, unchanged_count, error_count)
            
        Example:
            >>> converter = EncodingConverter()
            >>> converted, unchanged, errors = converter.convert_directory(Path("/media"))
            >>> print(f"Converted: {converted}, Unchanged: {unchanged}, Errors: {errors}")
        """
        logger.info(f"Scanning directory: {directory}")
        
        # Find all subtitle files
        subtitle_files = FileHandler.find_subtitle_files(directory, recursive)
        
        if not subtitle_files:
            logger.warning(f"No subtitle files found in {directory}")
            return 0, 0, 0
        
        logger.info(f"Found {len(subtitle_files)} subtitle files to process")
        
        converted = unchanged = errors = 0
        
        # Process each file
        for i, file_path in enumerate(subtitle_files, 1):
            logger.debug(f"Processing {i}/{len(subtitle_files)}: {file_path.name}")
            
            try:
                if self.convert_file(file_path, keep_backup, force_conversion, target_encoding):
                    logger.info(f"✓ {file_path.name}")
                    converted += 1
                else:
                    logger.debug(f"- {file_path.name} (no changes needed)")
                    unchanged += 1
            except Exception as e:
                logger.error(f"✗ {file_path.name} → {e}")
                errors += 1
        
        return converted, unchanged, errors
    
    def _normalize_line_endings(self, text: str) -> str:
        """
        Normalize line endings to Unix-style (LF only) for better Plex compatibility.
        
        Args:
            text: Text to normalize
            
        Returns:
            Text with normalized line endings
        """
        # Replace Windows (CRLF) and old Mac (CR) line endings with Unix (LF)
        return text.replace('\r\n', '\n').replace('\r', '\n')
    
    def _validate_subtitle_format(self, content: str, file_path: Path) -> Tuple[bool, str]:
        """
        Validate subtitle file format for Plex compatibility.
        
        Args:
            content: File content as string
            file_path: Path to the file for format detection
            
        Returns:
            Tuple of (is_valid, format_type)
        """
        ext = file_path.suffix.lower()

        if ext == '.srt':
            # Basic SRT validation
            srt_pattern = r'^\d+\s*\n\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*\n'
            if re.search(srt_pattern, content, re.MULTILINE):
                return True, 'srt'
            else:
                logger.warning(f"Invalid SRT format detected in {file_path}")
                return False, 'srt'

        elif ext in ['.ass', '.ssa']:
            # Basic ASS/SSA validation
            if '[Script Info]' in content and '[Events]' in content:
                return True, 'ass'
            else:
                logger.warning(f"Invalid ASS/SSA format detected in {file_path}")
                return False, 'ass'

        # Unknown format, assume valid
        return True, 'unknown'
    
    def get_detection_info(self) -> dict:
        """
        Get information about available encoding detection libraries.
        
        Returns:
            Dictionary with detection library availability
            
        Example:
            >>> converter = EncodingConverter()
            >>> info = converter.get_detection_info()
            >>> print(f"Detection info: {info}")
        """
        return self.detector.get_detection_info()
    
    def batch_convert(self, file_paths: List[Path], keep_backup: bool = False,
                     force_conversion: bool = False, target_encoding: str = 'utf-8') -> Tuple[int, int, int]:
        """
        Convert a batch of subtitle files.
        
        Args:
            file_paths: List of file paths to convert
            keep_backup: Whether to keep backup files
            force_conversion: Force conversion even if files appear to be target encoding
            target_encoding: Target encoding
            
        Returns:
            Tuple of (converted_count, unchanged_count, error_count)
            
        Example:
            >>> converter = EncodingConverter()
            >>> files = [Path("sub1.srt"), Path("sub2.srt")]
            >>> converted, unchanged, errors = converter.batch_convert(files)
        """
        logger.info(f"Processing {len(file_paths)} files")
        
        converted = unchanged = errors = 0
        
        for i, file_path in enumerate(file_paths, 1):
            logger.debug(f"Processing {i}/{len(file_paths)}: {file_path.name}")
            
            try:
                if self.convert_file(file_path, keep_backup, force_conversion, target_encoding):
                    logger.info(f"✓ {file_path.name}")
                    converted += 1
                else:
                    logger.debug(f"- {file_path.name} (no changes needed)")
                    unchanged += 1
            except Exception as e:
                logger.error(f"✗ {file_path.name} → {e}")
                errors += 1
        
        return converted, unchanged, errors
