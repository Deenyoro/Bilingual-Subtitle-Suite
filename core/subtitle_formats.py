"""
Subtitle format handlers and data structures.

This module provides:
- Core data structures for subtitle events and tracks
- Format-specific parsers for SRT, ASS, VTT
- Subtitle file writing capabilities
- Format validation and conversion
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from utils.constants import SubtitleFormat
from utils.logging_config import get_logger
from core.encoding_detection import EncodingDetector
from core.timing_utils import TimeConverter

logger = get_logger(__name__)


@dataclass
class SubtitleEvent:
    """Represents a single subtitle event/cue."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Display text
    style: Optional[str] = None  # Style name (for ASS/SSA)
    raw: Optional[str] = None    # Raw text with formatting codes
    
    def duration(self) -> float:
        """Get the duration of this event in seconds."""
        return self.end - self.start
    
    def format_time_range(self, format_type: str = 'readable') -> str:
        """
        Format the time range as a string.
        
        Args:
            format_type: Format type ('readable', 'srt', 'ass', 'vtt')
            
        Returns:
            Formatted time range string
        """
        if format_type == 'readable':
            start_str = TimeConverter.milliseconds_to_readable(int(self.start * 1000))
            end_str = TimeConverter.milliseconds_to_readable(int(self.end * 1000))
            return f"{start_str} --> {end_str}"
        else:
            start_str = TimeConverter.seconds_to_time(self.start, format_type)
            end_str = TimeConverter.seconds_to_time(self.end, format_type)
            return f"{start_str} --> {end_str}"


@dataclass
class SubtitleTrack:
    """Represents a subtitle track with metadata."""
    track_id: str
    track_type: str = "subtitle"
    codec: str = ""
    language: str = ""
    title: str = ""
    is_default: bool = False
    is_forced: bool = False
    ffmpeg_index: str = ""  # FFmpeg stream specifier (e.g., "0:3")
    mkvextract_track_id: str = ""  # Track ID for mkvextract (different from ffmpeg index)

    def __str__(self) -> str:
        """String representation of the track."""
        parts = [f"Track {self.track_id}"]
        if self.language:
            parts.append(f"lang={self.language}")
        if self.title:
            parts.append(f"title='{self.title}'")
        if self.codec:
            parts.append(f"codec={self.codec}")
        if self.is_default:
            parts.append("default")
        if self.is_forced:
            parts.append("forced")
        return f"<{' '.join(parts)}>"


@dataclass
class SubtitleFile:
    """Represents a complete subtitle file with metadata."""
    path: Path
    format: SubtitleFormat
    events: List[SubtitleEvent]
    encoding: str = 'utf-8'
    styles: List[str] = None  # For ASS files
    script_info: List[str] = None  # For ASS files
    
    def __post_init__(self):
        """Initialize default values after creation."""
        if self.styles is None:
            self.styles = []
        if self.script_info is None:
            self.script_info = []
    
    def get_earliest_event(self) -> Optional[SubtitleEvent]:
        """Get the event with the earliest start time."""
        return min(self.events, key=lambda e: e.start) if self.events else None
    
    def get_latest_event(self) -> Optional[SubtitleEvent]:
        """Get the event with the latest end time."""
        return max(self.events, key=lambda e: e.end) if self.events else None
    
    def get_total_duration(self) -> float:
        """Get the total duration from first to last event."""
        if not self.events:
            return 0.0
        earliest = self.get_earliest_event()
        latest = self.get_latest_event()
        return latest.end - earliest.start if earliest and latest else 0.0


class SubtitleParser:
    """Base class for subtitle format parsers."""
    
    @staticmethod
    def clean_subtitle_text(text: str, remove_formatting: bool = False) -> str:
        """
        Clean subtitle text by removing or normalizing formatting codes.
        
        Args:
            text: Raw subtitle text
            remove_formatting: If True, strip all formatting codes
            
        Returns:
            Cleaned text
        """
        # Replace ASS newlines with actual newlines
        text = text.replace('\\N', '\n').replace('\\n', '\n')
        
        if remove_formatting:
            # Remove ASS formatting codes
            text = re.sub(r'\{[^}]+\}', '', text)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            # Remove leading/trailing whitespace
            text = text.strip()
        
        return text


