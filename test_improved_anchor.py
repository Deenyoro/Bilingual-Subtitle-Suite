#!/usr/bin/env python3
"""Test the improved first dialogue pair anchor detection."""

import sys
sys.path.append('C:/chsub')

from core.subtitle_formats import SubtitleFormatFactory
from pathlib import Path

def test_first_dialogue_anchor():
    """Test the first dialogue pair anchor detection."""
    
    print("=== TESTING FIRST DIALOGUE PAIR ANCHOR DETECTION ===")
    
    # Load the files
    chinese_path = Path("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt")
    english_path = Path("direct_embedded_track2.srt")
    
    chinese_file = SubtitleFormatFactory.parse_file(chinese_path)
    english_file = SubtitleFormatFactory.parse_file(english_path)
    
    print(f"Chinese events: {len(chinese_file.events)}")
    print(f"English events: {len(english_file.events)}")
    
    # Test first dialogue pair detection
    print("\n=== FIRST DIALOGUE PAIR DETECTION ===")
    
    # Find first substantial dialogue in embedded track (English)
    first_dialogue_embedded = None
    print("English track - first 5 events:")
    for i, event in enumerate(english_file.events[:5]):
        text = event.text.strip().lower()
        has_question = ('who' in text or 'what' in text or 'how' in text or 'why' in text or '?' in text)
        is_substantial = len(text) > 20
        
        print(f"  {i}: [{event.start:.3f}s] {event.text}")
        print(f"      Length: {len(text)}, Has question: {has_question}, Substantial: {is_substantial}")
        
        if is_substantial and has_question and first_dialogue_embedded is None:
            first_dialogue_embedded = i
            print(f"      ^^^ FIRST DIALOGUE (English)")
    
    # Find first substantial dialogue in external track (Chinese)
    first_dialogue_external = None
    print("\nChinese track - first 5 events:")
    for j, event in enumerate(chinese_file.events[:5]):
        text = event.text.strip()
        has_question = ('你' in text or '什么' in text or '怎么' in text or '为什么' in text or '?' in text or '？' in text)
        is_substantial = len(text) > 5
        
        print(f"  {j}: [{event.start:.3f}s] {event.text}")
        print(f"      Length: {len(text)}, Has question: {has_question}, Substantial: {is_substantial}")
        
        if is_substantial and has_question and first_dialogue_external is None:
            first_dialogue_external = j
            print(f"      ^^^ FIRST DIALOGUE (Chinese)")
    
    if first_dialogue_embedded is not None and first_dialogue_external is not None:
        english_event = english_file.events[first_dialogue_embedded]
        chinese_event = chinese_file.events[first_dialogue_external]
        
        time_offset = english_event.start - chinese_event.start
        
        print(f"\n=== FIRST DIALOGUE PAIR ANCHOR RESULT ===")
        print(f"English anchor: [{first_dialogue_embedded}] at {english_event.start:.3f}s")
        print(f"  Text: {english_event.text}")
        print(f"Chinese anchor: [{first_dialogue_external}] at {chinese_event.start:.3f}s")
        print(f"  Text: {chinese_event.text}")
        print(f"Time offset: {time_offset:.3f}s")
        print(f"Confidence: 0.8 (first dialogue pair)")
        
        # Check if this is the correct match
        if 'who' in english_event.text.lower() and '你' in chinese_event.text:
            print("✅ CORRECT MATCH: Both are 'who' questions!")
            print("   This should be the semantic anchor point")
        else:
            print("❌ Not the expected match")
            
        # Compare timing
        print(f"\n=== TIMING ANALYSIS ===")
        print(f"English timing: {english_event.start:.3f}s")
        print(f"Chinese timing: {chinese_event.start:.3f}s")
        print(f"Offset: {time_offset:.3f}s")
        
        if abs(time_offset) < 20:
            print("✅ Reasonable offset for subtitle alignment")
        else:
            print("❌ Large offset - may indicate timing issues")
            
    else:
        print("❌ Could not find first dialogue pair in both tracks")
        print(f"English first dialogue: {first_dialogue_embedded}")
        print(f"Chinese first dialogue: {first_dialogue_external}")

if __name__ == "__main__":
    test_first_dialogue_anchor()
