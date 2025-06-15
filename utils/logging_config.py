"""
Logging configuration for the subtitle processing application.

This module provides centralized logging setup with colored output,
different log levels, and proper formatting for both console and file output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from .constants import DEFAULT_LOG_FORMAT, DEFAULT_LOG_DATE_FORMAT


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log message with colors
        """
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    use_colors: bool = True,
    logger_name: str = "subtitle_processor"
) -> logging.Logger:
    """
    Set up logging with appropriate level and formatting.
    
    Args:
        level: Logging level (e.g., logging.DEBUG, logging.INFO)
        log_file: Optional path to log file for file output
        use_colors: Whether to use colored output for console
        logger_name: Name for the logger instance
        
    Returns:
        Configured logger instance
        
    Example:
        >>> logger = setup_logging(logging.DEBUG, Path("app.log"))
        >>> logger.info("Application started")
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Choose formatter based on terminal capability and user preference
    if use_colors and sys.stdout.isatty():
        console_formatter = ColoredFormatter(
            DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_LOG_DATE_FORMAT
        )
    else:
        console_formatter = logging.Formatter(
            DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_LOG_DATE_FORMAT
        )
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if log file specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        file_formatter = logging.Formatter(
            DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_LOG_DATE_FORMAT
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "subtitle_processor") -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
        
    Note:
        This assumes setup_logging() has already been called.
    """
    return logging.getLogger(name)


def set_log_level(logger: logging.Logger, level: int) -> None:
    """
    Set the log level for a logger and all its handlers.
    
    Args:
        logger: Logger instance to modify
        level: New logging level
        
    Example:
        >>> logger = get_logger()
        >>> set_log_level(logger, logging.DEBUG)
    """
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
