#!/usr/bin/env python3
"""
convert_ch_subs.py  –  Batch‑convert .srt and .ass/.ssa subtitles to UTF‑8 (no BOM)
for maximum Plex compatibility.

Enhanced version with improved Chinese encoding detection, better error handling,
and comprehensive subtitle format validation for optimal Plex compatibility.

usage:
    python convert_ch_subs.py /path/to/plex/library
    python convert_ch_subs.py /media -b          # keep .bak backup copies
    python convert_ch_subs.py /media -f          # force conversion even if UTF-8
    python convert_ch_subs.py /media -v          # verbose output for debugging
"""
from pathlib import Path
import argparse, sys, shutil, os, re
import logging
from typing import Optional, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Extended list of Chinese encodings to try
CHINESE_ENCODINGS = [
    'gb18030',    # Comprehensive Chinese encoding (superset of GB2312 and GBK)
    'gbk',        # Simplified Chinese (Windows)
    'gb2312',     # Simplified Chinese (older standard)
    'big5',       # Traditional Chinese
    'big5-hkscs', # Hong Kong variant of Big5
    'cp950',      # Windows Traditional Chinese
    'hz-gb-2312', # HZ encoding
]

# Choose the best detector available
CHARSET_NORMALIZER_AVAILABLE = False
CHARDET_AVAILABLE = False

try:
    from charset_normalizer import from_path as detect  # pip install charset-normalizer
    CHARSET_NORMALIZER_AVAILABLE = True
    def sniff(p):
        try:
            # Limit the amount of data read for large files to avoid hanging
            result = detect(p)
            if result and result.best():
                return result.best().encoding
        except Exception as e:
            logger.debug(f"charset_normalizer detection failed: {e}")
        return None
except ImportError:                                     # fallback to chardet
    try:
        from chardet.universaldetector import UniversalDetector  # pip install chardet
        CHARDET_AVAILABLE = True
        def sniff(p):
            ud = UniversalDetector()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(4096), b""):
                    ud.feed(chunk)
                    if ud.done:
                        break
            ud.close()
            result = ud.result
            return result["encoding"] if result and result["encoding"] else None
    except ImportError:
        def sniff(p):
            return None

UTF8_BOM = b"\xef\xbb\xbf"

def detect_encoding_comprehensive(file_path: Path) -> Optional[str]:
    """
    Comprehensive encoding detection with special focus on Chinese encodings.

    Args:
        file_path: Path to the file to analyze

    Returns:
        Detected encoding or None if detection failed
    """
    # First try automatic detection if available
    detected = sniff(file_path)
    if detected:
        logger.debug(f"Auto-detected encoding: {detected}")
        return detected.lower()

    # Manual detection by trying encodings in order
    logger.debug("Auto-detection failed, trying manual detection")

    # Try UTF-8 variants first
    utf_encodings = ['utf-8', 'utf-8-sig']
    for encoding in utf_encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            logger.debug(f"Manual detection successful: {encoding}")
            return encoding
        except UnicodeDecodeError:
            continue

    # Try Chinese encodings
    for encoding in CHINESE_ENCODINGS:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                # Basic validation - check if we have reasonable Chinese content
                if has_chinese_characters(content):
                    logger.debug(f"Manual detection successful: {encoding}")
                    return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    # Try common Western encodings as last resort
    western_encodings = ['latin-1', 'cp1252', 'iso-8859-1']
    for encoding in western_encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            logger.debug(f"Manual detection successful: {encoding}")
            return encoding
        except UnicodeDecodeError:
            continue

    logger.warning(f"Could not detect encoding for {file_path}")
    return None

def has_chinese_characters(text: str) -> bool:
    """Check if text contains Chinese characters."""
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

def validate_subtitle_format(content: str, file_path: Path) -> Tuple[bool, str]:
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

def normalize_line_endings(text: str) -> str:
    """Normalize line endings to Unix-style (LF only) for better Plex compatibility."""
    # Replace Windows (CRLF) and old Mac (CR) line endings with Unix (LF)
    return text.replace('\r\n', '\n').replace('\r', '\n')

