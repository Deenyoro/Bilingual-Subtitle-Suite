#!/usr/bin/env python3
"""
Enhanced Bilingual Subtitle Merger
==================================

A comprehensive tool for merging Chinese and English subtitles into a single bilingual track.
Supports both external subtitle files and embedded subtitle tracks in video containers.

Key Features:
- Supports SRT, ASS/SSA, and VTT subtitle formats
- Automatic detection and extraction of embedded subtitles using FFmpeg
- Smart timing optimization to reduce subtitle flickering
- Language detection and remapping capabilities
- Bulk processing of multiple video files
- Forced subtitle detection
- Multiple output format options

Author: Enhanced version based on original script
License: MIT
Version: 2.0.0
"""

import argparse
import os
import re
import subprocess
import codecs
import glob
import tempfile
import shutil
import sys
import logging
import json
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import unicodedata

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("subtitle_merger")

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

class SubtitleFormat(Enum):
    """Supported subtitle formats"""
    SRT = "srt"
    ASS = "ass"
    SSA = "ssa"
    VTT = "vtt"
    
    @classmethod
    def from_extension(cls, ext: str) -> Optional['SubtitleFormat']:
        """Get format from file extension"""
        ext = ext.lower().lstrip('.')
        for format_type in cls:
            if format_type.value == ext:
                return format_type
        return None

@dataclass
class SubtitleEvent:
    """Represents a single subtitle event/cue"""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Display text
    style: Optional[str] = None  # Style name (for ASS/SSA)
    raw: Optional[str] = None    # Raw text with formatting codes

@dataclass
class SubtitleTrack:
    """Represents a subtitle track with metadata"""
    track_id: str
    track_type: str = "subtitle"
    codec: str = ""
    language: str = ""
    title: str = ""
    is_default: bool = False
    is_forced: bool = False
    ffmpeg_index: str = ""  # FFmpeg stream specifier

# Supported video container formats
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.m4v', '.mov', '.avi', '.flv', '.ts', '.webm', '.mpg', '.mpeg'}

# Language code mappings for detection
CHINESE_CODES = {'chi', 'zho', 'chs', 'cht', 'zh', 'chinese', 'cn', 'cmn', 'yue', 'hak', 'nan'}
ENGLISH_CODES = {'eng', 'en', 'english', 'enm', 'ang'}

# Subtitle file encoding detection order
ENCODING_PRIORITY = ['utf-8-sig', 'utf-8', 'utf-16', 'latin-1', 'cp1252', 'gbk', 'gb18030', 'big5', 'shift-jis']

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def detect_file_encoding(file_path: str) -> Optional[str]:
    """
    Detect the encoding of a text file by trying multiple encodings.
    
    Args:
        file_path: Path to the file to analyze
        
    Returns:
        The detected encoding name or None if detection failed
    """
    # Try to use chardet if available for better detection
    try:
        import chardet
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            if result['confidence'] > 0.7:
                return result['encoding']
    except ImportError:
        pass
    
    # Fallback to trying encodings in order
    for encoding in ENCODING_PRIORITY:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    return None

def read_file_with_encoding(file_path: str) -> Tuple[str, str]:
    """
    Read a file with automatic encoding detection.
    
    Args:
        file_path: Path to the file to read
        
    Returns:
        Tuple of (file_content, encoding_used)
        
    Raises:
        IOError: If file cannot be read with any encoding
    """
    encoding = detect_file_encoding(file_path)
    if not encoding:
        # Last resort - try with errors='replace'
        encoding = 'utf-8'
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        logger.warning(f"Failed to detect encoding for {file_path}, using UTF-8 with error replacement")
        return content, encoding
    
    with open(file_path, 'r', encoding=encoding) as f:
        content = f.read()
    return content, encoding

def time_to_seconds(time_str: str, format_type: str = 'srt') -> float:
    """
    Convert time string to seconds based on format type.
    
    Args:
        time_str: Time string to convert
        format_type: 'srt' for HH:MM:SS,mmm or 'ass' for H:MM:SS.cc
        
    Returns:
        Time in seconds as float
    """
    try:
        if format_type == 'srt':
            # Handle both comma and period as decimal separator
            time_str = time_str.replace(',', '.')
            h, m, s = time_str.split(':')
            s_parts = s.split('.')
            seconds = float(s_parts[0])
            milliseconds = float(s_parts[1]) / 1000.0 if len(s_parts) > 1 else 0
            return int(h) * 3600 + int(m) * 60 + seconds + milliseconds
        elif format_type == 'ass':
            h, m, s = time_str.split(':')
            s_parts = s.split('.')
            seconds = float(s_parts[0])
            centiseconds = float(s_parts[1]) / 100.0 if len(s_parts) > 1 else 0
            return int(h) * 3600 + int(m) * 60 + seconds + centiseconds
        elif format_type == 'vtt':
            # WebVTT uses HH:MM:SS.mmm or MM:SS.mmm
            parts = time_str.split(':')
            if len(parts) == 2:  # MM:SS.mmm
                m, s = parts
                h = 0
            else:  # HH:MM:SS.mmm
                h, m, s = parts
            s_parts = s.split('.')
            seconds = float(s_parts[0])
            milliseconds = float(s_parts[1]) / 1000.0 if len(s_parts) > 1 else 0
            return int(h) * 3600 + int(m) * 60 + seconds + milliseconds
    except Exception as e:
        logger.error(f"Failed to parse time string '{time_str}' as {format_type}: {e}")
        return 0.0

