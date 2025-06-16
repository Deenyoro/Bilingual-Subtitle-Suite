#!/usr/bin/env python3
"""
Debug script to analyze and fix subtitle alignment issues.

This script focuses on understanding why the alignment is failing and testing fixes.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.subtitle_formats import SubtitleFormatFactory
from core.translation_service import get_translation_service
from utils.logging_config import setup_logging, get_logger

# Setup logging
setup_logging(level='DEBUG')
logger = get_logger(__name__)

def analyze_timing_offset():
    """Analyze the timing offset between Chinese and English subtitles."""
    
    # Load subtitle files
    chinese_file = Path("Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt")
    existing_bilingual = Path("Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh-en.srt")
    
    if not chinese_file.exists():
        logger.error(f"Chinese file not found: {chinese_file}")
        return False
        
    if not existing_bilingual.exists():
        logger.error(f"Existing bilingual file not found: {existing_bilingual}")
        return False
    
    logger.info("="*80)
    logger.info("SUBTITLE TIMING ANALYSIS")
    logger.info("="*80)
    
    # Parse Chinese subtitles
    chinese_subtitle_file = SubtitleFormatFactory.parse_file(chinese_file)
    chinese_events = chinese_subtitle_file.events
    logger.info(f"Chinese subtitles: {len(chinese_events)} events")

    # Parse existing bilingual file to extract English timing
    bilingual_subtitle_file = SubtitleFormatFactory.parse_file(existing_bilingual)
    bilingual_events = bilingual_subtitle_file.events
    logger.info(f"Existing bilingual: {len(bilingual_events)} events")
    
    # Show first few entries from each
    logger.info("\nFirst 5 Chinese entries:")
    for i, event in enumerate(chinese_events[:5]):
        logger.info(f"  [{i}] {event.start:.3f}s-{event.end:.3f}s: {event.text[:50]}...")
    
    logger.info("\nFirst 5 bilingual entries (mixed content):")
    for i, event in enumerate(bilingual_events[:5]):
        logger.info(f"  [{i}] {event.start:.3f}s-{event.end:.3f}s: {event.text[:50]}...")
    
    # Calculate timing differences
    logger.info("\nTiming offset analysis:")
    chinese_start = chinese_events[0].start if chinese_events else 0
    bilingual_start = bilingual_events[0].start if bilingual_events else 0
    offset = chinese_start - bilingual_start
    
    logger.info(f"Chinese first entry starts at: {chinese_start:.3f}s")
    logger.info(f"Bilingual first entry starts at: {bilingual_start:.3f}s")
    logger.info(f"Calculated offset: {offset:.3f}s")
    
    return True

def test_translation_alignment():
    """Test translation-based alignment with sample entries."""
    
    logger.info("="*80)
    logger.info("TRANSLATION-BASED ALIGNMENT TEST")
    logger.info("="*80)
    
    # Get translation service
    translation_service = get_translation_service()
    if not translation_service:
        logger.error("Translation service not available")
        return False
    
    # Sample Chinese and English texts for testing
    chinese_samples = [
        "咿嚕繆咿",
        "我在遇到妳之前",
        "有個一直在找的東西",
        "在這個羅盤…",
        "它就位在這個羅盤屹立的地方"
    ]
    
    english_samples = [
        "Irumyuui...",
        "You know,",
        "until I met you,",
        "there was something I'd been looking for.",
        "This compass..."
    ]
    
    logger.info("Testing translation accuracy:")
    
    for i, chinese_text in enumerate(chinese_samples):
        logger.info(f"\nSample {i+1}:")
        logger.info(f"  Chinese: {chinese_text}")
        
        # Translate Chinese to English
        try:
            result = translation_service.translate_text(chinese_text, target_language='en')
            if result:
                translated = result.translated_text
                logger.info(f"  Translated: {translated}")
                
                # Compare with actual English samples
                best_match_idx = -1
                best_similarity = 0.0
                
                for j, english_text in enumerate(english_samples):
                    # Simple similarity calculation
                    similarity = calculate_simple_similarity(translated.lower(), english_text.lower())
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match_idx = j
                
                if best_match_idx >= 0:
                    logger.info(f"  Best English match: {english_samples[best_match_idx]} (similarity: {best_similarity:.3f})")
                else:
                    logger.info(f"  No good English match found")
            else:
                logger.warning(f"  Translation failed")
                
        except Exception as e:
            logger.error(f"  Translation error: {e}")
    
    return True

def calculate_simple_similarity(text1: str, text2: str) -> float:
    """Calculate simple word-based similarity."""
    words1 = set(text1.split())
    words2 = set(text2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union) if union else 0.0

def test_enhanced_alignment_algorithm():
    """Test the enhanced alignment algorithm with real data."""
    
    logger.info("="*80)
    logger.info("ENHANCED ALIGNMENT ALGORITHM TEST")
    logger.info("="*80)
    
    # Load actual subtitle files
    chinese_file = Path("Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt")

    chinese_subtitle_file = SubtitleFormatFactory.parse_file(chinese_file)
    chinese_events = chinese_subtitle_file.events
    
    # Create mock English events with proper timing (simulate embedded track)
    mock_english_events = [
        type('Event', (), {'start': 6.86, 'end': 8.20, 'text': 'Irumyuui...'})(),
        type('Event', (), {'start': 8.84, 'end': 10.35, 'text': 'You know,'})(),
        type('Event', (), {'start': 10.35, 'end': 12.20, 'text': 'until I met you,'})(),
        type('Event', (), {'start': 12.20, 'end': 14.01, 'text': 'there was something I\'d been looking for.'})(),
        type('Event', (), {'start': 18.59, 'end': 20.24, 'text': 'This compass...'})(),
    ]
    
    logger.info(f"Chinese events: {len(chinese_events)}")
    logger.info(f"Mock English events: {len(mock_english_events)}")
    
    # Test cross-language matching
    translation_service = get_translation_service()
    if not translation_service:
        logger.error("Translation service not available")
        return False
    
    logger.info("\nTesting cross-language content matching:")
    
    best_matches = []
    
    # Test first 5 Chinese events against first 5 English events
    for i, chinese_event in enumerate(chinese_events[:5]):
        logger.info(f"\nChinese[{i}] ({chinese_event.start:.3f}s): {chinese_event.text}")
        
        try:
            # Translate Chinese to English
            result = translation_service.translate_text(chinese_event.text, target_language='en')
            if not result:
                continue
                
            translated = result.translated_text
            logger.info(f"  Translated: {translated}")
            
            best_match_idx = -1
            best_similarity = 0.0
            
            for j, english_event in enumerate(mock_english_events):
                similarity = calculate_simple_similarity(translated.lower(), english_event.text.lower())
                logger.info(f"    vs English[{j}] ({english_event.start:.3f}s): {english_event.text} -> similarity: {similarity:.3f}")
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = j
            
            if best_match_idx >= 0 and best_similarity >= 0.3:
                offset = mock_english_events[best_match_idx].start - chinese_event.start
                best_matches.append((i, best_match_idx, best_similarity, offset))
                logger.info(f"  ✅ MATCH: Chinese[{i}] -> English[{best_match_idx}] (confidence: {best_similarity:.3f}, offset: {offset:.3f}s)")
            else:
                logger.info(f"  ❌ No good match (best: {best_similarity:.3f})")
                
        except Exception as e:
            logger.error(f"  Translation error: {e}")
    
    # Analyze results
    if best_matches:
        logger.info(f"\n✅ Found {len(best_matches)} potential alignment points:")
        for chinese_idx, english_idx, confidence, offset in best_matches:
            logger.info(f"  Chinese[{chinese_idx}] -> English[{english_idx}]: confidence={confidence:.3f}, offset={offset:.3f}s")
        
        # Calculate average offset
        avg_offset = sum(offset for _, _, _, offset in best_matches) / len(best_matches)
        logger.info(f"\n📊 Average timing offset: {avg_offset:.3f}s")
        logger.info(f"This suggests Chinese track should be shifted by {avg_offset:.3f}s to align with English")
        
        return True
    else:
        logger.warning("❌ No alignment points found")
        return False

def main():
    """Main debug function."""
    logger.info("Subtitle Alignment Debug Analysis")
    logger.info("=" * 50)
    
    # Step 1: Analyze timing offset
    logger.info("Step 1: Analyzing timing offset...")
    analyze_timing_offset()
    
    # Step 2: Test translation alignment
    logger.info("\nStep 2: Testing translation alignment...")
    test_translation_alignment()
    
    # Step 3: Test enhanced alignment algorithm
    logger.info("\nStep 3: Testing enhanced alignment algorithm...")
    success = test_enhanced_alignment_algorithm()
    
    if success:
        logger.info("\n🎉 Debug analysis completed successfully!")
        return 0
    else:
        logger.error("\n💥 Debug analysis failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
