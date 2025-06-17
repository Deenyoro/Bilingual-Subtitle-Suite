#!/usr/bin/env python3
"""Test the BOM handling fix in the subtitle parser."""

import sys
sys.path.append('C:/chsub')

from core.subtitle_formats import SubtitleFormatFactory
from core.encoding_detection import EncodingDetector
from pathlib import Path

def test_bom_handling():
    """Test the BOM handling fix."""
    
    print("=== TESTING BOM HANDLING FIX ===")
    
    chinese_path = Path("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt")
    
    # Test BOM detection
    has_bom = EncodingDetector.has_bom(chinese_path)
    print(f"File has BOM: {has_bom}")
    
    # Test encoding detection
    encoding = EncodingDetector.detect_encoding(chinese_path)
    print(f"Detected encoding: {encoding}")
    
    # Test file reading with encoding
    try:
        content, used_encoding = EncodingDetector.read_file_with_encoding(chinese_path)
        print(f"Read with encoding: {used_encoding}")
        
        # Check first few characters
        first_line = content.split('\n')[0]
        print(f"First line: {repr(first_line)}")
        
        # Check if BOM character is present
        if '\ufeff' in first_line:
            print("❌ BOM character still present in content!")
        else:
            print("✅ BOM character properly removed from content")
            
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False
    
    # Test subtitle parsing
    print("\n=== TESTING SUBTITLE PARSING ===")
    
    try:
        chinese_file = SubtitleFormatFactory.parse_file(chinese_path)
        print(f"Parsed {len(chinese_file.events)} events")
        
        if chinese_file.events:
            first_event = chinese_file.events[0]
            print(f"First event: [{first_event.start:.3f}s] {first_event.text}")
            
            # Check if this is the expected first event
            if "你觉得他们是谁" in first_event.text:
                print("✅ CORRECT: First event contains expected Chinese text!")
                print(f"   Timing: {first_event.start:.3f}s (expected: ~82.168s)")
                
                if abs(first_event.start - 82.168) < 0.1:
                    print("✅ TIMING CORRECT: First event timing matches expected value")
                    return True
                else:
                    print(f"❌ TIMING WRONG: Expected ~82.168s, got {first_event.start:.3f}s")
            else:
                print(f"❌ WRONG CONTENT: First event should contain '你觉得他们是谁', got: {first_event.text}")
        else:
            print("❌ No events parsed")
            
    except Exception as e:
        print(f"❌ Error parsing subtitle file: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return False

def test_anchor_detection():
    """Test that the anchor detection now works correctly."""
    
    print("\n=== TESTING ANCHOR DETECTION ===")
    
    try:
        # Load both files
        chinese_path = Path("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt")
        english_path = Path("direct_embedded_track2.srt")
        
        chinese_file = SubtitleFormatFactory.parse_file(chinese_path)
        english_file = SubtitleFormatFactory.parse_file(english_path)
        
        print(f"Chinese events: {len(chinese_file.events)}")
        print(f"English events: {len(english_file.events)}")
        
        # Find the expected anchor pair
        chinese_anchor = None
        english_anchor = None
        
        # Look for Chinese question
        for i, event in enumerate(chinese_file.events[:5]):
            if "你觉得他们是谁" in event.text:
                chinese_anchor = (i, event.start, event.text)
                break
        
        # Look for English question
        for i, event in enumerate(english_file.events[:5]):
            if "who do you think" in event.text.lower() and "each other" in event.text.lower():
                english_anchor = (i, event.start, event.text)
                break
        
        if chinese_anchor and english_anchor:
            chi_idx, chi_time, chi_text = chinese_anchor
            eng_idx, eng_time, eng_text = english_anchor
            
            time_offset = eng_time - chi_time
            
            print(f"\n✅ SEMANTIC ANCHOR PAIR FOUND:")
            print(f"Chinese [{chi_idx}]: {chi_text} at {chi_time:.3f}s")
            print(f"English [{eng_idx}]: {eng_text} at {eng_time:.3f}s")
            print(f"Time offset: {time_offset:.3f}s")
            
            # This should be close to -16.665s
            if abs(abs(time_offset) - 16.665) < 1.0:
                print("✅ OFFSET CORRECT: Matches expected semantic anchor timing")
                return True
            else:
                print(f"❌ OFFSET UNEXPECTED: Expected ~±16.665s, got {time_offset:.3f}s")
        else:
            print("❌ Could not find expected anchor pair")
            if not chinese_anchor:
                print("   Missing Chinese anchor: '你觉得他们是谁'")
            if not english_anchor:
                print("   Missing English anchor: 'Who do you think they are to each other'")
                
    except Exception as e:
        print(f"❌ Error in anchor detection test: {e}")
        import traceback
        traceback.print_exc()
        
    return False

if __name__ == "__main__":
    bom_success = test_bom_handling()
    anchor_success = test_anchor_detection()
    
    print(f"\n=== FINAL RESULTS ===")
    print(f"BOM handling fix: {'✅ SUCCESS' if bom_success else '❌ FAILED'}")
    print(f"Anchor detection: {'✅ SUCCESS' if anchor_success else '❌ FAILED'}")
    
    if bom_success and anchor_success:
        print("\n🎉 ALL TESTS PASSED - BOM fix resolves semantic anchor detection!")
    else:
        print("\n❌ Some tests failed - further investigation needed")
