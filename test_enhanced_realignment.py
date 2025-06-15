#!/usr/bin/env python3
"""
Test script for enhanced realignment logic in mixed track scenarios.

This tests the specific scenario where external tracks need timing modifications
while preserving embedded track timing.
"""

import sys
import os
from pathlib import Path
from typing import List

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from core.subtitle_formats import SubtitleEvent
from processors.merger import BilingualMerger
from utils.logging_config import get_logger

logger = get_logger(__name__)


def create_embedded_track() -> List[SubtitleEvent]:
    """Create a properly-timed embedded English track."""
    return [
        SubtitleEvent(start=5.0, end=7.0, text="Welcome to the abyss"),
        SubtitleEvent(start=12.0, end=15.0, text="The curse affects everyone"),
        SubtitleEvent(start=20.0, end=23.0, text="We must go deeper"),
        SubtitleEvent(start=28.0, end=31.0, text="The artifacts are dangerous"),
        SubtitleEvent(start=35.0, end=38.0, text="Stay close to me"),
    ]


def create_misaligned_external_track() -> List[SubtitleEvent]:
    """Create a misaligned external Chinese track (offset by +10 seconds)."""
    return [
        SubtitleEvent(start=0.5, end=2.0, text="前言内容"),  # Pre-anchor content
        SubtitleEvent(start=3.0, end=4.5, text="介绍文字"),  # Pre-anchor content
        SubtitleEvent(start=15.0, end=17.0, text="欢迎来到深渊"),  # Should align with embedded[0]
        SubtitleEvent(start=22.0, end=25.0, text="诅咒影响着每个人"),  # Should align with embedded[1]
        SubtitleEvent(start=30.0, end=33.0, text="我们必须深入"),  # Should align with embedded[2]
        SubtitleEvent(start=38.0, end=41.0, text="神器很危险"),  # Should align with embedded[3]
        SubtitleEvent(start=45.0, end=48.0, text="靠近我"),  # Should align with embedded[4]
    ]


def test_major_misalignment_detection():
    """Test detection of major timing misalignment."""
    logger.info("🧪 TEST 1: Major Timing Misalignment Detection")
    
    embedded_events = create_embedded_track()
    external_events = create_misaligned_external_track()
    
    # Create merger with mixed track info
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Test major misalignment detection
    is_major_misalignment = merger._detect_major_timing_misalignment(embedded_events, external_events)
    
    logger.info(f"Major misalignment detected: {is_major_misalignment}")
    
    if is_major_misalignment:
        logger.info("✅ TEST 1 PASSED: Major misalignment correctly detected")
        return True
    else:
        logger.error("❌ TEST 1 FAILED: Major misalignment not detected")
        return False


def test_semantic_anchor_finding():
    """Test semantic alignment anchor finding."""
    logger.info("🧪 TEST 2: Semantic Anchor Finding")
    
    embedded_events = create_embedded_track()
    external_events = create_misaligned_external_track()
    
    # Create merger
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Initialize similarity aligner (mock for testing)
    class MockSimilarityAligner:
        def _calculate_similarity_scores(self, text1, text2):
            # Simple mock - higher similarity for matching content
            if "abyss" in text1.lower() and "深渊" in text2:
                return {'sequence': 0.8, 'jaccard': 0.7, 'cosine': 0.9, 'edit_distance': 0.6}
            elif "curse" in text1.lower() and "诅咒" in text2:
                return {'sequence': 0.7, 'jaccard': 0.6, 'cosine': 0.8, 'edit_distance': 0.5}
            else:
                return {'sequence': 0.2, 'jaccard': 0.1, 'cosine': 0.3, 'edit_distance': 0.2}
    
    merger.similarity_aligner = MockSimilarityAligner()
    
    # Test semantic anchor finding
    anchor_result = merger._find_semantic_alignment_anchor(embedded_events, external_events)
    
    if anchor_result:
        embedded_idx, external_idx, confidence, time_offset = anchor_result
        logger.info(f"Anchor found: embedded[{embedded_idx}] ↔ external[{external_idx}]")
        logger.info(f"Confidence: {confidence:.3f}, Time offset: {time_offset:.3f}s")
        
        # Expected: embedded[0] should match with external[2] (both about "abyss")
        # Time offset should be approximately 5.0 - 15.0 = -10.0 seconds
        expected_offset = embedded_events[0].start - external_events[2].start  # 5.0 - 15.0 = -10.0
        
        if abs(time_offset - expected_offset) < 1.0:  # Within 1 second tolerance
            logger.info("✅ TEST 2 PASSED: Semantic anchor correctly found")
            return True
        else:
            logger.error(f"❌ TEST 2 FAILED: Incorrect time offset. Expected ~{expected_offset:.1f}s, got {time_offset:.3f}s")
            return False
    else:
        logger.error("❌ TEST 2 FAILED: No semantic anchor found")
        return False


