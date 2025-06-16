#!/usr/bin/env python3
"""
Test script to verify the enhanced subtitle alignment fixes.

This script tests the alignment of Chinese external subtitles with embedded English subtitles
from Made in Abyss episodes, focusing on handling large timing offsets.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from processors.merger import BilingualMerger
from core.video_containers import VideoContainerHandler
from utils.logging_config import setup_logging, get_logger

# Setup logging
setup_logging(level='INFO')
logger = get_logger(__name__)

def test_alignment_with_made_in_abyss():
    """Test alignment with Made in Abyss S02E01 episode."""
    
    # Test file paths
    video_file = Path("Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].mkv")
    chinese_file = Path("Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt")
    output_file = Path("Season 02/Made in Abyss S02E01-TEST-ALIGNMENT-FIX.zh-en.srt")
    
    if not video_file.exists():
        logger.error(f"Video file not found: {video_file}")
        return False
        
    if not chinese_file.exists():
        logger.error(f"Chinese subtitle file not found: {chinese_file}")
        return False
    
    logger.info("="*80)
    logger.info("TESTING ENHANCED SUBTITLE ALIGNMENT")
    logger.info("="*80)
    logger.info(f"Video: {video_file.name}")
    logger.info(f"Chinese subtitles: {chinese_file.name}")
    logger.info(f"Output: {output_file.name}")
    logger.info("")
    
    try:
        # Create merger with enhanced alignment enabled
        merger = BilingualMerger(
            auto_align=True,  # Enable automatic alignment using advanced methods
            use_translation=True,  # Enable translation-assisted alignment
            alignment_threshold=0.4,  # Even lower threshold for initial detection
            sync_strategy="translation",  # Use translation strategy
            enable_mixed_realignment=True,  # Enable enhanced realignment for mixed tracks
            gap_threshold=0.1,
            translation_api_key=None  # Use environment variable
        )

        logger.info("🔧 Merger configured with enhanced alignment settings:")
        logger.info(f"  - Auto alignment: ENABLED")
        logger.info(f"  - Translation assistance: ENABLED")
        logger.info(f"  - Mixed realignment: ENABLED")
        logger.info(f"  - Alignment threshold: 0.4")
        logger.info(f"  - Sync strategy: translation")

        # Check if translation service is available
        if merger.translation_service:
            logger.info(f"  - Translation service: AVAILABLE")
        else:
            logger.warning(f"  - Translation service: NOT AVAILABLE")
        logger.info("")
        
        # Analyze video container first
        logger.info("📹 Analyzing video container...")
        container_handler = VideoContainerHandler()
        subtitle_tracks = container_handler.list_subtitle_tracks(video_file)

        logger.info(f"Found {len(subtitle_tracks)} subtitle tracks:")
        for i, track in enumerate(subtitle_tracks):
            logger.info(f"  Track {track.track_id}: {track.language} ({track.codec})")

        # Find English embedded track
        english_track_obj = None
        english_track_id = None
        for track in subtitle_tracks:
            if track.language.lower() in ['en', 'eng', 'english']:
                english_track_obj = track
                english_track_id = track.track_id
                break

        if english_track_obj is None:
            logger.warning("No English embedded track found, using first track")
            if subtitle_tracks:
                english_track_obj = subtitle_tracks[0]
                english_track_id = subtitle_tracks[0].track_id
            else:
                logger.error("No subtitle tracks found!")
                return False

        logger.info(f"Using embedded English track: {english_track_id} ({english_track_obj.language})")
        logger.info("")

        # First, extract clean embedded English subtitles for reference
        logger.info("📤 Extracting clean embedded English subtitles...")
        clean_english_file = Path("Season 02/Made in Abyss S02E01-CLEAN-ENGLISH.srt")

        # Extract embedded English track
        success_extract = container_handler.extract_subtitle_track(
            video_file, english_track_obj, clean_english_file
        )

        if not success_extract:
            logger.error("Failed to extract embedded English track")
            return False

        logger.info(f"✅ Clean English subtitles extracted: {clean_english_file}")

        # Show first few entries of clean English
        if clean_english_file.exists():
            with open(clean_english_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.strip().split('\n')[:30]  # First 30 lines
                logger.info("Clean English subtitle sample:")
                for line in lines:
                    if line.strip():
                        logger.info(f"  {line}")
                logger.info("")

        # Perform merge with explicit track specification
        logger.info("🔄 Starting enhanced alignment merge...")
        success = merger.process_video(
            video_path=video_file,
            chinese_sub=chinese_file,  # External Chinese file
            english_track=str(english_track_id),     # Embedded English track ID
            output_path=output_file,
            output_format="srt"
        )
        
        if success:
            logger.info("✅ ALIGNMENT TEST SUCCESSFUL!")
            logger.info(f"Output file created: {output_file}")
            
            # Verify output file
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.strip().split('\n')
                    logger.info(f"Output file contains {len(lines)} lines")
                    
                    # Show first few entries
                    logger.info("\nFirst few entries:")
                    entry_count = 0
                    for i, line in enumerate(lines[:50]):  # Show first 50 lines
                        if line.strip().isdigit():
                            entry_count += 1
                            if entry_count <= 3:  # Show first 3 entries
                                logger.info(f"Entry {entry_count}:")
                                # Show next 3 lines (timing and text)
                                for j in range(1, 4):
                                    if i + j < len(lines):
                                        logger.info(f"  {lines[i + j]}")
                                logger.info("")
            
            return True
        else:
            logger.error("❌ ALIGNMENT TEST FAILED!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    logger.info("Enhanced Subtitle Alignment Test")
    logger.info("=" * 50)
    
    # Test the alignment
    success = test_alignment_with_made_in_abyss()
    
    if success:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error("\n💥 Tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