def convert_one(path: Path, keep_backup: bool = False, force_conversion: bool = False, verbose: bool = False) -> bool:
    """
    Convert a single subtitle file to UTF-8 without BOM.

    Args:
        path: Path to the subtitle file
        keep_backup: Whether to keep a backup of the original file
        force_conversion: Force conversion even if file appears to be UTF-8
        verbose: Enable verbose logging

    Returns:
        True if the file was modified, False otherwise
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    try:
        raw = path.read_bytes()
        logger.debug(f"Processing {path} ({len(raw)} bytes)")

        # Check for UTF-8 BOM
        has_bom = raw.startswith(UTF8_BOM)
        if has_bom:
            logger.debug("UTF-8 BOM detected, will be removed")
            text = raw[len(UTF8_BOM):].decode("utf-8", "strict")
        else:
            # Try to decode as UTF-8 first
            try:
                text = raw.decode("utf-8", "strict")
                if not force_conversion:
                    # Validate the content even if it's UTF-8
                    is_valid, format_type = validate_subtitle_format(text, path)
                    if is_valid:
                        logger.debug("File is already valid UTF-8, no conversion needed")
                        return False
                    else:
                        logger.info(f"File is UTF-8 but has format issues, will normalize")
                else:
                    logger.debug("Force conversion enabled, will process UTF-8 file")
            except UnicodeDecodeError:
                # Not UTF-8, need to detect encoding
                logger.debug("File is not UTF-8, detecting encoding")
                encoding = detect_encoding_comprehensive(path)
                if not encoding:
                    # Last resort fallback
                    encoding = "gb18030"
                    logger.warning(f"Could not detect encoding, using fallback: {encoding}")

                try:
                    text = raw.decode(encoding, "strict")
                    logger.info(f"Successfully decoded using {encoding}")
                except UnicodeDecodeError as e:
                    logger.error(f"Failed to decode {path} with {encoding}: {e}")
                    return False

        # Normalize line endings
        text = normalize_line_endings(text)

        # Validate subtitle format
        is_valid, format_type = validate_subtitle_format(text, path)
        if not is_valid:
            logger.warning(f"Subtitle format validation failed for {path}")

        # Create backup if requested
        if keep_backup:
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

        # Write the converted file
        path.write_text(text, encoding="utf-8", newline="\n")
        logger.debug(f"Successfully wrote UTF-8 file: {path}")

        return True

    except Exception as e:
        logger.error(f"Error processing {path}: {e}")
        return False

def print_detection_info():
    """Print information about available encoding detection libraries."""
    print("Encoding Detection Libraries:")
    if CHARSET_NORMALIZER_AVAILABLE:
        print("  ✓ charset-normalizer (recommended)")
    else:
        print("  ✗ charset-normalizer not available")

    if CHARDET_AVAILABLE:
        print("  ✓ chardet (fallback)")
    else:
        print("  ✗ chardet not available")

    if not CHARSET_NORMALIZER_AVAILABLE and not CHARDET_AVAILABLE:
        print("  ⚠ No automatic encoding detection available")
        print("    Install with: pip install charset-normalizer")
    print()

def main():
    ap = argparse.ArgumentParser(
        description="Enhanced Chinese subtitle converter for maximum Plex compatibility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic conversion
  python convert_ch_subs.py /path/to/plex/library

  # Keep backup copies
  python convert_ch_subs.py /media -b

  # Force conversion even for UTF-8 files (useful for format validation)
  python convert_ch_subs.py /media -f

  # Verbose output for debugging
  python convert_ch_subs.py /media -v

  # Show encoding detection info
  python convert_ch_subs.py --info

Supported formats: .srt, .ass, .ssa
        """
    )

    ap.add_argument("root", nargs='?', help="Root folder to scan")
    ap.add_argument("-b", "--backup", action="store_true",
                   help="Keep .bak backup copies of original files")
    ap.add_argument("-f", "--force", action="store_true",
                   help="Force conversion even if file appears to be UTF-8")
    ap.add_argument("-v", "--verbose", action="store_true",
                   help="Enable verbose output for debugging")
    ap.add_argument("--info", action="store_true",
                   help="Show encoding detection library information and exit")

    args = ap.parse_args()

    # Handle info request
    if args.info:
        print_detection_info()
        return

    # Validate required arguments
    if not args.root:
        ap.error("root folder is required (unless using --info)")

    root_path = Path(args.root)
    if not root_path.exists():
        logger.error(f"Path does not exist: {root_path}")
        sys.exit(1)

    # Set up logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        print_detection_info()

    changed = unchanged = errors = 0
    exts = {".srt", ".ass", ".ssa"}

    # Collect all subtitle files first
    subtitle_files = []

    if root_path.is_file():
        # Single file processing
        if root_path.suffix.lower() in exts:
            subtitle_files.append(root_path)
            logger.info(f"Processing single file: {root_path}")
        else:
            logger.error(f"File is not a supported subtitle format: {root_path}")
            sys.exit(1)
    else:
        # Directory processing
        logger.info(f"Scanning directory: {root_path}")
        for sub in root_path.rglob("*"):
            if sub.suffix.lower() in exts and sub.is_file():
                subtitle_files.append(sub)

    if not subtitle_files:
        logger.warning(f"No subtitle files found in {root_path}")
        return

    logger.info(f"Found {len(subtitle_files)} subtitle files to process")

    # Process each file
    for i, sub in enumerate(subtitle_files, 1):
        if args.verbose:
            logger.info(f"Processing {i}/{len(subtitle_files)}: {sub.name}")

        try:
            if convert_one(sub, keep_backup=args.backup, force_conversion=args.force, verbose=args.verbose):
                print(f"✓ {sub}")
                changed += 1
            else:
                if args.verbose:
                    print(f"- {sub} (no changes needed)")
                unchanged += 1
        except Exception as e:
            print(f"✗ {sub}  → {e}", file=sys.stderr)
            logger.error(f"Failed to process {sub}: {e}")
            errors += 1

    # Summary
    print(f"\nSummary:")
    print(f"  Converted: {changed}")
    print(f"  Unchanged: {unchanged}")
    if errors > 0:
        print(f"  Errors: {errors}")
    print(f"  Total processed: {changed + unchanged + errors}")

    if errors > 0:
        logger.warning("Some files could not be processed. Use -v for detailed error information.")

if __name__ == "__main__":
    main()
