#!/usr/bin/env python3
"""
Backup File Manager

This module provides utilities for managing backup files created during subtitle processing.
"""

import os
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from utils.logging_config import get_logger

logger = get_logger(__name__)


class BackupManager:
    """Manages backup files for subtitle processing operations."""
    
    def __init__(self):
        """Initialize the backup manager."""
        pass
    
    def create_backup(self, original_file: Path, backup_suffix: str = '.bak') -> Optional[Path]:
        """
        Create a backup of the original file.
        
        Args:
            original_file: Path to the original file
            backup_suffix: Suffix to add to backup file (default: '.bak')
            
        Returns:
            Path to backup file if successful, None otherwise
        """
        if not original_file.exists():
            logger.error(f"Original file not found: {original_file}")
            return None
        
        backup_file = original_file.with_suffix(original_file.suffix + backup_suffix)
        
        try:
            # Copy the original file to backup
            import shutil
            shutil.copy2(original_file, backup_file)
            logger.info(f"Created backup: {backup_file}")
            return backup_file
            
        except Exception as e:
            logger.error(f"Failed to create backup {backup_file}: {e}")
            return None
    
    def restore_from_backup(self, backup_file: Path, target_file: Optional[Path] = None) -> bool:
        """
        Restore a file from its backup.
        
        Args:
            backup_file: Path to the backup file
            target_file: Target file to restore to (defaults to original file)
            
        Returns:
            True if restoration was successful, False otherwise
        """
        if not backup_file.exists():
            logger.error(f"Backup file not found: {backup_file}")
            return False
        
        # Determine target file
        if target_file is None:
            # Remove .bak suffix to get original filename
            if backup_file.suffix == '.bak':
                target_file = backup_file.with_suffix('')
            else:
                logger.error(f"Cannot determine original filename from backup: {backup_file}")
                return False
        
        try:
            import shutil
            shutil.copy2(backup_file, target_file)
            logger.info(f"Restored from backup: {backup_file} -> {target_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore from backup {backup_file}: {e}")
            return False
    
    def find_backup_files(self, directory: Path, recursive: bool = False, 
                         older_than_days: Optional[int] = None) -> List[Path]:
        """
        Find backup files in a directory.
        
        Args:
            directory: Directory to search
            recursive: Search subdirectories recursively
            older_than_days: Only include files older than N days
            
        Returns:
            List of backup file paths
        """
        backup_files = []
        
        # Define backup patterns
        backup_patterns = ['*.bak', '*.backup', '*.orig']
        
        # Search for backup files
        for pattern in backup_patterns:
            if recursive:
                files = directory.rglob(pattern)
            else:
                files = directory.glob(pattern)
            
            for file_path in files:
                if file_path.is_file():
                    # Check age if specified
                    if older_than_days is not None:
                        age_days = self.get_file_age_days(file_path)
                        if age_days >= older_than_days:
                            backup_files.append(file_path)
                    else:
                        backup_files.append(file_path)
        
        return sorted(backup_files)
    
    def get_file_age_days(self, file_path: Path) -> int:
        """
        Get the age of a file in days.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Age in days
        """
        try:
            file_time = file_path.stat().st_mtime
            current_time = time.time()
            age_seconds = current_time - file_time
            age_days = int(age_seconds / (24 * 3600))
            return age_days
        except Exception as e:
            logger.error(f"Failed to get file age for {file_path}: {e}")
            return 0
    
    def cleanup_backups(self, backup_files: List[Path]) -> int:
        """
        Delete backup files.
        
        Args:
            backup_files: List of backup files to delete
            
        Returns:
            Number of files successfully deleted
        """
        deleted_count = 0
        
        for backup_file in backup_files:
            try:
                backup_file.unlink()
                logger.info(f"Deleted backup file: {backup_file}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete backup file {backup_file}: {e}")
        
        return deleted_count
    
    def get_backup_info(self, directory: Path, recursive: bool = False) -> dict:
        """
        Get information about backup files in a directory.
        
        Args:
            directory: Directory to analyze
            recursive: Search subdirectories recursively
            
        Returns:
            Dictionary with backup file statistics
        """
        backup_files = self.find_backup_files(directory, recursive)
        
        if not backup_files:
            return {
                'total_files': 0,
                'total_size': 0,
                'oldest_file': None,
                'newest_file': None,
                'average_age_days': 0
            }
        
        # Calculate statistics
        total_size = 0
        file_ages = []
        oldest_file = backup_files[0]
        newest_file = backup_files[0]
        oldest_time = backup_files[0].stat().st_mtime
        newest_time = backup_files[0].stat().st_mtime
        
        for backup_file in backup_files:
            # Size
            size = backup_file.stat().st_size
            total_size += size
            
            # Age
            age_days = self.get_file_age_days(backup_file)
            file_ages.append(age_days)
            
            # Oldest/newest
            file_time = backup_file.stat().st_mtime
            if file_time < oldest_time:
                oldest_time = file_time
                oldest_file = backup_file
            if file_time > newest_time:
                newest_time = file_time
                newest_file = backup_file
        
        average_age = sum(file_ages) / len(file_ages) if file_ages else 0
        
        return {
            'total_files': len(backup_files),
            'total_size': total_size,
            'oldest_file': oldest_file,
            'newest_file': newest_file,
            'average_age_days': round(average_age, 1)
        }
    
    def suggest_cleanup(self, directory: Path, recursive: bool = False) -> dict:
        """
        Suggest backup files for cleanup based on age and size.
        
        Args:
            directory: Directory to analyze
            recursive: Search subdirectories recursively
            
        Returns:
            Dictionary with cleanup suggestions
        """
        backup_files = self.find_backup_files(directory, recursive)
        
        if not backup_files:
            return {
                'old_files': [],
                'large_files': [],
                'duplicate_backups': [],
                'total_savings': 0
            }
        
        # Find old files (older than 30 days)
        old_files = []
        for backup_file in backup_files:
            age_days = self.get_file_age_days(backup_file)
            if age_days > 30:
                old_files.append(backup_file)
        
        # Find large files (larger than 10MB)
        large_files = []
        for backup_file in backup_files:
            size = backup_file.stat().st_size
            if size > 10 * 1024 * 1024:  # 10MB
                large_files.append(backup_file)
        
        # Find potential duplicate backups (same base name, multiple .bak files)
        duplicate_backups = []
        base_names = {}
        for backup_file in backup_files:
            base_name = backup_file.stem
            if base_name.endswith('.bak'):
                base_name = base_name[:-4]  # Remove .bak
            
            if base_name not in base_names:
                base_names[base_name] = []
            base_names[base_name].append(backup_file)
        
        for base_name, files in base_names.items():
            if len(files) > 1:
                # Keep the newest, suggest others for cleanup
                files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                duplicate_backups.extend(files[1:])  # All except the newest
        
        # Calculate total potential savings
        cleanup_candidates = set(old_files + large_files + duplicate_backups)
        total_savings = sum(f.stat().st_size for f in cleanup_candidates)
        
        return {
            'old_files': old_files,
            'large_files': large_files,
            'duplicate_backups': duplicate_backups,
            'total_savings': total_savings
        }
