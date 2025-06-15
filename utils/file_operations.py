"""
File operations and backup utilities for subtitle processing.

This module provides safe file operations including:
- Backup creation with timestamps
- Safe file reading/writing with encoding detection
- Directory operations and file discovery
- Temporary file management
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Generator
from .constants import BACKUP_DIR_NAME, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from .logging_config import get_logger

logger = get_logger(__name__)


class FileHandler:
    """Handles file operations with proper error handling and logging."""
    
    @staticmethod
    def create_backup(file_path: Path, backup_dir: Optional[Path] = None) -> Path:
        """
        Create a backup of the file with timestamp.
        
        Args:
            file_path: Path to the file to backup
            backup_dir: Optional custom backup directory
            
        Returns:
            Path to the created backup file
            
        Raises:
            IOError: If backup creation fails
            
        Example:
            >>> backup_path = FileHandler.create_backup(Path("subtitle.srt"))
            >>> print(f"Backup created at: {backup_path}")
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Determine backup directory
        if backup_dir is None:
            backup_dir = file_path.parent / BACKUP_DIR_NAME
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = backup_dir / backup_name
        
        try:
            shutil.copy2(file_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup for {file_path}: {e}")
            raise IOError(f"Backup creation failed: {e}")
    
    @staticmethod
    def safe_write(file_path: Path, content: str, encoding: str = 'utf-8', 
                   create_backup: bool = True) -> None:
        """
        Safely write content to a file with optional backup.
        
        Args:
            file_path: Path to write to
            content: Content to write
            encoding: File encoding to use
            create_backup: Whether to create backup if file exists
            
        Raises:
            IOError: If write operation fails
            
        Example:
            >>> FileHandler.safe_write(Path("output.srt"), subtitle_content)
        """
        try:
            # Create backup if file exists and backup requested
            if create_backup and file_path.exists():
                FileHandler.create_backup(file_path)
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            with open(file_path, 'w', encoding=encoding, newline='\n') as f:
                f.write(content)
            
            logger.debug(f"Successfully wrote file: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            raise IOError(f"Write operation failed: {e}")
    
    @staticmethod
    def find_subtitle_files(directory: Path, recursive: bool = True) -> List[Path]:
        """
        Find all subtitle files in a directory.
        
        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            
        Returns:
            List of subtitle file paths
            
        Example:
            >>> files = FileHandler.find_subtitle_files(Path("/media/movies"))
            >>> print(f"Found {len(files)} subtitle files")
        """
        if not directory.exists() or not directory.is_dir():
            logger.warning(f"Directory not found or not a directory: {directory}")
            return []
        
        subtitle_files = []
        
        if recursive:
            pattern_func = directory.rglob
        else:
            pattern_func = directory.glob
        
        for ext in SUBTITLE_EXTENSIONS:
            pattern = f"*{ext}"
            subtitle_files.extend(pattern_func(pattern))
        
        # Sort for consistent ordering
        subtitle_files.sort()
        
        logger.debug(f"Found {len(subtitle_files)} subtitle files in {directory}")
        return subtitle_files
    
    @staticmethod
    def find_video_files(directory: Path, recursive: bool = True) -> List[Path]:
        """
        Find all video files in a directory.
        
        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            
        Returns:
            List of video file paths
            
        Example:
            >>> videos = FileHandler.find_video_files(Path("/media/movies"))
            >>> print(f"Found {len(videos)} video files")
        """
        if not directory.exists() or not directory.is_dir():
            logger.warning(f"Directory not found or not a directory: {directory}")
            return []
        
        video_files = []
        
        if recursive:
            pattern_func = directory.rglob
        else:
            pattern_func = directory.glob
        
        for ext in VIDEO_EXTENSIONS:
            pattern = f"*{ext}"
            video_files.extend(pattern_func(pattern))
        
        # Sort for consistent ordering
        video_files.sort()
        
        logger.debug(f"Found {len(video_files)} video files in {directory}")
        return video_files
    
    @staticmethod
    def find_matching_pairs(directory: Path, source_ext: str, 
                           reference_ext: str) -> List[Tuple[Path, Path]]:
        """
        Find matching subtitle pairs based on filename patterns.
        
        Args:
            directory: Directory to search
            source_ext: Source file extension (e.g., '.zh.srt')
            reference_ext: Reference file extension (e.g., '.en.srt')
            
        Returns:
            List of (source_path, reference_path) tuples
            
        Example:
            >>> pairs = FileHandler.find_matching_pairs(
            ...     Path("/media"), ".zh.srt", ".en.srt"
            ... )
            >>> print(f"Found {len(pairs)} matching pairs")
        """
        # Ensure extensions start with dot
        if not source_ext.startswith('.'):
            source_ext = '.' + source_ext
        if not reference_ext.startswith('.'):
            reference_ext = '.' + reference_ext
        
        # Find all source files
        source_pattern = f"*{source_ext}"
        source_files = list(directory.glob(source_pattern))
        
        pairs = []
        for source_path in source_files:
            # Construct reference path by replacing extension
            base_name = source_path.name[:-len(source_ext)]
            reference_name = base_name + reference_ext
            reference_path = source_path.parent / reference_name
            
            if reference_path.exists():
                pairs.append((source_path, reference_path))
            else:
                logger.debug(f"No matching reference for: {source_path.name}")
        
        logger.info(f"Found {len(pairs)} matching subtitle pairs")
        return pairs
