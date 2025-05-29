#!/usr/bin/env python3
"""
Enhanced Subtitle Realignment Tool
==================================

A comprehensive tool for realigning subtitle files (SRT/ASS) with multiple modes:
- Automatic mode: Aligns based on earliest start times
- Interactive mode: Allows manual selection of alignment points

Features:
- Supports both SRT and ASS subtitle formats
- Interactive alignment point selection
- Backup creation before modifications
- Comprehensive error handling
- Progress tracking
- Detailed logging

"""

import argparse
import os
import re
import glob
import logging
import sys
import shutil
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Union
from datetime import datetime
from pathlib import Path
import json

# For interactive mode
try:
    import curses
    CURSES_AVAILABLE = True
except ImportError:
    CURSES_AVAILABLE = False
    print("Warning: curses not available. Interactive mode will use basic console interface.")

# ----------------------------------------------------
# LOGGING SETUP
# ----------------------------------------------------
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

# Configure logging with colored output
def setup_logging(debug: bool = False) -> logging.Logger:
    """Set up logging with appropriate level and formatting"""
    logger = logging.getLogger("subtitle_realign_enhanced")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler with colored formatter
    handler = logging.StreamHandler()
    if sys.stdout.isatty():  # Only use colors if outputting to terminal
        formatter = ColoredFormatter('%(levelname)s: %(message)s')
    else:
        formatter = logging.Formatter('%(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

logger = setup_logging()

# ----------------------------------------------------
# DATA STRUCTURES
# ----------------------------------------------------
@dataclass
class SubtitleEvent:
    """Represents a single subtitle event/entry"""
    start: int          # Start time in milliseconds
    end: int            # End time in milliseconds
    text: str           # Subtitle text content
    idx: int = -1       # Line index in original file (for ASS)
    original_line: str = ""  # Original line (for ASS)
    
    def duration_ms(self) -> int:
        """Calculate duration in milliseconds"""
        return self.end - self.start
    
    def format_time_range(self) -> str:
        """Format start-end time as readable string"""
        start_str = format_ms_to_readable(self.start)
        end_str = format_ms_to_readable(self.end)
        return f"{start_str} --> {end_str}"

@dataclass
class SubtitleFile:
    """Represents a complete subtitle file with metadata"""
    path: Path
    format: str  # 'srt' or 'ass'
    events: List[SubtitleEvent]
    original_lines: Optional[List[str]] = None  # For ASS files
    encoding: str = 'utf-8'
    
    def get_earliest_event(self) -> Optional[SubtitleEvent]:
        """Get the event with the earliest start time"""
        return min(self.events, key=lambda e: e.start) if self.events else None
    
    def get_latest_event(self) -> Optional[SubtitleEvent]:
        """Get the event with the latest end time"""
        return max(self.events, key=lambda e: e.end) if self.events else None

# ----------------------------------------------------
# UTILITY FUNCTIONS
# ----------------------------------------------------
def format_ms_to_readable(ms: int) -> str:
    """Convert milliseconds to readable format (HH:MM:SS.mmm)"""
    if ms < 0:
        ms = 0
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def create_backup(file_path: Path) -> Path:
    """Create a backup of the file with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = file_path.parent / "subtitle_backups"
    backup_dir.mkdir(exist_ok=True)
    
    backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_name
    
    shutil.copy2(file_path, backup_path)
    logger.debug(f"Created backup: {backup_path}")
    return backup_path

def detect_encoding(file_path: Path) -> str:
    """Detect file encoding (simplified version)"""
    # Try common encodings
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'gbk', 'big5']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Default to utf-8 with error handling
    logger.warning(f"Could not detect encoding for {file_path}, using utf-8 with error replacement")
    return 'utf-8'

# ----------------------------------------------------
# SUBTITLE EVENT OPERATIONS
# ----------------------------------------------------
def shift_events_ms(events: List[SubtitleEvent], shift_ms: int) -> None:
    """
    Shift all events by the specified milliseconds.
    Negative values shift backwards, positive forwards.
    """
    for event in events:
        event.start += shift_ms
        event.end += shift_ms
        
        # Ensure no negative times
        if event.start < 0:
            logger.debug(f"Adjusted negative start time for event: {event.text[:30]}...")
            event.start = 0
        if event.end < 0:
            logger.debug(f"Adjusted negative end time for event: {event.text[:30]}...")
            event.end = 0

def remove_events_before(events: List[SubtitleEvent], cutoff_ms: int) -> List[SubtitleEvent]:
    """Remove all events that end before the cutoff time"""
    filtered = [e for e in events if e.end > cutoff_ms]
    removed_count = len(events) - len(filtered)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} events ending before {format_ms_to_readable(cutoff_ms)}")
    return filtered

# ----------------------------------------------------
# SRT PARSING & WRITING
# ----------------------------------------------------
class SRTHandler:
    """Handler for SRT subtitle format"""
    
    @staticmethod
    def parse(file_path: Path) -> SubtitleFile:
        """Parse an SRT file and return a SubtitleFile object"""
        encoding = detect_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            data = f.read()
        
        # Split into subtitle blocks
        blocks = re.split(r'\r?\n\r?\n', data.strip())
        events = []
        
        for block_idx, block in enumerate(blocks):
            lines = block.strip().splitlines()
            if not lines:
                continue
            
            # Skip the index line if present
            if re.match(r'^\d+$', lines[0]):
                lines = lines[1:]
            if not lines:
                continue
            
            # Parse timestamp line
            timestamp_pattern = r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)'
            match = re.match(timestamp_pattern, lines[0])
            if not match:
                logger.warning(f"Invalid timestamp in block {block_idx}: {lines[0]}")
                continue
            
            start_str, end_str = match.groups()
            
            # Convert to milliseconds
            start_ms = SRTHandler._timestamp_to_ms(start_str)
            end_ms = SRTHandler._timestamp_to_ms(end_str)
            
            # Get subtitle text
            text = "\n".join(lines[1:]) if len(lines) > 1 else ""
            
            events.append(SubtitleEvent(
                start=start_ms,
                end=end_ms,
                text=text
            ))
        
        logger.debug(f"Parsed {len(events)} events from {file_path}")
        return SubtitleFile(path=file_path, format='srt', events=events, encoding=encoding)
    
    @staticmethod
    def _timestamp_to_ms(timestr: str) -> int:
        """Convert SRT timestamp to milliseconds"""
        # Normalize decimal separator
        timestr = timestr.replace(',', '.')
        
        # Parse components
        h_str, m_str, s_str = timestr.split(':')
        h = int(h_str)
        m = int(m_str)
        
        # Handle seconds and milliseconds
        if '.' in s_str:
            s, ms_str = s_str.split('.')
        else:
            s, ms_str = s_str, '0'
        
        s = int(s)
        # Ensure milliseconds are 3 digits
        ms = int(ms_str.ljust(3, '0')[:3])
        
        total_ms = (h * 3600 + m * 60 + s) * 1000 + ms
        return total_ms
    
    @staticmethod
    def write(subtitle_file: SubtitleFile, out_path: Path) -> None:
        """Write SubtitleFile to SRT format"""
        with open(out_path, 'w', encoding=subtitle_file.encoding) as f:
            for i, event in enumerate(subtitle_file.events, start=1):
                start_str = SRTHandler._ms_to_timestamp(event.start)
                end_str = SRTHandler._ms_to_timestamp(event.end)
                
                f.write(f"{i}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{event.text}\n")
                f.write("\n")
        
        logger.debug(f"Wrote {len(subtitle_file.events)} events to {out_path}")
    
    @staticmethod
    def _ms_to_timestamp(ms: int) -> str:
        """Convert milliseconds to SRT timestamp format"""
        if ms < 0:
            ms = 0
        
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms %= 1000
        
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# ----------------------------------------------------
# ASS PARSING & WRITING
# ----------------------------------------------------
class ASSHandler:
    """Handler for ASS/SSA subtitle format"""
    
    @staticmethod
    def parse(file_path: Path) -> SubtitleFile:
        """Parse an ASS file and return a SubtitleFile object"""
        encoding = detect_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            lines = f.readlines()
        
        events = []
        in_events = False
        format_cols = []
        
        for i, line in enumerate(lines):
            line_lower = line.strip().lower()
            
            # Track section changes
            if line_lower.startswith("[events]"):
                in_events = True
                continue
            elif in_events and line_lower.startswith("["):
                # New section, done with events
                in_events = False
                continue
            
            if in_events:
                # Parse format line
                if line_lower.startswith("format:"):
                    format_str = line.split(":", 1)[1]
                    format_cols = [col.strip().lower() for col in format_str.split(",")]
                    logger.debug(f"ASS format columns: {format_cols}")
                    continue
                
                # Parse dialogue lines
                if line_lower.startswith("dialogue:"):
                    content = line.split(":", 1)[1]
                    
                    # Split by commas, respecting the format
                    if format_cols:
                        parts = content.split(",", len(format_cols) - 1)
                    else:
                        # Default ASS format assumption
                        parts = content.split(",", 9)
                    
                    if len(parts) < 3:
                        logger.warning(f"Invalid dialogue line at {i}: {line.strip()}")
                        continue
                    
                    # Find column indices
                    try:
                        start_idx = format_cols.index("start") if format_cols else 1
                        end_idx = format_cols.index("end") if format_cols else 2
                        text_idx = format_cols.index("text") if format_cols else 9
                    except (ValueError, IndexError):
                        start_idx, end_idx, text_idx = 1, 2, 9
                    
                    # Extract timing and text
                    start_str = parts[start_idx].strip() if start_idx < len(parts) else "0:00:00.00"
                    end_str = parts[end_idx].strip() if end_idx < len(parts) else "0:00:00.00"
                    text = parts[text_idx].strip() if text_idx < len(parts) else ""
                    
                    # Convert to milliseconds
                    start_ms = ASSHandler._timestamp_to_ms(start_str)
                    end_ms = ASSHandler._timestamp_to_ms(end_str)
                    
                    events.append(SubtitleEvent(
                        start=start_ms,
                        end=end_ms,
                        text=text,
                        idx=i,
                        original_line=line
                    ))
        
        logger.debug(f"Parsed {len(events)} dialogue events from {file_path}")
        return SubtitleFile(
            path=file_path,
            format='ass',
            events=events,
            original_lines=lines,
            encoding=encoding
        )
    
    @staticmethod
    def _timestamp_to_ms(ass_time: str) -> int:
        """Convert ASS timestamp to milliseconds"""
        parts = ass_time.split(':')
        if len(parts) < 3:
            return 0
        
        h = int(parts[0])
        m = int(parts[1])
        
        # Handle seconds and fractional part
        s_part = parts[2]
        if '.' in s_part:
            s_str, frac_str = s_part.split('.', 1)
        else:
            s_str, frac_str = s_part, '0'
        
        s = int(s_str)
        
        # Handle fractional seconds (can be centiseconds or milliseconds)
        if len(frac_str) >= 3:
            # Treat as milliseconds
            ms = int(frac_str[:3].ljust(3, '0'))
        elif len(frac_str) == 2:
            # Treat as centiseconds
            ms = int(frac_str) * 10
        elif len(frac_str) == 1:
            # Treat as deciseconds
            ms = int(frac_str) * 100
        else:
            ms = 0
        
        total_ms = (h * 3600 + m * 60 + s) * 1000 + ms
        return total_ms
    
    @staticmethod
    def write(subtitle_file: SubtitleFile, out_path: Path) -> None:
        """Write SubtitleFile to ASS format"""
        if not subtitle_file.original_lines:
            raise ValueError("Cannot write ASS file without original lines")
        
        # Create index mapping for events
        events_by_idx = {e.idx: e for e in subtitle_file.events}
        out_lines = []
        
        # Process each line
        for i, line in enumerate(subtitle_file.original_lines):
            if i in events_by_idx:
                # Update dialogue line with new timing
                event = events_by_idx[i]
                updated_line = ASSHandler._update_dialogue_timing(line, event)
                out_lines.append(updated_line)
            else:
                # Keep non-dialogue lines as-is
                out_lines.append(line)
        
        # Write to file
        with open(out_path, 'w', encoding=subtitle_file.encoding) as f:
            f.writelines(out_lines)
        
        logger.debug(f"Wrote {len(subtitle_file.events)} dialogue events to {out_path}")
    
    @staticmethod
    def _update_dialogue_timing(line: str, event: SubtitleEvent) -> str:
        """Update timing in a dialogue line"""
        prefix, content = line.split(":", 1)
        fields = content.split(",", 9)  # Max 10 fields in ASS
        
        if len(fields) >= 3:
            # Update start and end times (usually at indices 1 and 2)
            fields[1] = ASSHandler._ms_to_timestamp(event.start)
            fields[2] = ASSHandler._ms_to_timestamp(event.end)
            return prefix + ":" + ",".join(fields)
        else:
            # Fallback: return original line
            logger.warning(f"Could not update timing for line: {line.strip()}")
            return line
    
    @staticmethod
    def _ms_to_timestamp(ms: int) -> str:
        """Convert milliseconds to ASS timestamp format"""
        if ms < 0:
            ms = 0
        
        total_seconds = ms // 1000
        remain_ms = ms % 1000
        
        h = total_seconds // 3600
        total_seconds %= 3600
        m = total_seconds // 60
        s = total_seconds % 60
        
        # Convert to centiseconds for ASS format
        centiseconds = int(round(remain_ms / 10.0))
        if centiseconds >= 100:
            centiseconds = 99
        
        return f"{h}:{m:02d}:{s:02d}.{centiseconds:02d}"

# ----------------------------------------------------
# SUBTITLE FILE OPERATIONS
# ----------------------------------------------------
class SubtitleManager:
    """Main class for managing subtitle operations"""
    
    def __init__(self):
        self.handlers = {
            '.srt': SRTHandler,
            '.ass': ASSHandler,
            '.ssa': ASSHandler  # SSA uses same format as ASS
        }
    
    def load_subtitle(self, file_path: Path) -> SubtitleFile:
        """Load a subtitle file based on its extension"""
        ext = file_path.suffix.lower()
        
        if ext not in self.handlers:
            raise ValueError(f"Unsupported subtitle format: {ext}")
        
        handler = self.handlers[ext]
        logger.info(f"Loading {file_path.name}...")
        
        try:
            subtitle = handler.parse(file_path)
            logger.info(f"  Loaded {len(subtitle.events)} events")
            return subtitle
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            raise
    
    def save_subtitle(self, subtitle: SubtitleFile, out_path: Path, create_backup: bool = True) -> None:
        """Save a subtitle file"""
        if create_backup and out_path.exists():
            create_backup(out_path)
        
        ext = out_path.suffix.lower()
        if ext not in self.handlers:
            raise ValueError(f"Unsupported subtitle format: {ext}")
        
        handler = self.handlers[ext]
        
        try:
            handler.write(subtitle, out_path)
            logger.info(f"Saved {len(subtitle.events)} events to {out_path.name}")
        except Exception as e:
            logger.error(f"Failed to save {out_path}: {e}")
            raise
    
    def align_subtitles(self, source: SubtitleFile, reference: SubtitleFile,
                       source_align_idx: int = 0, ref_align_idx: int = 0) -> SubtitleFile:
        """
        Align source subtitle to reference at specified event indices.
        
        Args:
            source: Source subtitle file to be aligned
            reference: Reference subtitle file
            source_align_idx: Index of source event to align
            ref_align_idx: Index of reference event to align to
            
        Returns:
            Aligned subtitle file
        """
        if source_align_idx >= len(source.events):
            raise ValueError(f"Source align index {source_align_idx} out of range")
        if ref_align_idx >= len(reference.events):
            raise ValueError(f"Reference align index {ref_align_idx} out of range")
        
        # Get alignment points
        source_event = source.events[source_align_idx]
        ref_event = reference.events[ref_align_idx]
        
        # Calculate shift needed
        shift_ms = ref_event.start - source_event.start
        
        logger.info(f"Aligning at:")
        logger.info(f"  Source: Event {source_align_idx + 1} - {source_event.format_time_range()}")
        logger.info(f"  Reference: Event {ref_align_idx + 1} - {ref_event.format_time_range()}")
        logger.info(f"  Shift: {shift_ms:+d} ms ({shift_ms/1000:+.3f} seconds)")
        
        # Remove events before alignment points
        aligned_events = source.events[source_align_idx:]
        logger.info(f"  Removing {source_align_idx} events from source before alignment point")
        
        # Apply shift
        shift_events_ms(aligned_events, shift_ms)
        
        # Create aligned subtitle file
        aligned = SubtitleFile(
            path=source.path,
            format=source.format,
            events=aligned_events,
            original_lines=source.original_lines,
            encoding=source.encoding
        )
        
        return aligned

# ----------------------------------------------------
# INTERACTIVE MODE
# ----------------------------------------------------
class InteractiveAligner:
    """Interactive mode for manual alignment selection"""
    
    def __init__(self, source: SubtitleFile, reference: SubtitleFile):
        self.source = source
        self.reference = reference
        self.source_idx = 0
        self.ref_idx = 0
        self.current_side = 'source'  # 'source' or 'reference'
    
    def run_curses(self, stdscr) -> Tuple[int, int]:
        """Run interactive mode using curses"""
        curses.curs_set(0)  # Hide cursor
        stdscr.clear()
        
        # Color pairs
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Header
            header = "=== INTERACTIVE SUBTITLE ALIGNMENT ==="
            stdscr.addstr(0, (width - len(header)) // 2, header, curses.color_pair(1) | curses.A_BOLD)
            
            # Instructions
            instructions = [
                "Use TAB to switch between source/reference",
                "Use UP/DOWN arrows to navigate events",
                "Press ENTER to confirm alignment",
                "Press 'q' to quit without saving"
            ]
            
            y = 2
            for inst in instructions:
                stdscr.addstr(y, 2, inst, curses.color_pair(3))
                y += 1
            
            y += 1
            
            # Display subtitle info
            col_width = (width - 4) // 2
            
            # Source column
            source_header = f"SOURCE: {self.source.path.name}"
            stdscr.addstr(y, 2, source_header[:col_width-2], 
                         curses.color_pair(2 if self.current_side == 'source' else 0) | curses.A_BOLD)
            
            # Reference column
            ref_header = f"REFERENCE: {self.reference.path.name}"
            stdscr.addstr(y, col_width + 2, ref_header[:col_width-2],
                         curses.color_pair(2 if self.current_side == 'reference' else 0) | curses.A_BOLD)
            
            y += 2
            
            # Display events
            display_count = min(10, (height - y - 2) // 3)
            
            # Source events
            for i in range(display_count):
                idx = self.source_idx + i
                if idx >= len(self.source.events):
                    break
                
                event = self.source.events[idx]
                is_selected = i == 0 and self.current_side == 'source'
                
                # Event number and time
                line1 = f"{idx + 1}. {event.format_time_range()}"
                stdscr.addstr(y + i * 3, 2, line1[:col_width-2],
                            curses.color_pair(4) if is_selected else 0)
                
                # Event text (truncated)
                text_lines = event.text.split('\n')
                if text_lines:
                    line2 = text_lines[0][:col_width-4]
                    stdscr.addstr(y + i * 3 + 1, 4, line2,
                                curses.A_BOLD if is_selected else 0)
            
            # Reference events
            for i in range(display_count):
                idx = self.ref_idx + i
                if idx >= len(self.reference.events):
                    break
                
                event = self.reference.events[idx]
                is_selected = i == 0 and self.current_side == 'reference'
                
                # Event number and time
                line1 = f"{idx + 1}. {event.format_time_range()}"
                stdscr.addstr(y + i * 3, col_width + 2, line1[:col_width-2],
                            curses.color_pair(4) if is_selected else 0)
                
                # Event text (truncated)
                text_lines = event.text.split('\n')
                if text_lines:
                    line2 = text_lines[0][:col_width-4]
                    stdscr.addstr(y + i * 3 + 1, col_width + 4, line2,
                                curses.A_BOLD if is_selected else 0)
            
            # Status line
            status = f"Source: {self.source_idx + 1}/{len(self.source.events)} | " \
                    f"Reference: {self.ref_idx + 1}/{len(self.reference.events)}"
            stdscr.addstr(height - 1, 2, status, curses.color_pair(3))
            
            stdscr.refresh()
            
            # Handle input
            key = stdscr.getch()
            
            if key == ord('q'):
                return None, None
            elif key == ord('\t'):  # TAB
                self.current_side = 'reference' if self.current_side == 'source' else 'source'
            elif key == curses.KEY_UP:
                if self.current_side == 'source' and self.source_idx > 0:
                    self.source_idx -= 1
                elif self.current_side == 'reference' and self.ref_idx > 0:
                    self.ref_idx -= 1
            elif key == curses.KEY_DOWN:
                if self.current_side == 'source' and self.source_idx < len(self.source.events) - 1:
                    self.source_idx += 1
                elif self.current_side == 'reference' and self.ref_idx < len(self.reference.events) - 1:
                    self.ref_idx += 1
            elif key == ord('\n'):  # ENTER
                return self.source_idx, self.ref_idx
    
    def run_basic(self) -> Tuple[int, int]:
        """Run interactive mode using basic console interface"""
        print("\n=== INTERACTIVE SUBTITLE ALIGNMENT ===")
        print("Select alignment points for source and reference subtitles\n")
        
        # Display first few events from both files
        print(f"SOURCE: {self.source.path.name}")
        print("-" * 60)
        for i, event in enumerate(self.source.events[:10]):
            print(f"{i + 1}. [{event.format_time_range()}]")
            print(f"   {event.text[:100]}{'...' if len(event.text) > 100 else ''}")
        
        print(f"\nREFERENCE: {self.reference.path.name}")
        print("-" * 60)
        for i, event in enumerate(self.reference.events[:10]):
            print(f"{i + 1}. [{event.format_time_range()}]")
            print(f"   {event.text[:100]}{'...' if len(event.text) > 100 else ''}")
        
        # Get user input
        while True:
            try:
                source_num = input("\nEnter source event number to align (or 'q' to quit): ")
                if source_num.lower() == 'q':
                    return None, None
                source_idx = int(source_num) - 1
                
                if source_idx < 0 or source_idx >= len(self.source.events):
                    print(f"Invalid source event number. Must be between 1 and {len(self.source.events)}")
                    continue
                
                ref_num = input("Enter reference event number to align to: ")
                ref_idx = int(ref_num) - 1
                
                if ref_idx < 0 or ref_idx >= len(self.reference.events):
                    print(f"Invalid reference event number. Must be between 1 and {len(self.reference.events)}")
                    continue
                
                # Confirm selection
                print(f"\nYou selected:")
                print(f"  Source event {source_idx + 1}: {self.source.events[source_idx].format_time_range()}")
                print(f"  Reference event {ref_idx + 1}: {self.reference.events[ref_idx].format_time_range()}")
                
                confirm = input("Confirm alignment? (y/n): ")
                if confirm.lower() == 'y':
                    return source_idx, ref_idx
                
            except ValueError:
                print("Please enter valid numbers")
            except KeyboardInterrupt:
                return None, None
    
    def run(self) -> Tuple[int, int]:
        """Run interactive alignment selection"""
        if CURSES_AVAILABLE and sys.stdout.isatty():
            try:
                return curses.wrapper(self.run_curses)
            except Exception as e:
                logger.warning(f"Curses interface failed: {e}. Falling back to basic interface.")
                return self.run_basic()
        else:
            return self.run_basic()

# ----------------------------------------------------
# MAIN APPLICATION
# ----------------------------------------------------
class SubtitleRealignApp:
    """Main application class"""
    
    def __init__(self, args):
        self.args = args
        self.manager = SubtitleManager()
        
        # Set up logging
        global logger
        logger = setup_logging(args.debug)
    
    def find_subtitle_pairs(self) -> List[Tuple[Path, Path]]:
        """Find matching subtitle pairs in the specified folder"""
        folder = Path(self.args.folder)
        src_ext = self.args.src_ext.lower()
        ref_ext = self.args.ref_ext.lower()
        
        # Ensure extensions start with dot
        if not src_ext.startswith('.'):
            src_ext = '.' + src_ext
        if not ref_ext.startswith('.'):
            ref_ext = '.' + ref_ext
        
        logger.info(f"Scanning {folder} for subtitle pairs...")
        logger.info(f"  Source extension: {src_ext}")
        logger.info(f"  Reference extension: {ref_ext}")
        
        # Find all source files
        pattern = f"*{src_ext}"
        src_files = list(folder.glob(pattern))
        
        if not src_files:
            logger.warning(f"No source files found matching {pattern}")
            return []
        
        # Find matching pairs
        pairs = []
        for src_path in src_files:
            # Construct reference path
            base_name = src_path.name[:-len(src_ext)]
            ref_path = src_path.parent / (base_name + ref_ext)
            
            if ref_path.exists():
                pairs.append((src_path, ref_path))
            else:
                logger.debug(f"No matching reference for: {src_path.name}")
        
        logger.info(f"Found {len(pairs)} matching subtitle pairs")
        return pairs
    
    def process_pair(self, src_path: Path, ref_path: Path) -> bool:
        """Process a single subtitle pair"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing subtitle pair:")
        logger.info(f"  Source: {src_path.name}")
        logger.info(f"  Reference: {ref_path.name}")
        
        try:
            # Load subtitles
            source = self.manager.load_subtitle(src_path)
            reference = self.manager.load_subtitle(ref_path)
            
            if not source.events or not reference.events:
                logger.warning("One or both files have no events. Skipping.")
                return False
            
            # Get alignment points
            if self.args.interactive:
                aligner = InteractiveAligner(source, reference)
                source_idx, ref_idx = aligner.run()
                
                if source_idx is None or ref_idx is None:
                    logger.info("Alignment cancelled by user")
                    return False
            else:
                # Automatic mode: use earliest events
                source_idx = 0
                ref_idx = 0
                
                logger.info("Using automatic alignment (earliest events)")
            
            # Perform alignment
            aligned = self.manager.align_subtitles(source, reference, source_idx, ref_idx)
            
            # Save aligned subtitle
            out_path = src_path if not self.args.output_suffix else \
                      src_path.parent / (src_path.stem + self.args.output_suffix + src_path.suffix)
            
            self.manager.save_subtitle(aligned, out_path, create_backup=not self.args.no_backup)
            
            logger.info(f"Successfully aligned and saved: {out_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process pair: {e}")
            if self.args.debug:
                import traceback
                traceback.print_exc()
            return False
    
    def run(self):
        """Run the application"""
        logger.info("Enhanced Subtitle Realignment Tool")
        logger.info("==================================")
        
        # Find subtitle pairs
        pairs = self.find_subtitle_pairs()
        
        if not pairs:
            logger.error("No matching subtitle pairs found")
            sys.exit(1)
        
        # Process pairs
        success_count = 0
        for src_path, ref_path in pairs:
            if self.process_pair(src_path, ref_path):
                success_count += 1
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing complete!")
        logger.info(f"  Total pairs: {len(pairs)}")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failed: {len(pairs) - success_count}")

# ----------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------
def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Enhanced subtitle realignment tool with interactive mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Automatic alignment of Chinese to English subtitles
  %(prog)s --src-ext .zh.ass --ref-ext .en.ass
  
  # Interactive alignment with custom output suffix
  %(prog)s --src-ext .chs.srt --ref-ext .eng.srt --interactive --output-suffix .aligned
  
  # Process specific folder without creating backups
  %(prog)s --folder /path/to/subtitles --src-ext .cn.ass --ref-ext .en.ass --no-backup
        """
    )
    
    # Required arguments
    parser.add_argument("--src-ext", required=True,
                       help="Source subtitle extension (e.g., .zh.ass, .cn.srt)")
    parser.add_argument("--ref-ext", required=True,
                       help="Reference subtitle extension (e.g., .en.ass, .en.srt)")
    
    # Optional arguments
    parser.add_argument("--folder", default=".",
                       help="Folder to scan for subtitle pairs (default: current directory)")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Enable interactive mode for manual alignment selection")
    parser.add_argument("--output-suffix", default="",
                       help="Suffix to add to output files (e.g., .aligned)")
    parser.add_argument("--no-backup", action="store_true",
                       help="Don't create backups before modifying files")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Run application
    app = SubtitleRealignApp(args)
    
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
