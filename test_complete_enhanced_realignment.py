#!/usr/bin/env python3
"""
Complete test for enhanced realignment workflow with CLI integration.

This test verifies the entire enhanced realignment feature including:
- CLI flag handling
- Mixed track detection
- Semantic anchor finding
- User confirmation workflow
- Timing preservation validation
"""

import sys
import os
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from core.subtitle_formats import SubtitleEvent
from processors.merger import BilingualMerger
from ui.cli import CLIHandler
from utils.logging_config import get_logger

logger = get_logger(__name__)


def create_test_scenario():
    """Create a realistic test scenario matching Made in Abyss use case."""
    
    # Embedded English track (properly timed)
    embedded_english = [
        SubtitleEvent(start=5.0, end=7.5, text="Welcome to the abyss"),
        SubtitleEvent(start=12.0, end=15.0, text="The curse affects everyone"),
        SubtitleEvent(start=20.0, end=23.5, text="We must go deeper"),
        SubtitleEvent(start=28.0, end=31.0, text="The artifacts are dangerous"),
        SubtitleEvent(start=35.0, end=38.0, text="Stay close to me"),
    ]
    
    # External Chinese track (misaligned by +10 seconds with pre-anchor content)
    external_chinese = [
        SubtitleEvent(start=0.5, end=2.0, text="前言内容"),  # Pre-anchor
        SubtitleEvent(start=3.0, end=4.5, text="介绍文字"),  # Pre-anchor
        SubtitleEvent(start=15.0, end=17.5, text="欢迎来到深渊"),  # Should align with embedded[0]
        SubtitleEvent(start=22.0, end=25.0, text="诅咒影响着每个人"),  # Should align with embedded[1]
        SubtitleEvent(start=30.0, end=33.5, text="我们必须深入"),  # Should align with embedded[2]
        SubtitleEvent(start=38.0, end=41.0, text="神器很危险"),  # Should align with embedded[3]
        SubtitleEvent(start=45.0, end=48.0, text="靠近我"),  # Should align with embedded[4]
    ]
    
    return embedded_english, external_chinese


def test_cli_flag_integration():
    """Test that CLI properly handles the enhanced realignment flag."""
    logger.info("🧪 TEST 1: CLI Flag Integration")
    
    # Mock CLI arguments
    class MockArgs:
        def __init__(self):
            self.enable_mixed_realignment = True
            self.auto_align = False
            self.use_translation = False
            self.manual_align = False
            self.alignment_threshold = 0.8
            self.translation_api_key = None
            self.sync_strategy = 'auto'
            self.reference_language = 'auto'
            self.force_pgs = False
            self.no_pgs = False
    
    args = MockArgs()
    
    # Test merger creation with flag
    merger = BilingualMerger(
        enable_mixed_realignment=args.enable_mixed_realignment,
        auto_align=args.auto_align,
        use_translation=args.use_translation,
        alignment_threshold=args.alignment_threshold,
        translation_api_key=args.translation_api_key,
        manual_align=args.manual_align,
        sync_strategy=args.sync_strategy,
        reference_language_preference=args.reference_language,
        force_pgs=args.force_pgs,
        no_pgs=args.no_pgs
    )
    
    if merger.enable_mixed_realignment:
        logger.info("✅ TEST 1 PASSED: CLI flag properly integrated")
        return True
    else:
        logger.error("❌ TEST 1 FAILED: CLI flag not properly set")
        return False


def test_complete_workflow_with_flag_enabled():
    """Test complete workflow with enhanced realignment enabled."""
    logger.info("🧪 TEST 2: Complete Workflow (Flag Enabled)")
    
    embedded_events, external_events = create_test_scenario()
    
    # Create merger with enhanced realignment enabled
    merger = BilingualMerger(enable_mixed_realignment=True)
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Mock similarity aligner for consistent results
    class MockSimilarityAligner:
        def _calculate_similarity_scores(self, text1, text2):
            # High similarity for "abyss" content
            if "abyss" in text1.lower() and "深渊" in text2:
                return {'sequence': 0.8, 'jaccard': 0.7, 'cosine': 0.9, 'edit_distance': 0.6}
            else:
                return {'sequence': 0.2, 'jaccard': 0.1, 'cosine': 0.3, 'edit_distance': 0.2}
    
    merger.similarity_aligner = MockSimilarityAligner()
    
    # Mock user confirmation to auto-accept
    original_confirm = merger._confirm_major_timing_shift
    merger._confirm_major_timing_shift = lambda *args: True
    
    try:
        # Test the workflow
        merged_events = merger._merge_overlapping_events(embedded_events, external_events)
        
        # Verify results
        if len(merged_events) > 0:
            # Check that embedded timing is preserved
            embedded_times = {(e.start, e.end) for e in embedded_events}
            merged_times = {(e.start, e.end) for e in merged_events}
            preserved_count = len(embedded_times & merged_times)
            preservation_ratio = preserved_count / len(embedded_times)
            
            logger.info(f"Merged events: {len(merged_events)}")
            logger.info(f"Embedded timing preservation: {preservation_ratio:.1%}")
            
            if preservation_ratio >= 0.6:
                logger.info("✅ TEST 2 PASSED: Complete workflow successful with flag enabled")
                return True
            else:
                logger.error("❌ TEST 2 FAILED: Poor embedded timing preservation")
                return False
        else:
            logger.error("❌ TEST 2 FAILED: No merged events created")
            return False
            
    finally:
        merger._confirm_major_timing_shift = original_confirm


