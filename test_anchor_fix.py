#!/usr/bin/env python3
"""Test the improved anchor detection logic."""

import sys
sys.path.append('C:/chsub')

from core.subtitle_formats import SubtitleFormatFactory
from pathlib import Path

def test_position_based_anchor():
    """Test the position-based anchor detection."""
    
    print("=== TESTING POSITION-BASED ANCHOR DETECTION ===")
    
    # Load the files
    chinese_path = Path("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt")
    english_path = Path("direct_embedded_track2.srt")
    
    chinese_file = SubtitleFormatFactory.parse_file(chinese_path)
    english_file = SubtitleFormatFactory.parse_file(english_path)
    
    print(f"Chinese events: {len(chinese_file.events)}")
    print(f"English events: {len(english_file.events)}")
    
    # Test position-based heuristic
    print("\n=== POSITION-BASED HEURISTIC ===")
    
    # Look for first substantial dialogue in each track
    first_dialogue_english = None
    first_dialogue_chinese = None
    
    print("English track - first 10 events:")
    for i, event in enumerate(english_file.events[:10]):
        text_len = len(event.text.strip())
        print(f"  {i}: [{event.start:.3f}s] ({text_len} chars) {event.text}")
        if text_len > 15 and first_dialogue_english is None:
            first_dialogue_english = i
            print(f"    ^^^ FIRST SUBSTANTIAL DIALOGUE (English)")
    
    print("\nChinese track - first 10 events:")
    for i, event in enumerate(chinese_file.events[:10]):
        text_len = len(event.text.strip())
        print(f"  {i}: [{event.start:.3f}s] ({text_len} chars) {event.text}")
        if text_len > 15 and first_dialogue_chinese is None:
            first_dialogue_chinese = i
            print(f"    ^^^ FIRST SUBSTANTIAL DIALOGUE (Chinese)")
    
    if first_dialogue_english is not None and first_dialogue_chinese is not None:
        english_event = english_file.events[first_dialogue_english]
        chinese_event = chinese_file.events[first_dialogue_chinese]
        
        time_offset = english_event.start - chinese_event.start
        
        print(f"\n=== POSITION-BASED ANCHOR RESULT ===")
        print(f"English anchor: [{first_dialogue_english}] at {english_event.start:.3f}s")
        print(f"  Text: {english_event.text}")
        print(f"Chinese anchor: [{first_dialogue_chinese}] at {chinese_event.start:.3f}s")
        print(f"  Text: {chinese_event.text}")
        print(f"Time offset: {time_offset:.3f}s")
        print(f"Confidence: 0.6 (position-based)")
        
        # Compare with the wrong anchor that was being detected
        print(f"\n=== COMPARISON WITH WRONG ANCHOR ===")
        print("Previous wrong detection:")
        print("  English: 'I have no idea' at ~116.818s")
        print("  Chinese: '我不知道' at ~132.985s")
        print("  Offset: ~16.167s")
        print()
        print("New position-based detection:")
        print(f"  English: '{english_event.text}' at {english_event.start:.3f}s")
        print(f"  Chinese: '{chinese_event.text}' at {chinese_event.start:.3f}s")
        print(f"  Offset: {time_offset:.3f}s")
        
        # Check if this makes more sense
        if abs(time_offset) < 20:  # Less than 20 second offset
            print("✅ This anchor makes more sense (smaller offset)")
        else:
            print("❌ This anchor still has large offset")
    else:
        print("❌ Could not find substantial dialogue in both tracks")

if __name__ == "__main__":
    test_position_based_anchor()