def test_realignment_application():
    """Test application of realignment with pre-anchor deletion."""
    logger.info("🧪 TEST 3: Realignment Application")
    
    external_events = create_misaligned_external_track()
    
    # Create merger
    merger = BilingualMerger()
    
    # Test realignment application
    # Simulate anchor at index 2 (third event) with -10 second offset
    anchor_idx = 2
    time_offset = -10.0
    
    realigned_events = merger._apply_mixed_track_realignment(external_events, anchor_idx, time_offset)
    
    # Verify results
    expected_count = len(external_events) - anchor_idx  # Should remove pre-anchor events
    actual_count = len(realigned_events)
    
    logger.info(f"Original events: {len(external_events)}")
    logger.info(f"Expected realigned events: {expected_count}")
    logger.info(f"Actual realigned events: {actual_count}")
    
    if actual_count == expected_count:
        # Check timing of first realigned event
        first_realigned = realigned_events[0]
        original_first_kept = external_events[anchor_idx]
        expected_start = original_first_kept.start + time_offset  # 15.0 + (-10.0) = 5.0
        
        logger.info(f"First realigned event timing: {first_realigned.start:.3f}s")
        logger.info(f"Expected timing: {expected_start:.3f}s")
        
        if abs(first_realigned.start - expected_start) < 0.1:
            logger.info("✅ TEST 3 PASSED: Realignment correctly applied")
            return True
        else:
            logger.error("❌ TEST 3 FAILED: Incorrect timing after realignment")
            return False
    else:
        logger.error("❌ TEST 3 FAILED: Incorrect number of events after realignment")
        return False


def test_mixed_track_workflow():
    """Test the complete mixed track realignment workflow."""
    logger.info("🧪 TEST 4: Complete Mixed Track Workflow")
    
    embedded_events = create_embedded_track()
    external_events = create_misaligned_external_track()
    
    # Create merger with mixed track info
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Mock the similarity aligner
    class MockSimilarityAligner:
        def _calculate_similarity_scores(self, text1, text2):
            if "abyss" in text1.lower() and "深渊" in text2:
                return {'sequence': 0.8, 'jaccard': 0.7, 'cosine': 0.9, 'edit_distance': 0.6}
            else:
                return {'sequence': 0.2, 'jaccard': 0.1, 'cosine': 0.3, 'edit_distance': 0.2}
    
    merger.similarity_aligner = MockSimilarityAligner()
    
    # Mock user confirmation to always return True for testing
    original_confirm = merger._confirm_major_timing_shift
    merger._confirm_major_timing_shift = lambda *args: True
    
    try:
        # Test the complete workflow
        merged_events = merger._merge_overlapping_events(embedded_events, external_events)
        
        logger.info(f"Merged events created: {len(merged_events)}")
        
        # Verify that we got some merged events
        if len(merged_events) > 0:
            # Check that embedded timing is preserved in merged events
            embedded_times = {(e.start, e.end) for e in embedded_events}
            merged_times = {(e.start, e.end) for e in merged_events}
            
            # Some embedded timing should be preserved
            preserved_count = len(embedded_times & merged_times)
            preservation_ratio = preserved_count / len(embedded_times)
            
            logger.info(f"Embedded timing preservation: {preservation_ratio:.1%}")
            
            if preservation_ratio >= 0.6:  # At least 60% preserved
                logger.info("✅ TEST 4 PASSED: Mixed track workflow completed successfully")
                return True
            else:
                logger.error("❌ TEST 4 FAILED: Insufficient embedded timing preservation")
                return False
        else:
            logger.error("❌ TEST 4 FAILED: No merged events created")
            return False
            
    finally:
        # Restore original method
        merger._confirm_major_timing_shift = original_confirm


def main():
    """Run all enhanced realignment tests."""
    logger.info("🚀 STARTING ENHANCED REALIGNMENT TESTS")
    logger.info("=" * 80)
    
    tests = [
        test_major_misalignment_detection,
        test_semantic_anchor_finding,
        test_realignment_application,
        test_mixed_track_workflow
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            logger.info("-" * 80)
        except Exception as e:
            logger.error(f"❌ TEST FAILED WITH EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            logger.info("-" * 80)
    
    logger.info("🏁 TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Enhanced realignment logic is working correctly.")
        return True
    else:
        logger.error(f"💥 {total - passed} TESTS FAILED! Enhanced realignment needs more work.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