class SRTParser(SubtitleParser):
    """Parser for SRT subtitle format."""
    
    @staticmethod
    def parse(file_path: Path) -> SubtitleFile:
        """
        Parse an SRT subtitle file.
        
        Args:
            file_path: Path to the SRT file
            
        Returns:
            SubtitleFile object
            
        Raises:
            IOError: If file cannot be read
            ValueError: If file format is invalid
        """
        try:
            content, encoding = EncodingDetector.read_file_with_encoding(file_path)
            logger.debug(f"Read {file_path.name} with encoding: {encoding}")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise IOError(f"Cannot read SRT file: {e}")
        
        # Split into subtitle blocks (separated by blank lines)
        blocks = re.split(r'\r?\n\s*\r?\n', content.strip())
        events = []
        
        for block_idx, block in enumerate(blocks):
            lines = block.strip().split('\n')
            if len(lines) < 2:
                continue
                
            # Skip index number if present
            if lines[0].strip().isdigit():
                lines = lines[1:]
            if len(lines) < 2:
                continue
                
            # Parse timing line
            time_line = lines[0].strip()
            try:
                start_seconds, end_seconds = TimeConverter.parse_srt_timestamp(time_line)
            except ValueError as e:
                logger.warning(f"Invalid timestamp in block {block_idx}: {time_line} - {e}")
                continue
            
            # Join remaining lines as subtitle text
            text = '\n'.join(lines[1:]) if len(lines) > 1 else ""
            
            events.append(SubtitleEvent(
                start=start_seconds,
                end=end_seconds,
                text=text.strip()
            ))
        
        logger.info(f"Parsed {len(events)} events from SRT file: {file_path.name}")
        return SubtitleFile(
            path=file_path,
            format=SubtitleFormat.SRT,
            events=events,
            encoding=encoding
        )
    
    @staticmethod
    def write(subtitle_file: SubtitleFile, output_path: Path) -> None:
        """
        Write a SubtitleFile to SRT format.
        
        Args:
            subtitle_file: SubtitleFile to write
            output_path: Output file path
            
        Raises:
            IOError: If file cannot be written
        """
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                for i, event in enumerate(subtitle_file.events, start=1):
                    # Write index
                    f.write(f"{i}\n")
                    
                    # Write timing
                    start_str = TimeConverter.seconds_to_time(event.start, 'srt')
                    end_str = TimeConverter.seconds_to_time(event.end, 'srt')
                    f.write(f"{start_str} --> {end_str}\n")
                    
                    # Write text
                    f.write(f"{event.text}\n\n")
            
            logger.info(f"Created SRT file: {output_path}")
        except Exception as e:
            logger.error(f"Failed to create SRT file: {e}")
            raise IOError(f"Cannot write SRT file: {e}")


class VTTParser(SubtitleParser):
    """Parser for WebVTT subtitle format."""

    @staticmethod
    def parse(file_path: Path) -> SubtitleFile:
        """
        Parse a WebVTT subtitle file.

        Args:
            file_path: Path to the VTT file

        Returns:
            SubtitleFile object

        Raises:
            IOError: If file cannot be read
            ValueError: If file format is invalid
        """
        try:
            content, encoding = EncodingDetector.read_file_with_encoding(file_path)
            logger.debug(f"Read {file_path.name} with encoding: {encoding}")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise IOError(f"Cannot read VTT file: {e}")

        # Remove WEBVTT header and any metadata
        lines = content.strip().split('\n')
        if lines and lines[0].startswith('WEBVTT'):
            lines = lines[1:]

        # Join back and split into cue blocks
        content = '\n'.join(lines)
        blocks = re.split(r'\r?\n\s*\r?\n', content.strip())
        events = []

        for block in blocks:
            lines = block.strip().split('\n')
            if not lines:
                continue

            # Find timing line
            time_line_idx = -1
            for i, line in enumerate(lines):
                if '-->' in line:
                    time_line_idx = i
                    break

            if time_line_idx == -1:
                continue

            # Parse timing
            time_line = lines[time_line_idx]
            time_match = re.match(
                r'(\d{1,2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})',
                time_line
            )
            if not time_match:
                continue

            start_str, end_str = time_match.groups()
            start_seconds = TimeConverter.time_to_seconds(start_str, 'vtt')
            end_seconds = TimeConverter.time_to_seconds(end_str, 'vtt')

            # Get subtitle text (everything after timing line)
            text_lines = lines[time_line_idx + 1:]
            text = '\n'.join(text_lines)

            events.append(SubtitleEvent(
                start=start_seconds,
                end=end_seconds,
                text=text.strip()
            ))

        logger.info(f"Parsed {len(events)} events from VTT file: {file_path.name}")
        return SubtitleFile(
            path=file_path,
            format=SubtitleFormat.VTT,
            events=events,
            encoding=encoding
        )

    @staticmethod
    def write(subtitle_file: SubtitleFile, output_path: Path) -> None:
        """
        Write a SubtitleFile to VTT format.

        Args:
            subtitle_file: SubtitleFile to write
            output_path: Output file path

        Raises:
            IOError: If file cannot be written
        """
        try:
            with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
                # Write header
                f.write("WEBVTT\n\n")

                for event in subtitle_file.events:
                    # Write timing
                    start_str = TimeConverter.seconds_to_time(event.start, 'vtt')
                    end_str = TimeConverter.seconds_to_time(event.end, 'vtt')
                    f.write(f"{start_str} --> {end_str}\n")

                    # Write text
                    f.write(f"{event.text}\n\n")

            logger.info(f"Created VTT file: {output_path}")
        except Exception as e:
            logger.error(f"Failed to create VTT file: {e}")
            raise IOError(f"Cannot write VTT file: {e}")


