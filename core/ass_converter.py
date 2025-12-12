"""
ASS/SSA to SRT subtitle converter.

This module provides functionality to convert ASS/SSA subtitle files to SRT format,
with special handling for bilingual subtitles that contain both Chinese and English
text in a single file.

Features:
- Converts ASS formatting to clean SRT text
- Preserves bilingual structure (Chinese on top, English below)
- Handles various ASS formatting codes and effects
- Supports both full conversion and text extraction
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from utils.logging_config import get_logger
from core.encoding_detection import EncodingDetector

logger = get_logger(__name__)


@dataclass
class ASSDialogue:
    """Represents a parsed ASS dialogue line."""
    layer: int
    start: str  # Time string like "0:01:30.94"
    end: str
    style: str
    name: str
    margin_l: int
    margin_r: int
    margin_v: int
    effect: str
    text: str
    raw_text: str  # Original text with ASS codes


class ASSToSRTConverter:
    """
    Converts ASS/SSA subtitle files to SRT format.

    Handles bilingual subtitles where Chinese and English text may be:
    1. On separate lines within the same dialogue (separated by \\N)
    2. In separate dialogue entries with similar timing
    3. Mixed with ASS formatting codes
    """

    # ASS formatting patterns to remove
    ASS_TAG_PATTERN = re.compile(r'\{[^}]*\}')

    # Pattern to detect Chinese characters
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df\u2a700-\u2b73f\u2b740-\u2b81f\uf900-\ufaff\ufe30-\ufe4f]')

    # Pattern to detect Japanese characters (Hiragana and Katakana)
    JAPANESE_PATTERN = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')

    # Pattern to detect Korean characters (Hangul)
    KOREAN_PATTERN = re.compile(r'[\uac00-\ud7af\u1100-\u11ff]')

    def __init__(self,
                 strip_effects: bool = True,
                 preserve_bilingual: bool = True,
                 skip_empty: bool = True):
        """
        Initialize the converter.

        Args:
            strip_effects: Remove all ASS formatting/effect codes
            preserve_bilingual: Keep bilingual structure (CJK on top, English below)
            skip_empty: Skip dialogue entries with no visible text
        """
        self.strip_effects = strip_effects
        self.preserve_bilingual = preserve_bilingual
        self.skip_empty = skip_empty

    def convert_file(self,
                     input_path: Path,
                     output_path: Optional[Path] = None) -> Path:
        """
        Convert an ASS file to SRT format.

        Args:
            input_path: Path to the input ASS file
            output_path: Path for the output SRT file (default: same name with .srt extension)

        Returns:
            Path to the created SRT file

        Raises:
            IOError: If file cannot be read or written
            ValueError: If file format is invalid
        """
        input_path = Path(input_path)

        if output_path is None:
            output_path = input_path.with_suffix('.srt')
        else:
            output_path = Path(output_path)

        logger.info(f"Converting ASS to SRT: {input_path.name}")

        # Read and parse ASS file
        dialogues = self._parse_ass_file(input_path)

        if not dialogues:
            raise ValueError(f"No dialogue entries found in {input_path}")

        logger.info(f"Parsed {len(dialogues)} dialogue entries")

        # Convert to SRT entries
        srt_entries = self._convert_dialogues_to_srt(dialogues)

        logger.info(f"Created {len(srt_entries)} SRT entries")

        # Write SRT file
        self._write_srt_file(srt_entries, output_path)

        logger.info(f"Created SRT file: {output_path}")
        return output_path

    def _parse_ass_file(self, file_path: Path) -> List[ASSDialogue]:
        """
        Parse an ASS file and extract dialogue entries.

        Args:
            file_path: Path to ASS file

        Returns:
            List of ASSDialogue objects
        """
        try:
            content, encoding = EncodingDetector.read_file_with_encoding(file_path)
            logger.debug(f"Read {file_path.name} with encoding: {encoding}")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise IOError(f"Cannot read ASS file: {e}")

        dialogues = []
        format_fields = []
        in_events_section = False

        for line in content.split('\n'):
            line = line.rstrip('\r\n')

            # Check for Events section
            if re.match(r'^\[Events\]', line, re.IGNORECASE):
                in_events_section = True
                continue
            elif re.match(r'^\[.*\]', line):
                in_events_section = False
                continue

            if not in_events_section:
                continue

            # Parse format line
            if line.strip().lower().startswith('format:'):
                format_line = line.split(':', 1)[1].strip()
                format_fields = [f.strip().lower() for f in format_line.split(',')]
                continue

            # Parse dialogue line
            if line.strip().lower().startswith('dialogue:'):
                try:
                    dialogue = self._parse_dialogue_line(line, format_fields)
                    if dialogue:
                        dialogues.append(dialogue)
                except Exception as e:
                    logger.debug(f"Failed to parse dialogue: {line[:50]}... - {e}")
                    continue

        return dialogues

    def _parse_dialogue_line(self, line: str, format_fields: List[str]) -> Optional[ASSDialogue]:
        """
        Parse a single dialogue line.

        Args:
            line: Dialogue line from ASS file
            format_fields: Field names from Format line

        Returns:
            ASSDialogue object or None if parsing fails
        """
        content = line.split(':', 1)[1]

        # Split by comma, but preserve commas in text field (last field)
        num_fields = len(format_fields) if format_fields else 10
        parts = content.split(',', num_fields - 1)

        if len(parts) < num_fields:
            return None

        # Build field mapping
        if format_fields:
            field_map = {field: parts[i].strip() for i, field in enumerate(format_fields) if i < len(parts)}
        else:
            # Default ASS format
            field_map = {
                'layer': parts[0].strip(),
                'start': parts[1].strip(),
                'end': parts[2].strip(),
                'style': parts[3].strip(),
                'name': parts[4].strip(),
                'marginl': parts[5].strip(),
                'marginr': parts[6].strip(),
                'marginv': parts[7].strip(),
                'effect': parts[8].strip(),
                'text': parts[9] if len(parts) > 9 else ''
            }

        raw_text = field_map.get('text', '')

        return ASSDialogue(
            layer=int(field_map.get('layer', '0')),
            start=field_map.get('start', '0:00:00.00'),
            end=field_map.get('end', '0:00:00.00'),
            style=field_map.get('style', 'Default'),
            name=field_map.get('name', ''),
            margin_l=int(field_map.get('marginl', '0') or '0'),
            margin_r=int(field_map.get('marginr', '0') or '0'),
            margin_v=int(field_map.get('marginv', '0') or '0'),
            effect=field_map.get('effect', ''),
            text=self._clean_ass_text(raw_text),
            raw_text=raw_text
        )

    def _clean_ass_text(self, text: str) -> str:
        """
        Clean ASS text by removing formatting codes and converting newlines.

        Args:
            text: Raw ASS text with formatting codes

        Returns:
            Cleaned text suitable for SRT
        """
        if self.strip_effects:
            # Remove all ASS formatting tags
            text = self.ASS_TAG_PATTERN.sub('', text)

        # Convert ASS newlines to actual newlines
        text = text.replace('\\N', '\n').replace('\\n', '\n')

        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        return text.strip()

    def _convert_dialogues_to_srt(self, dialogues: List[ASSDialogue]) -> List[Tuple[str, str, str]]:
        """
        Convert ASS dialogues to SRT entries.

        Args:
            dialogues: List of parsed ASS dialogues

        Returns:
            List of (start_time, end_time, text) tuples in SRT format
        """
        srt_entries = []

        for dialogue in dialogues:
            # Skip empty entries
            if self.skip_empty and not dialogue.text.strip():
                continue

            # Convert times to SRT format
            start_srt = self._ass_time_to_srt(dialogue.start)
            end_srt = self._ass_time_to_srt(dialogue.end)

            text = dialogue.text

            # Handle bilingual preservation
            if self.preserve_bilingual:
                text = self._format_bilingual_text(text)

            if text.strip():
                srt_entries.append((start_srt, end_srt, text))

        # Sort by start time
        srt_entries.sort(key=lambda x: self._srt_time_to_ms(x[0]))

        return srt_entries

    def _ass_time_to_srt(self, ass_time: str) -> str:
        """
        Convert ASS time format (H:MM:SS.cc) to SRT format (HH:MM:SS,mmm).

        ASS uses centiseconds (1/100), SRT uses milliseconds (1/1000).

        Args:
            ass_time: Time string in ASS format

        Returns:
            Time string in SRT format
        """
        parts = ass_time.split(':')
        if len(parts) != 3:
            return "00:00:00,000"

        hours = int(parts[0])
        minutes = int(parts[1])
        sec_parts = parts[2].split('.')
        seconds = int(sec_parts[0])

        # Convert centiseconds to milliseconds
        if len(sec_parts) > 1:
            centiseconds = sec_parts[1].ljust(2, '0')[:2]
            milliseconds = int(centiseconds) * 10
        else:
            milliseconds = 0

        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _srt_time_to_ms(self, srt_time: str) -> int:
        """Convert SRT time string to milliseconds for sorting."""
        match = re.match(r'(\d+):(\d+):(\d+),(\d+)', srt_time)
        if not match:
            return 0

        h, m, s, ms = map(int, match.groups())
        return h * 3600000 + m * 60000 + s * 1000 + ms

    def _format_bilingual_text(self, text: str) -> str:
        """
        Format bilingual text to ensure CJK text appears on top.

        Args:
            text: Subtitle text (may contain multiple lines)

        Returns:
            Formatted text with CJK on top, English below
        """
        lines = text.split('\n')

        if len(lines) <= 1:
            return text

        cjk_lines = []
        other_lines = []

        for line in lines:
            if self._contains_cjk(line):
                cjk_lines.append(line)
            else:
                other_lines.append(line)

        # Combine with CJK on top
        result_lines = cjk_lines + other_lines
        return '\n'.join(result_lines)

    def _contains_cjk(self, text: str) -> bool:
        """Check if text contains CJK (Chinese, Japanese, Korean) characters."""
        return bool(
            self.CHINESE_PATTERN.search(text) or
            self.JAPANESE_PATTERN.search(text) or
            self.KOREAN_PATTERN.search(text)
        )

    def _write_srt_file(self,
                        entries: List[Tuple[str, str, str]],
                        output_path: Path) -> None:
        """
        Write SRT entries to file.

        Args:
            entries: List of (start_time, end_time, text) tuples
            output_path: Output file path
        """
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for i, (start, end, text) in enumerate(entries, 1):
                    f.write(f"{i}\n")
                    f.write(f"{start} --> {end}\n")
                    f.write(f"{text}\n\n")
        except Exception as e:
            logger.error(f"Failed to write SRT file: {e}")
            raise IOError(f"Cannot write SRT file: {e}")

    def get_preview(self, input_path: Path, max_entries: int = 10) -> List[Dict[str, Any]]:
        """
        Get a preview of the conversion without writing to file.

        Args:
            input_path: Path to ASS file
            max_entries: Maximum number of entries to return

        Returns:
            List of dicts with 'start', 'end', 'text' keys
        """
        dialogues = self._parse_ass_file(input_path)
        entries = self._convert_dialogues_to_srt(dialogues)

        preview = []
        for start, end, text in entries[:max_entries]:
            preview.append({
                'start': start,
                'end': end,
                'text': text
            })

        return preview


def convert_ass_to_srt(input_path: Path,
                       output_path: Optional[Path] = None,
                       preserve_bilingual: bool = True) -> Path:
    """
    Convenience function to convert ASS file to SRT.

    Args:
        input_path: Path to input ASS file
        output_path: Optional output path (defaults to same name with .srt)
        preserve_bilingual: Keep bilingual structure

    Returns:
        Path to created SRT file
    """
    converter = ASSToSRTConverter(preserve_bilingual=preserve_bilingual)
    return converter.convert_file(input_path, output_path)
