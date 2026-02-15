"""
Bilingual subtitle splitting processor.

This module provides functionality for splitting bilingual subtitle files
into separate language-specific files. It is the inverse of the merger -
taking a combined bilingual SRT and producing individual Chinese and English
(or other language) SRT files.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple, Callable
from core.subtitle_formats import SubtitleEvent, SubtitleFile, SubtitleFormatFactory
from core.language_detection import LanguageDetector
from utils.constants import SubtitleFormat
from utils.logging_config import get_logger

logger = get_logger(__name__)


class BilingualSplitter:
    """Splits bilingual subtitle files into separate language files."""

    def __init__(self, strip_formatting: bool = True,
                 progress_callback: Optional[Callable[[str, int, int], None]] = None):
        """
        Initialize the bilingual splitter.

        Args:
            strip_formatting: Whether to strip HTML formatting tags from output
            progress_callback: Optional callback function(step_name, current, total)
        """
        self.strip_formatting = strip_formatting
        self.progress_callback = progress_callback

    def split_file(self, input_path: Path, output_dir: Optional[Path] = None,
                   lang1_label: str = 'zh', lang2_label: str = 'en',
                   lang1_format: str = 'srt') -> Tuple[Optional[Path], Optional[Path]]:
        """
        Split a bilingual subtitle file into separate language files.

        Args:
            input_path: Path to the bilingual subtitle file
            output_dir: Output directory (default: same as input file)
            lang1_label: Label for the first language (default: 'zh')
            lang2_label: Label for the second language (default: 'en')
            lang1_format: Output format for CJK file ('srt' or 'ass'). ASS format
                         embeds a CJK-compatible font for better player compatibility.

        Returns:
            Tuple of (lang1_output_path, lang2_output_path), either may be None if
            no content was found for that language

        Raises:
            IOError: If file cannot be read or written
            ValueError: If file format is not supported
        """
        if not input_path.exists():
            raise IOError(f"Input file not found: {input_path}")

        logger.info(f"Splitting bilingual subtitle: {input_path.name}")
        self._report_progress("Parsing subtitle file", 0, 3)

        # Parse the input file
        subtitle_file = SubtitleFormatFactory.parse_file(input_path)
        logger.info(f"Parsed {len(subtitle_file.events)} events from {input_path.name}")

        # Split events by language
        self._report_progress("Splitting by language", 1, 3)
        lang1_events, lang2_events = self._split_events(subtitle_file.events)

        logger.info(f"Split result: {len(lang1_events)} CJK events, {len(lang2_events)} English events")

        # Determine output paths
        if output_dir is None:
            output_dir = input_path.parent

        base_name = self._get_clean_base_name(input_path)
        lang1_ext = lang1_format if lang1_format in ('srt', 'ass') else 'srt'
        lang1_path = output_dir / f"{base_name}.{lang1_label}.{lang1_ext}"
        lang2_path = output_dir / f"{base_name}.{lang2_label}.srt"

        # Safety: prevent overwriting the input file
        input_resolved = input_path.resolve()
        if lang1_path.resolve() == input_resolved:
            lang1_path = output_dir / f"{base_name}.{lang1_label}-only.{lang1_ext}"
            logger.info(f"Output would overwrite input, using: {lang1_path.name}")
        if lang2_path.resolve() == input_resolved:
            lang2_path = output_dir / f"{base_name}.{lang2_label}-only.srt"
            logger.info(f"Output would overwrite input, using: {lang2_path.name}")

        # Write output files
        self._report_progress("Writing output files", 2, 3)
        lang1_output = None
        lang2_output = None

        if lang1_events:
            lang1_fmt = SubtitleFormat.ASS if lang1_ext == 'ass' else SubtitleFormat.SRT
            lang1_file = SubtitleFile(
                path=lang1_path,
                format=lang1_fmt,
                events=lang1_events,
                encoding='utf-8'
            )
            SubtitleFormatFactory.write_file(lang1_file, lang1_path, output_format=lang1_fmt)
            lang1_output = lang1_path
            logger.info(f"Wrote {len(lang1_events)} events to {lang1_path.name}")
        else:
            logger.warning(f"No {lang1_label} content found in bilingual file")

        if lang2_events:
            lang2_file = SubtitleFile(
                path=lang2_path,
                format=SubtitleFormat.SRT,
                events=lang2_events,
                encoding='utf-8'
            )
            SubtitleFormatFactory.write_file(lang2_file, lang2_path)
            lang2_output = lang2_path
            logger.info(f"Wrote {len(lang2_events)} events to {lang2_path.name}")
        else:
            logger.warning(f"No {lang2_label} content found in bilingual file")

        self._report_progress("Split complete", 3, 3)
        return lang1_output, lang2_output

    def _split_events(self, events: List[SubtitleEvent]) -> Tuple[List[SubtitleEvent], List[SubtitleEvent]]:
        """
        Split subtitle events into two language-specific lists.

        Each event's text is examined line-by-line. Lines containing CJK characters
        go to lang1 (Chinese/Japanese/Korean), and lines containing primarily
        Latin characters go to lang2 (English).

        Args:
            events: List of subtitle events to split

        Returns:
            Tuple of (lang1_events, lang2_events)
        """
        lang1_events = []
        lang2_events = []

        for event in events:
            text = event.text
            if not text or not text.strip():
                continue

            lines = text.split('\n')
            lang1_lines = []
            lang2_lines = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Strip HTML formatting if requested
                clean_line = self._strip_html_tags(line) if self.strip_formatting else line
                if not clean_line.strip():
                    continue

                lang = self._classify_line(clean_line)
                if lang == 'cjk':
                    lang1_lines.append(clean_line)
                elif lang == 'latin':
                    lang2_lines.append(clean_line)
                else:
                    # Ambiguous lines (numbers, punctuation only) - add to both
                    lang1_lines.append(clean_line)
                    lang2_lines.append(clean_line)

            # Create events for each language if there's content
            if lang1_lines:
                lang1_events.append(SubtitleEvent(
                    start=event.start,
                    end=event.end,
                    text='\n'.join(lang1_lines)
                ))

            if lang2_lines:
                lang2_events.append(SubtitleEvent(
                    start=event.start,
                    end=event.end,
                    text='\n'.join(lang2_lines)
                ))

        return lang1_events, lang2_events

    def _classify_line(self, line: str) -> str:
        """
        Classify a text line as CJK, Latin, or ambiguous.

        Args:
            line: Text line to classify

        Returns:
            'cjk' for Chinese/Japanese/Korean text,
            'latin' for English/Latin text,
            'other' for ambiguous content
        """
        cjk_count = 0
        latin_count = 0

        for char in line:
            cp = ord(char)
            # CJK Unified Ideographs
            if 0x4E00 <= cp <= 0x9FFF:
                cjk_count += 1
            # CJK Extension A
            elif 0x3400 <= cp <= 0x4DBF:
                cjk_count += 1
            # CJK Extension B and beyond
            elif 0x20000 <= cp <= 0x2CEAF:
                cjk_count += 1
            # CJK Compatibility Ideographs
            elif 0xF900 <= cp <= 0xFAFF:
                cjk_count += 1
            # Hiragana
            elif 0x3040 <= cp <= 0x309F:
                cjk_count += 1
            # Katakana
            elif 0x30A0 <= cp <= 0x30FF:
                cjk_count += 1
            # Hangul
            elif 0xAC00 <= cp <= 0xD7AF:
                cjk_count += 1
            # CJK punctuation (fullwidth forms, CJK symbols)
            elif 0x3000 <= cp <= 0x303F:
                cjk_count += 1
            elif 0xFF00 <= cp <= 0xFFEF:
                cjk_count += 1
            # Latin letters
            elif char.isalpha() and cp < 0x0250:
                latin_count += 1

        if cjk_count > 0 and cjk_count >= latin_count:
            return 'cjk'
        elif latin_count > 0:
            return 'latin'
        else:
            return 'other'

    def _strip_html_tags(self, text: str) -> str:
        """
        Strip HTML formatting tags from subtitle text.

        Removes tags like <i>, </i>, <b>, </b>, <u>, </u>, <font ...>, </font>.

        Args:
            text: Text with potential HTML tags

        Returns:
            Text with HTML tags removed
        """
        return re.sub(r'<[^>]+>', '', text)

    def _get_clean_base_name(self, file_path: Path) -> str:
        """
        Get a clean base name by stripping language suffixes and subtitle extensions.

        For example:
            'Movie.zh.srt' -> 'Movie'
            'Movie.zh-en.srt' -> 'Movie'
            'Movie.bilingual.srt' -> 'Movie'

        Args:
            file_path: Path to the subtitle file

        Returns:
            Clean base name without language suffixes
        """
        name = file_path.stem  # e.g., 'Movie.zh'

        # Language patterns to strip (order matters - check compound first)
        lang_patterns = [
            '.zh-en', '.en-zh', '.zh-ja', '.ja-zh', '.zh-ko', '.ko-zh',
            '.ja-en', '.en-ja', '.ko-en', '.en-ko',
            '.bilingual', '.dual',
            '.zh', '.en', '.chi', '.eng', '.chs', '.cht', '.cn',
            '.chinese', '.english',
            '.ja', '.jp', '.jpn', '.japanese',
            '.ko', '.kr', '.kor', '.korean',
            '.fr', '.fre', '.fra', '.french',
            '.de', '.ger', '.deu', '.german',
            '.es', '.spa', '.spanish',
        ]

        for pattern in lang_patterns:
            if name.lower().endswith(pattern):
                name = name[:-len(pattern)]
                break

        return name

    def is_bilingual(self, file_path: Path) -> bool:
        """
        Check if a subtitle file appears to contain bilingual content.

        Args:
            file_path: Path to the subtitle file

        Returns:
            True if the file contains both CJK and Latin text lines
        """
        try:
            subtitle_file = SubtitleFormatFactory.parse_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path} for bilingual check: {e}")
            return False

        has_cjk = False
        has_latin = False

        for event in subtitle_file.events[:50]:  # Check first 50 events
            for line in event.text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                lang = self._classify_line(line)
                if lang == 'cjk':
                    has_cjk = True
                elif lang == 'latin':
                    has_latin = True

                if has_cjk and has_latin:
                    return True

        return has_cjk and has_latin

    def _report_progress(self, step_name: str, current: int = 0, total: int = 0):
        """Report progress to callback if available."""
        if self.progress_callback:
            self.progress_callback(step_name, current, total)