class ASSParser(SubtitleParser):
    """Parser for ASS/SSA subtitle format."""

    @staticmethod
    def parse(file_path: Path) -> SubtitleFile:
        """
        Parse an ASS/SSA subtitle file.

        Args:
            file_path: Path to the ASS/SSA file

        Returns:
            SubtitleFile object with events, styles, and script info

        Raises:
            IOError: If file cannot be read
        """
        try:
            content, encoding = EncodingDetector.read_file_with_encoding(file_path)
            logger.debug(f"Read {file_path.name} with encoding: {encoding}")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise IOError(f"Cannot read ASS file: {e}")

        events = []
        styles = []
        script_info = []
        format_fields = []
        current_section = None

        lines = content.split('\n')

        for line in lines:
            line = line.rstrip('\r\n')

            # Detect section headers
            if re.match(r'^\[Script Info\]', line, re.IGNORECASE):
                current_section = 'script_info'
                script_info.append(line)
                continue
            elif re.match(r'^\[V4\+? Styles\]', line, re.IGNORECASE):
                current_section = 'styles'
                styles.append(line)
                continue
            elif re.match(r'^\[Events\]', line, re.IGNORECASE):
                current_section = 'events'
                continue
            elif re.match(r'^\[.*\]', line):
                # Unknown section
                current_section = 'unknown'
                continue

            # Process lines based on current section
            if current_section == 'script_info':
                script_info.append(line)
            elif current_section == 'styles':
                styles.append(line)
            elif current_section == 'events':
                if line.strip().lower().startswith('format:'):
                    # Parse format line to know field order
                    format_line = line.split(':', 1)[1].strip()
                    format_fields = [f.strip().lower() for f in format_line.split(',')]
                elif line.strip().lower().startswith('dialogue:'):
                    # Parse dialogue event
                    try:
                        event = ASSParser._parse_dialogue_line(line, format_fields)
                        if event:
                            events.append(event)
                    except Exception as e:
                        logger.debug(f"Failed to parse dialogue line: {line} - {e}")
                        continue

        logger.info(f"Parsed {len(events)} events from ASS file: {file_path.name}")
        return SubtitleFile(
            path=file_path,
            format=SubtitleFormat.ASS if file_path.suffix.lower() == '.ass' else SubtitleFormat.SSA,
            events=events,
            encoding=encoding,
            styles=styles,
            script_info=script_info
        )

    @staticmethod
    def _parse_dialogue_line(line: str, format_fields: List[str]) -> Optional[SubtitleEvent]:
        """
        Parse a dialogue line from ASS format.

        Args:
            line: Dialogue line to parse
            format_fields: List of field names from format line

        Returns:
            SubtitleEvent or None if parsing fails
        """
        content = line.split(':', 1)[1]

        # Split by comma, but preserve commas in the text field
        if format_fields:
            parts = content.split(',', len(format_fields) - 1)
        else:
            # Default ASS format
            parts = content.split(',', 9)

        if len(parts) < 2:
            return None

        # Extract fields based on format or use defaults
        if format_fields:
            try:
                start_idx = format_fields.index('start')
                end_idx = format_fields.index('end')
                text_idx = format_fields.index('text')
                style_idx = format_fields.index('style') if 'style' in format_fields else 3
            except ValueError:
                # Fallback to default positions
                start_idx, end_idx, style_idx, text_idx = 1, 2, 3, 9
        else:
            start_idx, end_idx, style_idx, text_idx = 1, 2, 3, 9

        # Parse times
        start_str = parts[start_idx].strip() if start_idx < len(parts) else "0:00:00.00"
        end_str = parts[end_idx].strip() if end_idx < len(parts) else "0:00:00.00"
        style_name = parts[style_idx].strip() if style_idx < len(parts) else "Default"
        text = parts[text_idx] if text_idx < len(parts) else ""

        start_seconds = TimeConverter.time_to_seconds(start_str, 'ass')
        end_seconds = TimeConverter.time_to_seconds(end_str, 'ass')

        return SubtitleEvent(
            start=start_seconds,
            end=end_seconds,
            text=ASSParser.clean_subtitle_text(text),
            style=style_name,
            raw=text
        )

    @staticmethod
    def write(subtitle_file: SubtitleFile, output_path: Path) -> None:
        """
        Write a SubtitleFile to ASS format.

        Args:
            subtitle_file: SubtitleFile to write
            output_path: Output file path

        Raises:
            IOError: If file cannot be written
        """
        try:
            with open(output_path, 'w', encoding='utf-8-sig', newline='\n') as f:
                # Write script info section
                if subtitle_file.script_info:
                    f.write('\n'.join(subtitle_file.script_info))
                    f.write('\n\n')
                else:
                    f.write('[Script Info]\n')
                    f.write('Title: Generated by Unified Subtitle Processor\n')
                    f.write('ScriptType: v4.00+\n\n')

                # Write styles section
                if subtitle_file.styles:
                    f.write('\n'.join(subtitle_file.styles))
                    f.write('\n\n')
                else:
                    f.write('[V4+ Styles]\n')
                    f.write('Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n')
                    f.write('Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n')

                # Write events section
                f.write('[Events]\n')
                f.write('Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')

                for event in subtitle_file.events:
                    start_str = TimeConverter.seconds_to_time(event.start, 'ass')
                    end_str = TimeConverter.seconds_to_time(event.end, 'ass')
                    style = event.style or 'Default'
                    text = event.raw if event.raw else event.text.replace('\n', '\\N')

                    f.write(f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{text}\n")

            logger.info(f"Created ASS file: {output_path}")
        except Exception as e:
            logger.error(f"Failed to create ASS file: {e}")
            raise IOError(f"Cannot write ASS file: {e}")


class SubtitleFormatFactory:
    """Factory class for creating subtitle parsers and writers."""

    _parsers = {
        SubtitleFormat.SRT: SRTParser,
        SubtitleFormat.VTT: VTTParser,
        SubtitleFormat.ASS: ASSParser,
        SubtitleFormat.SSA: ASSParser,
    }

    @classmethod
    def get_parser(cls, format_type: SubtitleFormat) -> SubtitleParser:
        """
        Get a parser for the specified format.

        Args:
            format_type: Subtitle format

        Returns:
            Parser instance

        Raises:
            ValueError: If format is not supported
        """
        if format_type not in cls._parsers:
            raise ValueError(f"Unsupported subtitle format: {format_type}")
        return cls._parsers[format_type]

    @classmethod
    def parse_file(cls, file_path: Path) -> SubtitleFile:
        """
        Parse a subtitle file automatically detecting the format.

        Args:
            file_path: Path to the subtitle file

        Returns:
            SubtitleFile object

        Raises:
            ValueError: If format is not supported
            IOError: If file cannot be read
        """
        try:
            format_type = SubtitleFormat.from_extension(file_path.suffix)
        except ValueError as e:
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")

        parser = cls.get_parser(format_type)
        return parser.parse(file_path)

    @classmethod
    def write_file(cls, subtitle_file: SubtitleFile, output_path: Path,
                   output_format: Optional[SubtitleFormat] = None) -> None:
        """
        Write a subtitle file in the specified format.

        Args:
            subtitle_file: SubtitleFile to write
            output_path: Output file path
            output_format: Output format (if None, use file extension)

        Raises:
            ValueError: If format is not supported
            IOError: If file cannot be written
        """
        if output_format is None:
            try:
                output_format = SubtitleFormat.from_extension(output_path.suffix)
            except ValueError:
                raise ValueError(f"Cannot determine format from extension: {output_path.suffix}")

        parser = cls.get_parser(output_format)
        parser.write(subtitle_file, output_path)

    @classmethod
    def get_format_from_extension(cls, extension: str) -> SubtitleFormat:
        """
        Get SubtitleFormat from file extension.

        Args:
            extension: File extension (with or without dot)

        Returns:
            SubtitleFormat enum value

        Raises:
            ValueError: If extension is not supported
        """
        return SubtitleFormat.from_extension(extension)
