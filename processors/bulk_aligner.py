#!/usr/bin/env python3
"""
Bulk Subtitle Aligner

This module provides functionality for bulk alignment of subtitle files without combining them.
It aligns timing of source language subtitles to match reference language subtitles while
keeping the files separate.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass

from utils.logging_config import get_logger
from processors.realigner import SubtitleRealigner
from processors.merger import BilingualMerger
from core.subtitle_formats import SubtitleFormatFactory

logger = get_logger(__name__)


@dataclass
class AlignmentPair:
    """Represents a pair of source and reference subtitle files for alignment."""
    source_file: Path
    reference_file: Path
    output_file: Path
    backup_file: Optional[Path] = None


class BulkSubtitleAligner:
    """Handles bulk alignment of subtitle files without combining them."""
    
    def __init__(self, auto_confirm: bool = False, create_backup: bool = True):
        """
        Initialize the bulk subtitle aligner.
        
        Args:
            auto_confirm: Skip interactive confirmations for fully automated processing
            create_backup: Create .bak backup files before modifying originals
        """
        self.auto_confirm = auto_confirm
        self.create_backup = create_backup
        self.realigner = SubtitleRealigner()
    
    def align_directory(self, source_dir: Path, source_pattern: str, 
                       reference_pattern: str, reference_dir: Optional[Path] = None,
                       output_dir: Optional[Path] = None,
                       alignment_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Align subtitle files in a directory.
        
        Args:
            source_dir: Directory containing source subtitle files
            source_pattern: Pattern to match source files (e.g., "*.zh.srt")
            reference_pattern: Pattern to match reference files (e.g., "*.en.srt")
            reference_dir: Directory containing reference files (defaults to source_dir)
            output_dir: Output directory (defaults to in-place modification)
            alignment_options: Options for alignment algorithm
            
        Returns:
            Dictionary with processing results
        """
        if reference_dir is None:
            reference_dir = source_dir
        
        # Find alignment pairs
        alignment_pairs = self._find_alignment_pairs(
            source_dir, source_pattern, reference_dir, reference_pattern, output_dir
        )
        
        if not alignment_pairs:
            logger.warning("No matching subtitle pairs found for alignment")
            return {
                'total': 0, 'successful': 0, 'failed': 0, 'skipped': 0,
                'errors': [], 'aligned_files': []
            }
        
        logger.info(f"Found {len(alignment_pairs)} subtitle pairs for alignment")
        
        results = {
            'total': len(alignment_pairs),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'aligned_files': []
        }
        
        # Process each alignment pair
        for i, pair in enumerate(alignment_pairs, 1):
            print(f"\n{'='*80}")
            print(f"BULK ALIGNMENT: PAIR {i}/{len(alignment_pairs)}")
            print(f"{'='*80}")
            print(f"Source: {pair.source_file.name}")
            print(f"Reference: {pair.reference_file.name}")
            print(f"Output: {pair.output_file}")
            
            # Interactive confirmation (unless auto-confirm is enabled)
            if not self.auto_confirm:
                print(f"\nOptions:")
                print(f"  y = Yes, align this pair")
                print(f"  n = No, skip this pair")
                print(f"  q = Quit bulk alignment")
                
                try:
                    choice = input(f"\nAlign this pair? (y/n/q): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print(f"\nBulk alignment interrupted by user")
                    break
                
                if choice == 'q':
                    print(f"Bulk alignment stopped by user")
                    break
                elif choice == 'n':
                    print(f"⏭️ Skipping {pair.source_file.name}")
                    results['skipped'] += 1
                    continue
                elif choice != 'y':
                    print(f"Invalid choice '{choice}', skipping pair")
                    results['skipped'] += 1
                    continue
            
            # Perform alignment
            success = self._align_pair(pair, alignment_options)
            
            if success:
                results['successful'] += 1
                results['aligned_files'].append({
                    'source': str(pair.source_file),
                    'reference': str(pair.reference_file),
                    'output': str(pair.output_file)
                })
                print(f"✅ Successfully aligned: {pair.source_file.name}")
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed to align: {pair.source_file.name}")
                print(f"❌ Failed to align: {pair.source_file.name}")
        
        return results
    
    def _find_alignment_pairs(self, source_dir: Path, source_pattern: str,
                             reference_dir: Path, reference_pattern: str,
                             output_dir: Optional[Path]) -> List[AlignmentPair]:
        """Find matching pairs of source and reference subtitle files."""
        pairs = []
        
        # Find source files
        source_files = list(source_dir.glob(source_pattern))
        if not source_files:
            logger.warning(f"No source files found matching pattern '{source_pattern}' in {source_dir}")
            return pairs
        
        # Find reference files
        reference_files = list(reference_dir.glob(reference_pattern))
        if not reference_files:
            logger.warning(f"No reference files found matching pattern '{reference_pattern}' in {reference_dir}")
            return pairs
        
        # Create mapping of base names to files
        ref_map = {}
        for ref_file in reference_files:
            base_name = self._get_base_name(ref_file)
            ref_map[base_name] = ref_file
        
        # Match source files with reference files
        for source_file in source_files:
            base_name = self._get_base_name(source_file)
            
            if base_name in ref_map:
                reference_file = ref_map[base_name]
                
                # Determine output file
                if output_dir:
                    output_file = output_dir / source_file.name
                else:
                    output_file = source_file  # In-place modification
                
                # Determine backup file
                backup_file = None
                if self.create_backup and output_file == source_file:
                    backup_file = source_file.with_suffix(source_file.suffix + '.bak')
                
                pairs.append(AlignmentPair(
                    source_file=source_file,
                    reference_file=reference_file,
                    output_file=output_file,
                    backup_file=backup_file
                ))
            else:
                logger.debug(f"No matching reference file found for {source_file.name}")
        
        return pairs
    
    def _get_base_name(self, file_path: Path) -> str:
        """Extract base name for matching files (removes language extensions)."""
        name = file_path.stem
        
        # Remove common language suffixes
        language_suffixes = ['.zh', '.en', '.chi', '.eng', '.chinese', '.english']
        for suffix in language_suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        return name
    
    def _align_pair(self, pair: AlignmentPair, alignment_options: Optional[Dict[str, Any]]) -> bool:
        """Align a single pair of subtitle files."""
        try:
            # Create backup if needed
            if pair.backup_file and pair.output_file == pair.source_file:
                logger.info(f"Creating backup: {pair.backup_file}")
                shutil.copy2(pair.source_file, pair.backup_file)
            
            # Load subtitle files
            source_sub = SubtitleFormatFactory.parse_file(pair.source_file)
            reference_sub = SubtitleFormatFactory.parse_file(pair.reference_file)
            
            if not source_sub or not reference_sub:
                logger.error(f"Failed to load subtitle files")
                return False
            
            # Create merger with alignment options for advanced alignment
            if alignment_options and alignment_options.get('auto_align'):
                merger = BilingualMerger(**alignment_options)
                
                # Use the enhanced alignment from merger
                aligned_events1, aligned_events2, offset = merger._perform_global_synchronization(
                    source_sub.events, reference_sub.events
                )
                
                # Use the aligned source events
                source_sub.events = aligned_events1
                
            else:
                # Use basic realignment
                aligned_events = self.realigner.realign_subtitles(
                    source_sub.events, reference_sub.events
                )
                source_sub.events = aligned_events
            
            # Save aligned subtitle
            source_sub.save(pair.output_file)
            logger.info(f"Saved aligned subtitle: {pair.output_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error aligning {pair.source_file.name}: {e}")
            
            # Restore from backup if alignment failed and we created a backup
            if pair.backup_file and pair.backup_file.exists() and pair.output_file == pair.source_file:
                try:
                    shutil.copy2(pair.backup_file, pair.source_file)
                    logger.info(f"Restored from backup due to alignment failure")
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")
            
            return False
