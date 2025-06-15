"""
Time conversion and manipulation utilities for subtitle processing.

This module provides functions for:
- Converting between different time formats (SRT, ASS, VTT)
- Time arithmetic and manipulation
- Subtitle timing optimization
"""

import re
from typing import Union
from utils.logging_config import get_logger

logger = get_logger(__name__)


class TimeConverter:
    """Handles time format conversions and manipulations for subtitles."""
    
    @staticmethod
    def time_to_seconds(time_str: str, format_type: str = 'srt') -> float:
        """
        Convert time string to seconds based on format type.
        
        Args:
            time_str: Time string to convert
            format_type: Format type ('srt', 'ass', or 'vtt')
            
        Returns:
            Time in seconds as float
            
        Raises:
            ValueError: If time string format is invalid
            
        Example:
            >>> seconds = TimeConverter.time_to_seconds("01:23:45,678", "srt")
            >>> print(f"Time in seconds: {seconds}")
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
            raise ValueError(f"Invalid time format: {time_str}")
    
    @staticmethod
    def seconds_to_time(seconds: float, format_type: str = 'srt') -> str:
        """
        Convert seconds to time string based on format type.
        
        Args:
            seconds: Time in seconds
            format_type: Output format ('srt', 'ass', or 'vtt')
            
        Returns:
            Formatted time string
            
        Example:
            >>> time_str = TimeConverter.seconds_to_time(3825.678, "srt")
            >>> print(f"SRT format: {time_str}")  # "01:03:45,678"
        """
        if seconds < 0:
            seconds = 0
            
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
    
    @staticmethod
    def milliseconds_to_readable(ms: int) -> str:
        """
        Convert milliseconds to readable format (HH:MM:SS.mmm).
        
        Args:
            ms: Time in milliseconds
            
        Returns:
            Readable time string
            
        Example:
            >>> readable = TimeConverter.milliseconds_to_readable(3825678)
            >>> print(readable)  # "01:03:45.678"
        """
        if ms < 0:
            ms = 0
        hours = ms // 3600000
        ms %= 3600000
        minutes = ms // 60000
        ms %= 60000
        seconds = ms // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    @staticmethod
    def shift_time(time_str: str, shift_ms: int, format_type: str = 'srt') -> str:
        """
        Shift a time string by the specified milliseconds.
        
        Args:
            time_str: Original time string
            shift_ms: Milliseconds to shift (positive = forward, negative = backward)
            format_type: Time format type
            
        Returns:
            Shifted time string
            
        Example:
            >>> shifted = TimeConverter.shift_time("01:00:00,000", 5000, "srt")
            >>> print(shifted)  # "01:00:05,000"
        """
        # Convert to seconds, apply shift, convert back
        seconds = TimeConverter.time_to_seconds(time_str, format_type)
        shifted_seconds = seconds + (shift_ms / 1000.0)
        
        # Ensure no negative times
        if shifted_seconds < 0:
            shifted_seconds = 0
            
        return TimeConverter.seconds_to_time(shifted_seconds, format_type)
    
    @staticmethod
    def parse_srt_timestamp(timestamp_line: str) -> tuple[float, float]:
        """
        Parse SRT timestamp line to get start and end times in seconds.
        
        Args:
            timestamp_line: SRT timestamp line (e.g., "00:01:23,456 --> 00:01:26,789")
            
        Returns:
            Tuple of (start_seconds, end_seconds)
            
        Raises:
            ValueError: If timestamp format is invalid
            
        Example:
            >>> start, end = TimeConverter.parse_srt_timestamp("00:01:23,456 --> 00:01:26,789")
            >>> print(f"Duration: {end - start} seconds")
        """
        timestamp_pattern = r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})'
        match = re.match(timestamp_pattern, timestamp_line.strip())
        
        if not match:
            raise ValueError(f"Invalid SRT timestamp format: {timestamp_line}")
        
        start_str, end_str = match.groups()
        start_seconds = TimeConverter.time_to_seconds(start_str, 'srt')
        end_seconds = TimeConverter.time_to_seconds(end_str, 'srt')
        
        return start_seconds, end_seconds
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Format duration in seconds to human-readable string.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Human-readable duration string
            
        Example:
            >>> duration = TimeConverter.format_duration(3825.5)
            >>> print(duration)  # "1h 3m 45.5s"
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds:.1f}s"
        else:
            hours = int(seconds // 3600)
            remaining_seconds = seconds % 3600
            minutes = int(remaining_seconds // 60)
            remaining_seconds = remaining_seconds % 60
            return f"{hours}h {minutes}m {remaining_seconds:.1f}s"
