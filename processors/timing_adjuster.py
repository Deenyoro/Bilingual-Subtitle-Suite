"""
Timing adjustment processor for subtitle files.

This module provides functionality for shifting subtitle timing by a fixed offset
or adjusting the first subtitle line to start at a specific timestamp.
"""

import re
from pathlib import Path
from typing import Optional, Union
from core.subtitle_formats import SubtitleFormatFactory, SubtitleFile, SubtitleEvent
from core.timing_utils import TimeConverter
from utils.logging_config import get_logger
from utils.backup_manager import BackupManager

logger = get_logger(__name__)


class TimingAdjuster:
    """Handles timing adjustments for subtitle files."""
    
    def __init__(self, create_backup: bool = True):
        """
        Initialize the timing adjuster.
        
        Args:
            create_backup: Whether to create backup files before modification
        """
        self.create_backup = create_backup
        self.backup_manager = BackupManager() if create_backup else None
    
    def adjust_by_offset(self, input_path: Path, offset_ms: int, 
                        output_path: Optional[Path] = None) -> bool:
        """
        Adjust subtitle timing by a fixed offset.
        
        Args:
            input_path: Path to input subtitle file
            offset_ms: Offset in milliseconds (positive = delay, negative = advance)
            output_path: Path for output file (if None, overwrites input)
            
        Returns:
            True if adjustment was successful
            
        Example:
            >>> adjuster = TimingAdjuster()
            >>> success = adjuster.adjust_by_offset(Path("sub.srt"), -2470)
        """
        try:
            # Parse input file
            subtitle_file = SubtitleFormatFactory.parse_file(input_path)
            logger.info(f"Loaded {len(subtitle_file.events)} events from {input_path.name}")
            
            # Create backup if requested and overwriting
            if self.create_backup and (output_path is None or output_path == input_path):
                self.backup_manager.create_backup(input_path)
            
            # Adjust timing for all events
            adjusted_events = []
            for event in subtitle_file.events:
                adjusted_start = event.start + (offset_ms / 1000.0)
                adjusted_end = event.end + (offset_ms / 1000.0)
                
                # Ensure no negative timestamps
                if adjusted_start < 0:
                    adjustment_needed = -adjusted_start
                    adjusted_start = 0
                    adjusted_end = max(0, adjusted_end + adjustment_needed)
                    logger.warning(f"Adjusted negative timestamp to 0:00:00,000")
                
                adjusted_events.append(SubtitleEvent(
                    start=adjusted_start,
                    end=adjusted_end,
                    text=event.text
                ))
            
            # Create output file
            output_file = SubtitleFile(
                path=output_path or input_path,
                format=subtitle_file.format,
                events=adjusted_events,
                encoding=subtitle_file.encoding,
                styles=getattr(subtitle_file, 'styles', None),
                script_info=getattr(subtitle_file, 'script_info', None)
            )
            
            # Write output
            SubtitleFormatFactory.write_file(output_file, output_path or input_path)
            
            offset_direction = "delayed" if offset_ms > 0 else "advanced"
            logger.info(f"Successfully {offset_direction} {len(adjusted_events)} events by "
                       f"{abs(offset_ms)}ms in {(output_path or input_path).name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to adjust timing by offset: {e}")
            return False
    
    def adjust_first_line_to(self, input_path: Path, target_timestamp: str,
                           output_path: Optional[Path] = None) -> bool:
        """
        Adjust subtitle timing so the first line starts at the specified timestamp.
        
        Args:
            input_path: Path to input subtitle file
            target_timestamp: Target timestamp for first line (e.g., "00:00:50,983")
            output_path: Path for output file (if None, overwrites input)
            
        Returns:
            True if adjustment was successful
            
        Example:
            >>> adjuster = TimingAdjuster()
            >>> success = adjuster.adjust_first_line_to(Path("sub.srt"), "00:00:50,983")
        """
        try:
            # Parse input file
            subtitle_file = SubtitleFormatFactory.parse_file(input_path)
            logger.info(f"Loaded {len(subtitle_file.events)} events from {input_path.name}")
            
            if not subtitle_file.events:
                logger.error("No subtitle events found in file")
                return False
            
            # Get first event's current start time
            first_event = subtitle_file.events[0]
            current_start_seconds = first_event.start
            
            # Parse target timestamp
            target_start_seconds = TimeConverter.time_to_seconds(target_timestamp, 'srt')
            
            # Calculate offset needed
            offset_seconds = target_start_seconds - current_start_seconds
            offset_ms = int(offset_seconds * 1000)
            
            logger.info(f"First line currently starts at {TimeConverter.seconds_to_time(current_start_seconds, 'srt')}")
            logger.info(f"Target start time: {target_timestamp}")
            logger.info(f"Calculated offset: {offset_ms}ms")
            
            # Use the offset method to apply the adjustment
            return self.adjust_by_offset(input_path, offset_ms, output_path)
            
        except Exception as e:
            logger.error(f"Failed to adjust first line timing: {e}")
            return False
    
    def parse_offset_string(self, offset_str: str) -> int:
        """
        Parse offset string to milliseconds.
        
        Args:
            offset_str: Offset string (e.g., "2.5s", "-1500ms", "00:00:02,500")
            
        Returns:
            Offset in milliseconds
            
        Raises:
            ValueError: If offset string format is invalid
        """
        offset_str = offset_str.strip()
        
        # Handle timestamp format (HH:MM:SS,mmm or HH:MM:SS.mmm)
        if ':' in offset_str:
            # Convert timestamp to seconds, then to milliseconds
            seconds = TimeConverter.time_to_seconds(offset_str, 'srt')
            return int(seconds * 1000)
        
        # Handle milliseconds (e.g., "1500ms", "-2470ms")
        if offset_str.lower().endswith('ms'):
            return int(offset_str[:-2])
        
        # Handle seconds (e.g., "2.5s", "-1.5s")
        if offset_str.lower().endswith('s'):
            return int(float(offset_str[:-1]) * 1000)
        
        # Handle plain numbers (assume milliseconds)
        try:
            return int(offset_str)
        except ValueError:
            pass
        
        # Handle decimal numbers (assume seconds)
        try:
            return int(float(offset_str) * 1000)
        except ValueError:
            pass
        
        raise ValueError(f"Invalid offset format: {offset_str}. "
                        f"Supported formats: '1500ms', '2.5s', '00:00:02,500', or plain numbers")