def seconds_to_time(seconds: float, format_type: str = 'srt') -> str:
    """
    Convert seconds to time string based on format type.
    
    Args:
        seconds: Time in seconds
        format_type: Output format ('srt', 'ass', or 'vtt')
        
    Returns:
        Formatted time string
    """
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    
    if format_type == 'srt':
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    elif format_type == 'ass':
        cs = ms // 10  # Convert to centiseconds
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    elif format_type == 'vtt':
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    else:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def detect_language(text: str) -> str:
    """
    Detect if text contains Chinese characters.
    
    Args:
        text: Text to analyze
        
    Returns:
        'chinese' if Chinese characters detected, 'english' otherwise
    """
    # Check for CJK characters
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # Common Chinese characters
            return 'chinese'
        if '\u3400' <= char <= '\u4dbf':  # Extended Chinese characters
            return 'chinese'
    return 'english'

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

def run_command(cmd: List[str], capture_output: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    """
    Run a command with proper error handling and timeout.
    
    Args:
        cmd: Command and arguments as list
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        
    Returns:
        CompletedProcess instance
    """
    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout
            )
        else:
            result = subprocess.run(cmd, timeout=timeout)
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        # Create a dummy result
        class TimeoutResult:
            def __init__(self):
                self.returncode = -1
                self.stdout = ""
                self.stderr = "Command execution timed out"
        return TimeoutResult()
    except Exception as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.debug(f"Error: {e}")
        # Create a dummy result
        class ErrorResult:
            def __init__(self, error):
                self.returncode = 1
                self.stdout = ""
                self.stderr = f"Command execution failed: {error}"
        return ErrorResult(str(e))

# ============================================================================
# SUBTITLE PARSING FUNCTIONS
# ============================================================================

def parse_srt(file_path: str) -> List[SubtitleEvent]:
    """
    Parse an SRT subtitle file into a list of subtitle events.
    
    SRT Format:
    1
    00:00:01,000 --> 00:00:04,000
    Subtitle text here
    
    Args:
        file_path: Path to the SRT file
        
    Returns:
        List of SubtitleEvent objects
    """
    try:
        data, encoding = read_file_with_encoding(file_path)
        logger.debug(f"Read {file_path} with encoding: {encoding}")
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return []
    
    # Split into subtitle blocks (separated by blank lines)
    blocks = re.split(r'\r?\n\s*\r?\n', data.strip())
    events = []
    
    for block in blocks:
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
        time_match = re.match(
            r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})',
            time_line
        )
        if not time_match:
            logger.debug(f"Failed to parse time line: {time_line}")
            continue
            
        start_str, end_str = time_match.groups()
        start = time_to_seconds(start_str, 'srt')
        end = time_to_seconds(end_str, 'srt')
        
        # Join remaining lines as subtitle text
        text = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        
        events.append(SubtitleEvent(
            start=start,
            end=end,
            text=text.strip()
        ))
    
    logger.info(f"Parsed {len(events)} events from SRT file: {os.path.basename(file_path)}")
    return events

def parse_vtt(file_path: str) -> List[SubtitleEvent]:
    """
    Parse a WebVTT subtitle file into a list of subtitle events.
    
    WebVTT Format:
    WEBVTT
    
    00:00:01.000 --> 00:00:04.000
    Subtitle text here
    
    Args:
        file_path: Path to the VTT file
        
    Returns:
        List of SubtitleEvent objects
    """
    try:
        data, encoding = read_file_with_encoding(file_path)
        logger.debug(f"Read {file_path} with encoding: {encoding}")
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return []
    
    # Remove WEBVTT header and any metadata
    lines = data.strip().split('\n')
    if lines and lines[0].startswith('WEBVTT'):
        lines = lines[1:]
    
    # Join back and split into cue blocks
    data = '\n'.join(lines)
    blocks = re.split(r'\r?\n\s*\r?\n', data.strip())
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
        start = time_to_seconds(start_str, 'vtt')
        end = time_to_seconds(end_str, 'vtt')
        
        # Get subtitle text (everything after timing line)
        text_lines = lines[time_line_idx + 1:]
        text = '\n'.join(text_lines)
        
        events.append(SubtitleEvent(
            start=start,
            end=end,
            text=text.strip()
        ))
    
    logger.info(f"Parsed {len(events)} events from VTT file: {os.path.basename(file_path)}")
    return events