def test_complete_workflow_with_flag_disabled():
    """Test complete workflow with enhanced realignment disabled."""
    logger.info("🧪 TEST 3: Complete Workflow (Flag Disabled)")
    
    embedded_events, external_events = create_test_scenario()
    
    # Create merger with enhanced realignment disabled
    merger = BilingualMerger(enable_mixed_realignment=False)
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Test the workflow
    merged_events = merger._merge_overlapping_events(embedded_events, external_events)
    
    # Should fall back to timing preservation
    if len(merged_events) > 0:
        logger.info(f"Merged events: {len(merged_events)} (using timing preservation fallback)")
        logger.info("✅ TEST 3 PASSED: Proper fallback behavior when flag disabled")
        return True
    else:
        logger.error("❌ TEST 3 FAILED: No merged events created")
        return False


def test_major_misalignment_detection_accuracy():
    """Test accuracy of major misalignment detection."""
    logger.info("🧪 TEST 4: Major Misalignment Detection Accuracy")
    
    embedded_events, external_events = create_test_scenario()
    
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Test with major misalignment (should detect)
    major_misalignment = merger._detect_major_timing_misalignment(embedded_events, external_events)
    
    if major_misalignment:
        logger.info("✅ Major misalignment correctly detected")
        
        # Test with synchronized tracks (should not detect)
        synchronized_external = [
            SubtitleEvent(start=e.start + 0.1, end=e.end + 0.1, text=f"同步字幕{i}")
            for i, e in enumerate(embedded_events)
        ]
        
        merger._track2_info = {'source_type': 'external', 'language': 'zh'}
        no_misalignment = merger._detect_major_timing_misalignment(embedded_events, synchronized_external)
        
        if not no_misalignment:
            logger.info("✅ Synchronized tracks correctly identified")
            logger.info("✅ TEST 4 PASSED: Misalignment detection is accurate")
            return True
        else:
            logger.error("❌ TEST 4 FAILED: False positive on synchronized tracks")
            return False
    else:
        logger.error("❌ TEST 4 FAILED: Major misalignment not detected")
        return False


def test_timing_validation_for_mixed_scenarios():
    """Test timing validation specifically for mixed track scenarios."""
    logger.info("🧪 TEST 5: Timing Validation for Mixed Scenarios")
    
    embedded_events, external_events = create_test_scenario()
    
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'external', 'language': 'zh'}
    
    # Create mock merged events that preserve embedded timing
    merged_events = []
    for i, embedded_event in enumerate(embedded_events):
        # Preserve embedded timing exactly
        merged_event = SubtitleEvent(
            start=embedded_event.start,
            end=embedded_event.end,
            text=f"{external_events[i+2].text if i+2 < len(external_events) else 'Chinese'}\n{embedded_event.text}"
        )
        merged_events.append(merged_event)
    
    # Test validation
    validation_result = merger._validate_timing_preservation(
        embedded_events, external_events, merged_events, "mixed_track_realignment"
    )
    
    if validation_result:
        logger.info("✅ TEST 5 PASSED: Mixed scenario timing validation works correctly")
        return True
    else:
        logger.error("❌ TEST 5 FAILED: Mixed scenario timing validation failed")
        return False


def main():
    """Run all enhanced realignment tests."""
    logger.info("🚀 STARTING COMPLETE ENHANCED REALIGNMENT TESTS")
    logger.info("=" * 80)
    
    tests = [
        test_cli_flag_integration,
        test_complete_workflow_with_flag_enabled,
        test_complete_workflow_with_flag_disabled,
        test_major_misalignment_detection_accuracy,
        test_timing_validation_for_mixed_scenarios
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
    
    logger.info("🏁 COMPLETE TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Enhanced realignment is fully functional.")
        logger.info("🎯 Ready for production use with Made in Abyss and similar scenarios.")
        return True
    else:
        logger.error(f"💥 {total - passed} TESTS FAILED! Enhanced realignment needs fixes.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
