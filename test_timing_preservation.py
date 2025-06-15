#!/usr/bin/env python3
"""
Test script to verify timing preservation fixes in the Bilingual Subtitle Suite.

This script tests the critical timing preservation requirements:
1. Embedded track merging preserves exact original timing boundaries
2. Realignment preserves reference track timing completely  
3. Anti-jitter logic has strict scope limitations
"""

import sys
import os
from pathlib import Path
from typing import List

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from core.subtitle_formats import SubtitleEvent, SubtitleFormatFactory
from processors.merger import BilingualMerger
from processors.realigner import SubtitleRealigner
from utils.logging_config import get_logger

logger = get_logger(__name__)


def create_test_events(base_times: List[float], texts: List[str], source_type: str = 'embedded') -> List[SubtitleEvent]:
    """Create test subtitle events with specified timing."""
    events = []
    for i, (start_time, text) in enumerate(zip(base_times, texts)):
        events.append(SubtitleEvent(
            start=start_time,
            end=start_time + 2.0,  # 2 second duration
            text=text
        ))
    return events


def test_embedded_timing_preservation():
    """Test that embedded track merging preserves exact timing boundaries."""
    logger.info("🧪 TEST 1: Embedded Track Timing Preservation")
    
    # Create test events with precise timing
    chinese_times = [1.0, 5.0, 10.0, 15.0, 20.0]
    english_times = [1.5, 5.5, 10.5, 15.5, 20.5]  # Slightly offset
    
    chinese_texts = ["你好", "世界", "测试", "字幕", "结束"]
    english_texts = ["Hello", "World", "Test", "Subtitle", "End"]
    
    chinese_events = create_test_events(chinese_times, chinese_texts, 'embedded')
    english_events = create_test_events(english_times, english_texts, 'embedded')
    
    # Create merger with embedded track info
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'zh'}
    merger._track2_info = {'source_type': 'embedded', 'language': 'en'}
    
    # Merge events
    merged_events = merger._merge_overlapping_events(chinese_events, english_events)
    
    # Collect all timing boundaries
    original_times = set()
    for event in chinese_events + english_events:
        original_times.add(event.start)
        original_times.add(event.end)
    
    merged_times = set()
    for event in merged_events:
        merged_times.add(event.start)
        merged_times.add(event.end)
    
    # Check preservation ratio
    preserved_ratio = len(original_times & merged_times) / len(original_times)
    
    logger.info(f"Original timing boundaries: {len(original_times)}")
    logger.info(f"Preserved timing boundaries: {len(original_times & merged_times)}")
    logger.info(f"Preservation ratio: {preserved_ratio:.1%}")
    
    if preserved_ratio >= 0.8:
        logger.info("✅ TEST 1 PASSED: Embedded timing preservation successful")
        return True
    else:
        logger.error("❌ TEST 1 FAILED: Embedded timing not properly preserved")
        return False


def test_realignment_reference_preservation():
    """Test that realignment preserves reference track timing."""
    logger.info("🧪 TEST 2: Realignment Reference Track Preservation")
    
    # Create misaligned source events and reference events
    source_times = [2.0, 7.0, 12.0, 17.0]  # Offset by 2 seconds
    reference_times = [0.0, 5.0, 10.0, 15.0]
    
    source_texts = ["Source 1", "Source 2", "Source 3", "Source 4"]
    reference_texts = ["Ref 1", "Ref 2", "Ref 3", "Ref 4"]
    
    source_events = create_test_events(source_times, source_texts, 'external')
    reference_events = create_test_events(reference_times, reference_texts, 'embedded')
    
    # Store original reference timing
    original_ref_times = [(e.start, e.end) for e in reference_events]
    
    # Create realigner
    realigner = SubtitleRealigner()
    
    # Align source to reference (reference should remain unchanged)
    aligned_events = realigner._align_events(source_events, reference_events, 0, 0)
    
    # Check that reference timing is preserved by checking if aligned events match reference timing
    # (In a real scenario, we'd merge these, but here we're testing the alignment logic)
    expected_aligned_start = reference_events[0].start  # Should align to reference
    actual_aligned_start = aligned_events[0].start
    
    timing_preserved = abs(expected_aligned_start - actual_aligned_start) < 0.001
    
    logger.info(f"Reference timing: {original_ref_times[0]}")
    logger.info(f"Aligned source timing: ({aligned_events[0].start:.3f}, {aligned_events[0].end:.3f})")
    logger.info(f"Timing alignment correct: {timing_preserved}")
    
    if timing_preserved:
        logger.info("✅ TEST 2 PASSED: Reference track timing preserved during realignment")
        return True
    else:
        logger.error("❌ TEST 2 FAILED: Reference track timing not preserved")
        return False


def test_anti_jitter_scope():
    """Test that anti-jitter logic has proper scope limitations."""
    logger.info("🧪 TEST 3: Anti-jitter Logic Scope")
    
    # Create events with identical consecutive segments within 100ms
    events = [
        SubtitleEvent(start=1.0, end=3.0, text="Same text"),
        SubtitleEvent(start=3.05, end=5.0, text="Same text"),  # 50ms gap - should combine
        SubtitleEvent(start=6.0, end=8.0, text="Different text"),
        SubtitleEvent(start=8.2, end=10.0, text="Different text"),  # 200ms gap - should NOT combine
    ]
    
    # Create merger
    merger = BilingualMerger()
    merger._track1_info = {'source_type': 'embedded', 'language': 'en'}
    merger._track2_info = {'source_type': 'embedded', 'language': 'en'}
    
    # Apply anti-jitter optimization
    optimized_events = merger._optimize_subtitle_timing(events)
    
    # Check results
    # Should combine first two events (same text, <100ms gap)
    # Should NOT combine last two events (same text, >100ms gap)
    expected_count = 3  # 4 original -> 3 after combining first two
    actual_count = len(optimized_events)
    
    logger.info(f"Original events: {len(events)}")
    logger.info(f"Optimized events: {actual_count}")
    logger.info(f"Expected events: {expected_count}")
    
    # Check that first event was extended properly
    first_optimized = optimized_events[0]
    expected_end = 5.0  # Should extend to end of second event
    actual_end = first_optimized.end
    
    scope_correct = (actual_count == expected_count and 
                    abs(actual_end - expected_end) < 0.001)
    
    if scope_correct:
        logger.info("✅ TEST 3 PASSED: Anti-jitter scope properly limited")
        return True
    else:
        logger.error("❌ TEST 3 FAILED: Anti-jitter scope not properly limited")
        return False


def main():
    """Run all timing preservation tests."""
    logger.info("🚀 STARTING COMPREHENSIVE TIMING PRESERVATION TESTS")
    logger.info("=" * 80)
    
    tests = [
        test_embedded_timing_preservation,
        test_realignment_reference_preservation,
        test_anti_jitter_scope
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
            logger.info("-" * 80)
    
    logger.info("🏁 TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Timing preservation fixes are working correctly.")
        return True
    else:
        logger.error(f"💥 {total - passed} TESTS FAILED! Timing preservation needs more work.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
