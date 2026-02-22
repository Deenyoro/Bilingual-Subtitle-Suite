"""
Encoding conversion processor for subtitle files.

This module provides functionality for converting subtitle file encodings
with special focus on Chinese encodings and Plex compatibility.
"""

import platform
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional
from core.encoding_detection import EncodingDetector
from utils.constants import UTF8_BOM
from utils.logging_config import get_logger
from utils.file_operations import FileHandler

logger = get_logger(__name__)


@dataclass
class ConvertResult:
    """Result of a subtitle file conversion."""
    modified: bool
    encoding_changed: bool = False
    fonts_fixed: List[Tuple[str, str, str]] = field(default_factory=list)  # (style, old_font, new_font)

    def __bool__(self):
        return self.modified


class EncodingConverter:
    """Handles encoding conversion for subtitle files with Chinese support."""

    _font_cache: dict = {}

    def __init__(self):
        """Initialize the encoding converter."""
        self.detector = EncodingDetector()

    @staticmethod
    def _is_font_available(font_name: str) -> bool:
        """Check if a font is available on the system.

        Uses GDI on Windows and fc-list on Linux/Mac. Results are cached.
        """
        if font_name in EncodingConverter._font_cache:
            return EncodingConverter._font_cache[font_name]

        available = False
        system = platform.system()

        if system == 'Windows':
            try:
                import ctypes
                from ctypes import wintypes

                gdi32 = ctypes.windll.gdi32
                user32 = ctypes.windll.user32

                # Get a device context for the desktop
                hdc = user32.GetDC(0)
                if not hdc:
                    EncodingConverter._font_cache[font_name] = False
                    return False

                try:
                    # Create a font with the requested name
                    hfont = gdi32.CreateFontW(
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                        font_name
                    )
                    if not hfont:
                        EncodingConverter._font_cache[font_name] = False
                        return False

                    try:
                        # Select the font into the DC and read back the actual face name
                        old_font = gdi32.SelectObject(hdc, hfont)
                        buf = ctypes.create_unicode_buffer(64)
                        gdi32.GetTextFaceW(hdc, 64, buf)
                        actual_name = buf.value
                        gdi32.SelectObject(hdc, old_font)

                        # If the actual name matches the requested name, the font exists
                        available = actual_name.lower() == font_name.lower()
                    finally:
                        gdi32.DeleteObject(hfont)
                finally:
                    user32.ReleaseDC(0, hdc)
            except Exception:
                available = False
        else:
            # Linux/Mac: use fc-list
            try:
                result = subprocess.run(
                    ['fc-list', ':family', '-f', '%{family}\n'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    families = result.stdout.strip().split('\n')
                    lower_name = font_name.lower()
                    for family in families:
                        # fc-list may return comma-separated aliases
                        for alias in family.split(','):
                            if alias.strip().lower() == lower_name:
                                available = True
                                break
                        if available:
                            break
            except (subprocess.SubprocessError, FileNotFoundError):
                available = False

        EncodingConverter._font_cache[font_name] = available
        return available

    @staticmethod
    def _has_cjk_characters(text: str) -> bool:
        """Check if text contains CJK characters."""
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or    # CJK Unified Ideographs
                0x3400 <= cp <= 0x4DBF or    # CJK Extension A
                0x3000 <= cp <= 0x303F or    # CJK Symbols and Punctuation
                0x3040 <= cp <= 0x309F or    # Hiragana
                0x30A0 <= cp <= 0x30FF or    # Katakana
                0xAC00 <= cp <= 0xD7AF):     # Hangul Syllables
                return True
        return False

    def _fix_ass_fonts(self, text: str, file_path: Path) -> Tuple[str, List[Tuple[str, str, str]]]:
        """Fix missing fonts in ASS/SSA subtitle files.

        Parses the [V4+ Styles] or [V4 Styles] section, checks each font
        for availability, and replaces missing fonts with system defaults.
        Also fixes Encoding field 134 (GBK) -> 1 (Unicode).

        Returns:
            (modified_text, replacements) where replacements is a list of
            (style_name, old_font, new_font) tuples.
        """
        replacements = []
        lines = text.split('\n')
        in_styles = False
        format_fields = None
        fontname_idx = None
        encoding_idx = None
        has_cjk = self._has_cjk_characters(text)
        new_lines = []

        for line in lines:
            stripped = line.strip()

            # Detect styles section
            if stripped.lower() in ('[v4+ styles]', '[v4 styles]'):
                in_styles = True
                new_lines.append(line)
                continue
            elif stripped.startswith('[') and stripped.endswith(']'):
                in_styles = False
                format_fields = None
                new_lines.append(line)
                continue

            if in_styles:
                if stripped.lower().startswith('format:'):
                    # Parse the Format line to find field indices
                    fields = [f.strip().lower() for f in stripped.split(':', 1)[1].split(',')]
                    fontname_idx = fields.index('fontname') if 'fontname' in fields else None
                    encoding_idx = fields.index('encoding') if 'encoding' in fields else None
                    format_fields = fields
                    new_lines.append(line)
                    continue

                if stripped.lower().startswith('style:') and format_fields is not None and fontname_idx is not None:
                    # Parse the Style line
                    prefix, values_str = line.split(':', 1)
                    values = [v.strip() for v in values_str.split(',')]

                    # Get style name (field 0 = Name)
                    style_name = values[0].strip() if values else 'unknown'

                    # Check and fix font
                    if fontname_idx < len(values):
                        old_font = values[fontname_idx].strip()
                        if old_font and not self._is_font_available(old_font):
                            new_font = 'Microsoft YaHei' if has_cjk else 'Arial'
                            values[fontname_idx] = new_font
                            replacements.append((style_name, old_font, new_font))
                            logger.info(f"Font replacement: [{style_name}] '{old_font}' -> '{new_font}'")

                    # Fix Encoding field: 134 (GBK) -> 1 (Unicode)
                    if encoding_idx is not None and encoding_idx < len(values):
                        if values[encoding_idx].strip() == '134':
                            values[encoding_idx] = '1'
                            logger.debug(f"Fixed encoding field 134->1 for style [{style_name}]")

                    line = prefix + ': ' + ', '.join(values)

            new_lines.append(line)

        return '\n'.join(new_lines), replacements
    
    def convert_file(self, file_path: Path, keep_backup: bool = False,
                    force_conversion: bool = False, target_encoding: str = 'utf-8',
                    fix_fonts: bool = True) -> ConvertResult:
        """
        Convert a single subtitle file to the target encoding without BOM.

        Args:
            file_path: Path to the subtitle file
            keep_backup: Whether to keep a backup of the original file
            force_conversion: Force conversion even if file appears to be target encoding
            target_encoding: Target encoding (default: utf-8)
            fix_fonts: Whether to fix missing fonts in ASS/SSA files (default: True)

        Returns:
            ConvertResult with modified status and details

        Example:
            >>> converter = EncodingConverter()
            >>> result = converter.convert_file(Path("subtitle.srt"))
            >>> print(f"File modified: {result.modified}")
        """
        try:
            raw_data = file_path.read_bytes()
            logger.debug(f"Processing {file_path.name} ({len(raw_data)} bytes)")

            encoding_changed = False

            # Check for UTF-8 BOM
            has_bom = raw_data.startswith(UTF8_BOM)
            if has_bom:
                logger.debug("UTF-8 BOM detected, will be removed")
                text = raw_data[len(UTF8_BOM):].decode("utf-8", "strict")
                encoding_changed = True
            else:
                # Try to decode as target encoding first
                try:
                    text = raw_data.decode(target_encoding, "strict")
                    if not force_conversion:
                        # Validate the content even if it's already target encoding
                        is_valid, format_type = self._validate_subtitle_format(text, file_path)
                        if is_valid:
                            # Even if encoding is fine, we may still need to fix fonts
                            ext = file_path.suffix.lower()
                            if fix_fonts and ext in ('.ass', '.ssa'):
                                text_fixed, font_replacements = self._fix_ass_fonts(text, file_path)
                                if font_replacements:
                                    if keep_backup:
                                        FileHandler.create_backup(file_path)
                                    FileHandler.safe_write(file_path, text_fixed, target_encoding, create_backup=False)
                                    logger.debug(f"Fixed fonts in {target_encoding} file: {file_path}")
                                    return ConvertResult(modified=True, encoding_changed=False, fonts_fixed=font_replacements)
                            logger.debug(f"File is already valid {target_encoding}, no conversion needed")
                            return ConvertResult(modified=False)
                        else:
                            logger.info(f"File is {target_encoding} but has format issues, will normalize")
                    else:
                        logger.debug(f"Force conversion enabled, will process {target_encoding} file")
                except UnicodeDecodeError:
                    # Not target encoding, need to detect encoding
                    logger.debug(f"File is not {target_encoding}, detecting encoding")
                    detected_encoding = self.detector.detect_encoding(file_path)
                    if not detected_encoding:
                        # Last resort fallback
                        detected_encoding = "gb18030"
                        logger.warning(f"Could not detect encoding, using fallback: {detected_encoding}")

                    try:
                        text = raw_data.decode(detected_encoding, "strict")
                        logger.info(f"Successfully decoded using {detected_encoding}")
                        encoding_changed = True
                    except UnicodeDecodeError as e:
                        logger.error(f"Failed to decode {file_path} with {detected_encoding}: {e}")
                        return ConvertResult(modified=False)

            # Normalize line endings
            text = self._normalize_line_endings(text)

            # Fix fonts in ASS/SSA files
            font_replacements = []
            ext = file_path.suffix.lower()
            if fix_fonts and ext in ('.ass', '.ssa'):
                text, font_replacements = self._fix_ass_fonts(text, file_path)

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

            return ConvertResult(modified=True, encoding_changed=encoding_changed, fonts_fixed=font_replacements)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return ConvertResult(modified=False)
    
    def convert_directory(self, directory: Path, recursive: bool = True,
                         keep_backup: bool = False, force_conversion: bool = False,
                         target_encoding: str = 'utf-8',
                         fix_fonts: bool = True) -> Tuple[int, int, int]:
        """
        Convert all subtitle files in a directory.

        Args:
            directory: Directory to process
            recursive: Whether to process subdirectories
            keep_backup: Whether to keep backup files
            force_conversion: Force conversion even if files appear to be target encoding
            target_encoding: Target encoding
            fix_fonts: Whether to fix missing fonts in ASS/SSA files

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
                result = self.convert_file(file_path, keep_backup, force_conversion,
                                          target_encoding, fix_fonts)
                if result.modified:
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
                     force_conversion: bool = False, target_encoding: str = 'utf-8',
                     fix_fonts: bool = True) -> Tuple[int, int, int]:
        """
        Convert a batch of subtitle files.

        Args:
            file_paths: List of file paths to convert
            keep_backup: Whether to keep backup files
            force_conversion: Force conversion even if files appear to be target encoding
            target_encoding: Target encoding
            fix_fonts: Whether to fix missing fonts in ASS/SSA files

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
                result = self.convert_file(file_path, keep_backup, force_conversion,
                                          target_encoding, fix_fonts)
                if result.modified:
                    logger.info(f"✓ {file_path.name}")
                    converted += 1
                else:
                    logger.debug(f"- {file_path.name} (no changes needed)")
                    unchanged += 1
            except Exception as e:
                logger.error(f"✗ {file_path.name} → {e}")
                errors += 1

        return converted, unchanged, errors