def parse_ass(file_path: str) -> Tuple[List[SubtitleEvent], List[str], List[str]]:
    """
    Parse an ASS/SSA subtitle file into events and metadata.
    
    Args:
        file_path: Path to the ASS/SSA file
        
    Returns:
        Tuple of (events, style_lines, script_info_lines)
    """
    try:
        data, encoding = read_file_with_encoding(file_path)
        logger.debug(f"Read {file_path} with encoding: {encoding}")
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return [], [], []
    
    events = []
    styles = []
    script_info = []
    format_fields = []
    current_section = None
    
    lines = data.split('\n')
    
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
                    content = line.split(':', 1)[1]
                    
                    # Split by comma, but preserve commas in the text field
                    if format_fields:
                        parts = content.split(',', len(format_fields) - 1)
                    else:
                        # Default ASS format
                        parts = content.split(',', 9)
                    
                    if len(parts) < 2:
                        continue
                    
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
                    
                    start = time_to_seconds(start_str, 'ass')
                    end = time_to_seconds(end_str, 'ass')
                    
                    events.append(SubtitleEvent(
                        start=start,
                        end=end,
                        text=clean_subtitle_text(text),
                        style=style_name,
                        raw=text
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse dialogue line: {line} - {e}")
                    continue
    
    logger.info(f"Parsed {len(events)} events from ASS file: {os.path.basename(file_path)}")
    return events, styles, script_info

def parse_subtitle_file(file_path: str) -> Tuple[List[SubtitleEvent], List[str], List[str]]:
    """
    Parse any supported subtitle file format.
    
    Args:
        file_path: Path to the subtitle file
        
    Returns:
        Tuple of (events, styles, script_info)
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.srt':
        events = parse_srt(file_path)
        return events, [], []
    elif ext == '.vtt':
        events = parse_vtt(file_path)
        return events, [], []
    elif ext in ['.ass', '.ssa']:
        return parse_ass(file_path)
    else:
        logger.error(f"Unsupported subtitle format: {ext}")
        return [], [], []

# ============================================================================
# SUBTITLE MERGING FUNCTIONS
# ============================================================================

def optimize_subtitle_timing(events: List[SubtitleEvent], gap_threshold: float = 0.1) -> List[SubtitleEvent]:
    """
    Optimize subtitle timing to reduce flickering and improve readability.
    
    Args:
        events: List of subtitle events to optimize
        gap_threshold: Maximum gap in seconds to merge adjacent subtitles
        
    Returns:
        Optimized list of subtitle events
    """
    if not events:
        return events
    
    # Sort events by start time
    sorted_events = sorted(events, key=lambda e: e.start)
    optimized = []
    
    i = 0
    while i < len(sorted_events):
        current = sorted_events[i]
        
        # Look ahead for events that can be merged
        j = i + 1
        while j < len(sorted_events):
            next_event = sorted_events[j]
            
            # Check if events are close enough and have the same text
            if (next_event.start - current.end <= gap_threshold and
                current.text == next_event.text):
                # Extend current event
                current = SubtitleEvent(
                    start=current.start,
                    end=next_event.end,
                    text=current.text,
                    style=current.style,
                    raw=current.raw
                )
                j += 1
            else:
                break
        
        optimized.append(current)
        i = j
    
    return optimized

def merge_overlapping_events(events1: List[SubtitleEvent], events2: List[SubtitleEvent]) -> List[SubtitleEvent]:
    """
    Merge two lists of subtitle events, handling overlaps intelligently.
    
    Args:
        events1: First list of events (e.g., Chinese)
        events2: Second list of events (e.g., English)
        
    Returns:
        Merged list of events with combined text
    """
    # Create timeline segments
    all_times = set()
    for event in events1 + events2:
        all_times.add(event.start)
        all_times.add(event.end)
    
    timeline = sorted(all_times)
    segments = []
    
    # Create segments for each time interval
    for i in range(len(timeline) - 1):
        seg_start = timeline[i]
        seg_end = timeline[i + 1]
        
        if seg_end <= seg_start:
            continue
        
        # Find events that overlap this segment
        text1 = None
        text2 = None
        
        for event in events1:
            if event.start <= seg_start < event.end:
                text1 = event.text
                break
        
        for event in events2:
            if event.start <= seg_start < event.end:
                text2 = event.text
                break
        
        # Skip empty segments
        if not text1 and not text2:
            continue
        
        # Combine texts
        if text1 and text2:
            combined_text = f"{text1}\n{text2}"
        else:
            combined_text = text1 if text1 else text2
        
        segments.append(SubtitleEvent(
            start=seg_start,
            end=seg_end,
            text=combined_text
        ))
    
    # Optimize the segments
    return optimize_subtitle_timing(segments)

def create_bilingual_srt(events: List[SubtitleEvent], output_path: str) -> None:
    """
    Create a bilingual SRT file from merged events.
    
    Args:
        events: List of merged subtitle events
        output_path: Path for the output SRT file
    """
    try:
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            for i, event in enumerate(events, start=1):
                # Write index
                f.write(f"{i}\n")
                
                # Write timing
                start_str = seconds_to_time(event.start, 'srt')
                end_str = seconds_to_time(event.end, 'srt')
                f.write(f"{start_str} --> {end_str}\n")
                
                # Write text
                f.write(f"{event.text}\n\n")
        
        logger.info(f"Created bilingual SRT: {output_path}")
    except Exception as e:
        logger.error(f"Failed to create SRT file: {e}")
        raise

def create_bilingual_ass(chinese_events: List[SubtitleEvent], 
                        english_events: List[SubtitleEvent],
                        chinese_styles: List[str],
                        english_styles: List[str],
                        script_info_cn: List[str],
                        script_info_en: List[str],
                        output_path: str) -> None:
    """
    Create a bilingual ASS file with separate styles for each language.
    
    Args:
        chinese_events: Chinese subtitle events
        english_events: English subtitle events
        chinese_styles: Chinese style definitions
        english_styles: English style definitions
        script_info_cn: Chinese script info
        script_info_en: English script info
        output_path: Path for the output ASS file
    """
    # Define style names
    style_name_cn = "Chinese"
    style_name_en = "English"
    
    # Build script info section
    script_info_out = ["[Script Info]", "; Merged bilingual subtitle", "; Generated by Enhanced Bilingual Subtitle Merger"]
    
    # Extract resolution info if available
    for line in (script_info_cn or []) + (script_info_en or []):
        if line.strip().startswith(("PlayResX", "PlayResY", "WrapStyle")):
            script_info_out.append(line.strip())
    
    # Add default values if not present
    script_info_out.extend([
        "ScriptType: v4.00+",
        "Collisions: Normal",
        "ScaledBorderAndShadow: yes",
        "Timer: 100.0000",
        ""
    ])
    
    # Build styles section
    style_lines = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    ]
    
    # Parse existing styles to use as templates
    def parse_style_line(line: str) -> List[str]:
        """Extract style parameters from a style line"""
        if line.strip().lower().startswith("style:"):
            return line.split(":", 1)[1].split(",")
        return []
    
    # Get base styles from existing files
    base_cn_style = None
    base_en_style = None
    
    for line in (chinese_styles or []):
        if line.strip().lower().startswith("style:"):
            base_cn_style = parse_style_line(line)
            break
    
    for line in (english_styles or []):
        if line.strip().lower().startswith("style:"):
            base_en_style = parse_style_line(line)
            break
    
    # Create default styles if needed
    if not base_cn_style:
        base_cn_style = [
            style_name_cn, "Arial", "48", "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
            "0", "0", "0", "0", "100", "100", "0", "0", "1", "2", "2", "8", "10", "10", "10", "1"
        ]
    else:
        base_cn_style = base_cn_style[:]
        base_cn_style[0] = style_name_cn
        # Set alignment to top-center (8)
        if len(base_cn_style) > 18:
            base_cn_style[18] = "8"
    
    if not base_en_style:
        base_en_style = [
            style_name_en, "Arial", "44", "&H00FFFF00", "&H000000FF", "&H00000000", "&H00000000",
            "0", "0", "0", "0", "100", "100", "0", "0", "1", "2", "1", "2", "10", "10", "10", "1"
        ]
    else:
        base_en_style = base_en_style[:]
        base_en_style[0] = style_name_en
        # Set alignment to bottom-center (2)
        if len(base_en_style) > 18:
            base_en_style[18] = "2"
    
    # Add styles to output
    style_lines.append("Style: " + ",".join(str(x).strip() for x in base_cn_style))
    style_lines.append("Style: " + ",".join(str(x).strip() for x in base_en_style))
    
    # Build events section
    event_lines = [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    # Combine all events
    all_events = []
    
    for event in chinese_events:
        all_events.append({
            'start': event.start,
            'end': event.end,
            'style': style_name_cn,
            'text': event.raw if event.raw else event.text.replace('\n', '\\N')
        })
    
    for event in english_events:
        all_events.append({
            'start': event.start,
            'end': event.end,
            'style': style_name_en,
            'text': event.raw if event.raw else event.text.replace('\n', '\\N')
        })
    
    # Sort by start time
    all_events.sort(key=lambda e: e['start'])
    
    # Write events
    for event in all_events:
        start_str = seconds_to_time(event['start'], 'ass')
        end_str = seconds_to_time(event['end'], 'ass')
        text = event['text']
        style = event['style']
        
        event_lines.append(
            f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{text}"
        )
    
    # Write to file
    try:
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write('\n'.join(script_info_out))
            f.write('\n\n')
            f.write('\n'.join(style_lines))
            f.write('\n\n')
            f.write('\n'.join(event_lines))
            f.write('\n')
        
        logger.info(f"Created bilingual ASS: {output_path}")
    except Exception as e:
        logger.error(f"Failed to create ASS file: {e}")
        raise

# ============================================================================
# VIDEO CONTAINER FUNCTIONS (FFMPEG INTEGRATION)
# ============================================================================

def is_video_container(file_path: str) -> bool:
    """Check if a file is a supported video container."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS

def probe_video_file(video_path: str) -> Dict[str, Any]:
    """
    Use ffprobe to get detailed information about a video file.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Dictionary containing video metadata
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path
    ]
    
    result = run_command(cmd, timeout=60)
    
    if result.returncode != 0:
        logger.error(f"ffprobe failed for {video_path}: {result.stderr}")
        return {}
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse ffprobe output for {video_path}")
        return {}

def list_subtitle_tracks(video_path: str) -> List[SubtitleTrack]:
    """
    List all subtitle tracks in a video file.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        List of SubtitleTrack objects
    """
    logger.info(f"Analyzing subtitle tracks in: {os.path.basename(video_path)}")
    
    # Try ffprobe first for detailed information
    probe_data = probe_video_file(video_path)
    
    if probe_data and 'streams' in probe_data:
        tracks = []
        
        for stream in probe_data['streams']:
            if stream.get('codec_type') == 'subtitle':
                track = SubtitleTrack(
                    track_id=str(stream['index']),
                    codec=stream.get('codec_name', 'unknown'),
                    language=stream.get('tags', {}).get('language', ''),
                    title=stream.get('tags', {}).get('title', ''),
                    is_default=stream.get('disposition', {}).get('default', 0) == 1,
                    is_forced=stream.get('disposition', {}).get('forced', 0) == 1,
                    ffmpeg_index=f"0:{stream['index']}"
                )
                tracks.append(track)
        
        return tracks
    
    # Fallback to parsing ffmpeg output
    cmd = ["ffmpeg", "-hide_banner", "-i", video_path]
    result = run_command(cmd)
    
    tracks = []
    
    # Parse stream information from stderr
    stream_pattern = re.compile(
        r"Stream #(\d+):(\d+)(?:\((\w+)\))?: Subtitle: ([^,\n]+)([^\n]*)",
        re.IGNORECASE
    )
    
    for line in result.stderr.splitlines():
        match = stream_pattern.search(line)
        if match:
            file_idx = match.group(1)
            stream_idx = match.group(2)
            lang = match.group(3) or ""
            codec = match.group(4).strip()
            extra = match.group(5) or ""
            
            # Extract title if present
            title = ""
            title_match = re.search(r"title\s*:\s*([^,\n]+)", extra, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            
            # Check for default/forced flags
            is_default = "(default)" in extra.lower()
            is_forced = "(forced)" in extra.lower()
            
            track = SubtitleTrack(
                track_id=stream_idx,
                codec=codec,
                language=lang.lower(),
                title=title,
                is_default=is_default,
                is_forced=is_forced,
                ffmpeg_index=f"{file_idx}:{stream_idx}"
            )
            tracks.append(track)
    
    logger.info(f"Found {len(tracks)} subtitle tracks")
    return tracks

def extract_subtitle_track(video_path: str, track: SubtitleTrack, output_path: str) -> Optional[str]:
    """
    Extract a subtitle track from a video file.
    
    Args:
        video_path: Path to the video file
        track: SubtitleTrack object to extract
        output_path: Desired output path
        
    Returns:
        Path to extracted subtitle file or None if extraction failed
    """
    logger.info(f"Extracting subtitle track {track.track_id} ({track.language}) to {os.path.basename(output_path)}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Determine output format from extension
    _, ext = os.path.splitext(output_path)
    ext = ext.lower()
    
    # Map extensions to ffmpeg codec names
    format_map = {
        '.srt': 'srt',
        '.ass': 'ass',
        '.ssa': 'ssa',
        '.vtt': 'webvtt'
    }
    
    # Try extraction with specified format
    output_format = format_map.get(ext, 'srt')
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, f"subtitle{ext if ext else '.srt'}")
        
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", video_path,
            "-map", track.ffmpeg_index,
            "-c:s", output_format,
            tmp_path
        ]
        
        result = run_command(cmd, timeout=120)
        
        if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            # Copy to final destination
            try:
                shutil.copy2(tmp_path, output_path)
                logger.info(f"Successfully extracted subtitle to {os.path.basename(output_path)}")
                return output_path
            except Exception as e:
                logger.error(f"Failed to copy extracted subtitle: {e}")
                return None
        
        # If format conversion failed, try direct copy
        logger.debug(f"Format conversion failed, trying direct stream copy")
        
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", video_path,
            "-map", track.ffmpeg_index,
            "-c:s", "copy",
            tmp_path
        ]
        
        result = run_command(cmd, timeout=120)
        
        if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            # Change extension if needed
            final_output = output_path
            if not output_path.lower().endswith(('.srt', '.ass', '.ssa', '.vtt')):
                # Try to detect format from codec
                if 'ass' in track.codec.lower() or 'ssa' in track.codec.lower():
                    final_output = os.path.splitext(output_path)[0] + '.ass'
                else:
                    final_output = os.path.splitext(output_path)[0] + '.srt'
            
            try:
                shutil.copy2(tmp_path, final_output)
                logger.info(f"Successfully extracted subtitle to {os.path.basename(final_output)}")
                return final_output
            except Exception as e:
                logger.error(f"Failed to copy extracted subtitle: {e}")
                return None
    
    logger.error(f"Failed to extract subtitle track {track.track_id}")
    return None

def find_subtitle_track(tracks: List[SubtitleTrack], 
                       language_codes: set, 
                       prefer_track: Optional[str] = None,
                       remap_lang: Optional[str] = None) -> Optional[SubtitleTrack]:
    """
    Find the best matching subtitle track based on language preferences.
    
    Args:
        tracks: List of available subtitle tracks
        language_codes: Set of language codes to match
        prefer_track: Specific track ID to prefer
        remap_lang: Language code to treat as target language
        
    Returns:
        Best matching SubtitleTrack or None
    """
    if not tracks:
        return None
    
    # If specific track requested, find it
    if prefer_track is not None:
        for track in tracks:
            if track.track_id == str(prefer_track):
                logger.info(f"Using preferred track: {track.track_id}")
                return track
    
    # Check for remapped language
    if remap_lang:
        for track in tracks:
            if track.language.lower() == remap_lang.lower():
                logger.info(f"Found remapped language track: {track.track_id} ({remap_lang})")
                return track
    
    # Find tracks matching language codes
    matching_tracks = []
    for track in tracks:
        # Check language code
        if track.language.lower() in language_codes:
            matching_tracks.append(track)
            continue
        
        # Check title for language hints
        title_lower = track.title.lower()
        if any(code in title_lower for code in language_codes):
            matching_tracks.append(track)
    
    if not matching_tracks:
        return None
    
    # Prefer non-forced tracks
    non_forced = [t for t in matching_tracks if not t.is_forced]
    if non_forced:
        matching_tracks = non_forced
    
    # Prefer default track
    default_tracks = [t for t in matching_tracks if t.is_default]
    if default_tracks:
        return default_tracks[0]
    
    # Return first matching track
    return matching_tracks[0]

# ============================================================================
# EXTERNAL SUBTITLE DETECTION
# ============================================================================

def find_external_subtitle(video_path: str, is_chinese: bool = False) -> Optional[str]:
    """
    Find external subtitle files for a video.
    
    Args:
        video_path: Path to the video file
        is_chinese: True to look for Chinese subtitles, False for English
        
    Returns:
        Path to the best matching subtitle file or None
    """
    video_dir = os.path.dirname(video_path) or '.'
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    logger.info(f"Searching for external {'Chinese' if is_chinese else 'English'} subtitle for: {os.path.basename(video_path)}")
    
    # Build search patterns
    if is_chinese:
        lang_patterns = [
            '.zh', '.chi', '.chs', '.cht', '.cn', '.chinese',
            '_zh', '_chi', '_chs', '_cht', '_cn', '_chinese'
        ]
    else:
        lang_patterns = [
            '.en', '.eng', '.english',
            '_en', '_eng', '_english'
        ]
    
    # Search for subtitle files
    candidates = []
    
    for file in os.listdir(video_dir):
        if not file.startswith(base_name):
            continue
        
        file_lower = file.lower()
        
        # Check if it's a subtitle file
        if not any(file_lower.endswith(ext) for ext in ['.srt', '.ass', '.ssa', '.vtt']):
            continue
        
        # Check for language patterns
        for pattern in lang_patterns:
            if pattern in file_lower:
                candidates.append(os.path.join(video_dir, file))
                break
    
    # If no language-specific files found, check the default subtitle
    if not candidates:
        for ext in ['.srt', '.ass', '.ssa', '.vtt']:
            default_sub = os.path.join(video_dir, base_name + ext)
            if os.path.exists(default_sub):
                # Try to detect language from content
                try:
                    with open(default_sub, 'r', encoding='utf-8', errors='ignore') as f:
                        sample = f.read(4096)
                        detected_lang = detect_language(sample)
                        
                        if is_chinese and detected_lang == 'chinese':
                            candidates.append(default_sub)
                        elif not is_chinese and detected_lang == 'english':
                            candidates.append(default_sub)
                except:
                    pass
    
    if candidates:
        # Sort by specificity (more specific language codes first)
        candidates.sort(key=lambda x: len(x))
        logger.info(f"Found external subtitle: {os.path.basename(candidates[0])}")
        return candidates[0]
    
    logger.info(f"No external {'Chinese' if is_chinese else 'English'} subtitle found")
    return None

# ============================================================================
# FORCED SUBTITLE DETECTION
# ============================================================================

def detect_forced_subtitles(events1: List[SubtitleEvent], 
                          events2: List[SubtitleEvent], 
                          threshold: float = 0.1) -> Optional[str]:
    """
    Detect if one subtitle track is likely forced subtitles.
    
    Forced subtitles typically have significantly fewer lines than regular subtitles.
    
    Args:
        events1: First subtitle track events
        events2: Second subtitle track events
        threshold: Ratio threshold for forced detection
        
    Returns:
        'first' or 'second' if forced detected, None otherwise
    """
    count1 = len(events1)
    count2 = len(events2)
    
    if count1 == 0 or count2 == 0:
        return None
    
    ratio1 = count1 / count2
    ratio2 = count2 / count1
    
    if ratio1 < threshold:
        return 'first'
    elif ratio2 < threshold:
        return 'second'
    
    return None

# ============================================================================
# MAIN PROCESSING FUNCTIONS
# ============================================================================

def process_video(video_path: str,
                 chinese_sub: Optional[str] = None,
                 english_sub: Optional[str] = None,
                 output_format: str = "srt",
                 output_path: Optional[str] = None,
                 chinese_track: Optional[str] = None,
                 english_track: Optional[str] = None,
                 remap_chinese: Optional[str] = None,
                 remap_english: Optional[str] = None,
                 prefer_external: bool = False,
                 prefer_embedded: bool = False,
                 force_overwrite: bool = False) -> bool:
    """
    Process a video file to create bilingual subtitles.
    
    Args:
        video_path: Path to the video file
        chinese_sub: Path to Chinese subtitle file (optional)
        english_sub: Path to English subtitle file (optional)
        output_format: Output format ('srt' or 'ass')
        output_path: Custom output path (optional)
        chinese_track: Specific Chinese track to use
        english_track: Specific English track to use
        remap_chinese: Language code to treat as Chinese
        remap_english: Language code to treat as English
        prefer_external: Prefer external subtitles over embedded
        prefer_embedded: Prefer embedded subtitles over external
        force_overwrite: Overwrite existing output files
        
    Returns:
        True if processing succeeded, False otherwise
    """
    logger.info(f"{'=' * 60}")
    logger.info(f"Processing: {os.path.basename(video_path)}")
    logger.info(f"{'=' * 60}")
    
    # Validate preferences
    if prefer_external and prefer_embedded:
        logger.warning("Both prefer_external and prefer_embedded set. Using default behavior.")
        prefer_external = prefer_embedded = False
    
    # Temporary files for extracted subtitles
    temp_files = []
    
    try:
        # 1. Find/Extract Chinese subtitles
        if not chinese_sub:
            # Check external first (unless preferring embedded)
            if not prefer_embedded:
                chinese_sub = find_external_subtitle(video_path, is_chinese=True)
            
            # If no external or preferring embedded, check embedded tracks
            if not chinese_sub or prefer_embedded:
                tracks = list_subtitle_tracks(video_path)
                
                # Build language codes to search for
                lang_codes = CHINESE_CODES.copy()
                if remap_chinese:
                    lang_codes.add(remap_chinese.lower())
                
                track = find_subtitle_track(tracks, lang_codes, chinese_track, remap_chinese)
                
                if track:
                    # Extract to temporary file
                    temp_file = os.path.join(
                        os.path.dirname(video_path),
                        f".{os.path.basename(video_path)}.chi_track_{track.track_id}.ass"
                    )
                    extracted = extract_subtitle_track(video_path, track, temp_file)
                    if extracted:
                        temp_files.append(extracted)
                        # If preferring external and we have both, keep external
                        if not (prefer_external and chinese_sub):
                            chinese_sub = extracted
        
        # 2. Find/Extract English subtitles
        if not english_sub:
            # Check external first (unless preferring embedded)
            if not prefer_embedded:
                english_sub = find_external_subtitle(video_path, is_chinese=False)
            
            # If no external or preferring embedded, check embedded tracks
            if not english_sub or prefer_embedded:
                tracks = list_subtitle_tracks(video_path)
                
                # Build language codes to search for
                lang_codes = ENGLISH_CODES.copy()
                if remap_english:
                    lang_codes.add(remap_english.lower())
                
                track = find_subtitle_track(tracks, lang_codes, english_track, remap_english)
                
                if track:
                    # Extract to temporary file
                    temp_file = os.path.join(
                        os.path.dirname(video_path),
                        f".{os.path.basename(video_path)}.eng_track_{track.track_id}.ass"
                    )
                    extracted = extract_subtitle_track(video_path, track, temp_file)
                    if extracted:
                        temp_files.append(extracted)
                        # If preferring external and we have both, keep external
                        if not (prefer_external and english_sub):
                            english_sub = extracted
        
        # 3. Check if we have at least one subtitle
        if not chinese_sub and not english_sub:
            logger.error("No Chinese or English subtitles found!")
            return False
        
        if not chinese_sub:
            logger.warning("No Chinese subtitles found. Output will contain English only.")
        if not english_sub:
            logger.warning("No English subtitles found. Output will contain Chinese only.")
        
        # 4. Parse subtitle files
        chinese_events = []
        chinese_styles = []
        chinese_script = []
        
        english_events = []
        english_styles = []
        english_script = []
        
        if chinese_sub:
            logger.info(f"Parsing Chinese subtitle: {os.path.basename(chinese_sub)}")
            chinese_events, chinese_styles, chinese_script = parse_subtitle_file(chinese_sub)
            logger.info(f"Found {len(chinese_events)} Chinese subtitle events")
        
        if english_sub:
            logger.info(f"Parsing English subtitle: {os.path.basename(english_sub)}")
            english_events, english_styles, english_script = parse_subtitle_file(english_sub)
            logger.info(f"Found {len(english_events)} English subtitle events")
        
        # 5. Check for forced subtitles
        if chinese_events and english_events:
            forced = detect_forced_subtitles(chinese_events, english_events)
            if forced:
                which = "Chinese" if forced == 'first' else "English"
                logger.warning(f"Warning: {which} track appears to be forced subtitles (significantly fewer lines)")
        
        # 6. Determine output path
        if not output_path:
            base = os.path.splitext(video_path)[0]
            output_path = f"{base}.bilingual.{output_format}"
        
        # Check if output exists
        if os.path.exists(output_path) and not force_overwrite:
            logger.warning(f"Output file already exists: {output_path}")
            logger.warning("Use --force to overwrite")
            return False
        
        # 7. Create merged subtitle file
        if output_format.lower() == 'srt':
            # Merge events for SRT
            merged_events = merge_overlapping_events(chinese_events, english_events)
            create_bilingual_srt(merged_events, output_path)
        else:
            # Create ASS with separate tracks
            create_bilingual_ass(
                chinese_events, english_events,
                chinese_styles, english_styles,
                chinese_script, english_script,
                output_path
            )
        
        logger.info(f"Successfully created: {os.path.basename(output_path)}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"Removed temporary file: {temp_file}")
            except Exception as e:
                logger.debug(f"Failed to remove temporary file {temp_file}: {e}")

def process_videos_parallel(video_files: List[str], 
                          args: argparse.Namespace,
                          max_workers: int = 4) -> None:
    """
    Process multiple videos in parallel.
    
    Args:
        video_files: List of video file paths
        args: Command line arguments
        max_workers: Maximum number of parallel workers
    """
    total = len(video_files)
    completed = 0
    failed = []
    
    logger.info(f"Processing {total} video files with {max_workers} workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_video = {
            executor.submit(
                process_video,
                video,
                args.chinese,
                args.english,
                args.format,
                args.output,
                args.chi_track,
                args.eng_track,
                args.remap_chi,
                args.remap_eng,
                args.prefer_external,
                args.prefer_embedded,
                args.force
            ): video
            for video in video_files
        }
        
        # Process completed tasks
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            completed += 1
            
            try:
                success = future.result()
                if not success:
                    failed.append(video)
                
                # Progress update
                logger.info(f"Progress: {completed}/{total} completed")
                
            except Exception as e:
                logger.error(f"Failed to process {os.path.basename(video)}: {e}")
                failed.append(video)
    
    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Processing complete!")
    logger.info(f"Total: {total}, Successful: {total - len(failed)}, Failed: {len(failed)}")
    
    if failed:
        logger.info("\nFailed videos:")
        for video in failed:
            logger.info(f"  - {os.path.basename(video)}")

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point for the command line interface."""
    parser = argparse.ArgumentParser(
        description="Enhanced Bilingual Subtitle Merger - Merge Chinese and English subtitles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Merge external subtitle files
  %(prog)s -c movie.chi.srt -e movie.eng.srt -o movie.bilingual.srt
  
  # Extract and merge from video file
  %(prog)s -v movie.mkv
  
  # Process all videos in a directory
  %(prog)s --bulk /path/to/movies/
  
  # Use specific embedded tracks
  %(prog)s -v movie.mkv --chi-track 2 --eng-track 3
  
  # Remap Japanese audio as Chinese (for anime)
  %(prog)s -v anime.mkv --remap-chi jpn
  
  # Prefer external subtitles over embedded
  %(prog)s -v movie.mkv --prefer-external
"""
    )
    
    # Input options
    input_group = parser.add_argument_group('Input Options')
    input_group.add_argument('-v', '--video', 
                           help='Video file to process')
    input_group.add_argument('-c', '--chinese', 
                           help='External Chinese subtitle file')
    input_group.add_argument('-e', '--english', 
                           help='External English subtitle file')
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument('-o', '--output', 
                            help='Output file path (default: <video>.bilingual.<format>)')
    output_group.add_argument('-f', '--format', 
                            choices=['srt', 'ass'], 
                            default='srt',
                            help='Output format (default: srt)')
    output_group.add_argument('--force', 
                            action='store_true',
                            help='Overwrite existing output files')
    
    # Track selection
    track_group = parser.add_argument_group('Track Selection')
    track_group.add_argument('--chi-track', 
                           help='Specific track number for Chinese subtitles')
    track_group.add_argument('--eng-track', 
                           help='Specific track number for English subtitles')
    track_group.add_argument('--remap-chi', 
                           help='Treat this language code as Chinese (e.g., "jpn" for anime)')
    track_group.add_argument('--remap-eng', 
                           help='Treat this language code as English')
    
    # Processing options
    proc_group = parser.add_argument_group('Processing Options')
    proc_group.add_argument('--bulk', 
                          action='store_true',
                          help='Process all videos in the specified directory')
    proc_group.add_argument('--prefer-external', 
                          action='store_true',
                          help='Prefer external subtitles over embedded ones')
    proc_group.add_argument('--prefer-embedded', 
                          action='store_true',
                          help='Prefer embedded subtitles over external ones')
    proc_group.add_argument('--workers', 
                          type=int, 
                          default=4,
                          help='Number of parallel workers for bulk processing (default: 4)')
    
    # Other options
    parser.add_argument('--debug', 
                       action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--version', 
                       action='version', 
                       version='%(prog)s 2.0.0')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        logger.setLevel(logging.DEBUG)
        # Also set debug for subprocess commands
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate arguments
    if not args.video and not args.chinese and not args.english and not args.bulk:
        parser.error("Must provide --video, --chinese/--english, or --bulk")
    
    # Handle bulk processing
    if args.bulk:
        target_path = args.video or '.'
        
        if os.path.isdir(target_path):
            # Find all video files
            video_files = []
            for ext in VIDEO_EXTENSIONS:
                pattern = os.path.join(target_path, f'*{ext}')
                video_files.extend(glob.glob(pattern))
            
            video_files.sort()
        elif os.path.isfile(target_path) and is_video_container(target_path):
            video_files = [target_path]
        else:
            logger.error(f"Invalid path for bulk processing: {target_path}")
            sys.exit(1)
        
        if not video_files:
            logger.warning("No video files found for bulk processing")
            sys.exit(0)
        
        # Process videos
        if len(video_files) > 1 and args.workers > 1:
            process_videos_parallel(video_files, args, args.workers)
        else:
            # Process sequentially
            for i, video in enumerate(video_files, 1):
                logger.info(f"\nProcessing {i}/{len(video_files)}: {os.path.basename(video)}")
                process_video(
                    video,
                    args.chinese,
                    args.english,
                    args.format,
                    args.output,
                    args.chi_track,
                    args.eng_track,
                    args.remap_chi,
                    args.remap_eng,
                    args.prefer_external,
                    args.prefer_embedded,
                    args.force
                )
    
    # Handle single video processing
    elif args.video:
        if not os.path.exists(args.video):
            logger.error(f"Video file not found: {args.video}")
            sys.exit(1)
        
        success = process_video(
            args.video,
            args.chinese,
            args.english,
            args.format,
            args.output,
            args.chi_track,
            args.eng_track,
            args.remap_chi,
            args.remap_eng,
            args.prefer_external,
            args.prefer_embedded,
            args.force
        )
        
        sys.exit(0 if success else 1)
    
    # Handle direct subtitle merging (no video)
    else:
        if not args.chinese and not args.english:
            logger.error("Must provide at least one subtitle file")
            sys.exit(1)
        
        # Parse subtitles
        chinese_events = []
        chinese_styles = []
        chinese_script = []
        
        english_events = []
        english_styles = []
        english_script = []
        
        if args.chinese:
            if not os.path.exists(args.chinese):
                logger.error(f"Chinese subtitle file not found: {args.chinese}")
                sys.exit(1)
            chinese_events, chinese_styles, chinese_script = parse_subtitle_file(args.chinese)
        
        if args.english:
            if not os.path.exists(args.english):
                logger.error(f"English subtitle file not found: {args.english}")
                sys.exit(1)
            english_events, english_styles, english_script = parse_subtitle_file(args.english)
        
        # Determine output path
        output_path = args.output
        if not output_path:
            if args.chinese:
                base = os.path.splitext(args.chinese)[0]
            else:
                base = os.path.splitext(args.english)[0]
            output_path = f"{base}.bilingual.{args.format}"
        
        # Check if output exists
        if os.path.exists(output_path) and not args.force:
            logger.error(f"Output file already exists: {output_path}")
            logger.error("Use --force to overwrite")
            sys.exit(1)
        
        # Create merged file
        try:
            if args.format == 'srt':
                merged_events = merge_overlapping_events(chinese_events, english_events)
                create_bilingual_srt(merged_events, output_path)
            else:
                create_bilingual_ass(
                    chinese_events, english_events,
                    chinese_styles, english_styles,
                    chinese_script, english_script,
                    output_path
                )
            
            logger.info(f"Successfully created: {output_path}")
        except Exception as e:
            logger.error(f"Failed to create output file: {e}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if logger.level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(1)
