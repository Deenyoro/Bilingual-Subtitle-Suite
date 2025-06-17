#!/usr/bin/env python3
"""Debug the anchor detection process."""

import sys
sys.path.append('C:/chsub')

from core.subtitle_formats import SubtitleFormatFactory
from pathlib import Path

def debug_anchor_detection():
    """Debug what's happening in anchor detection."""
    
    print("=== DEBUGGING ANCHOR DETECTION ===")
    
    # Load both files
    chinese_path = Path("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt")
    english_path = Path("direct_embedded_track2.srt")
    
    chinese_file = SubtitleFormatFactory.parse_file(chinese_path)
    english_file = SubtitleFormatFactory.parse_file(english_path)
    
    print(f"Chinese events: {len(chinese_file.events)}")
    print(f"English events: {len(english_file.events)}")
    
    # Check what the position-based heuristic should find
    print("\n=== POSITION-BASED HEURISTIC TEST ===")
    
    # Find first substantial dialogue in embedded track (English)
    first_dialogue_embedded = None
    print("English track - first 3 events:")
    for i, event in enumerate(english_file.events[:3]):
        text = event.text.strip().lower()
        has_who_what = ('who' in text or 'what' in text)
        has_question = ('?' in text)
        is_substantial = len(text) > 20
        
        print(f"  {i}: [{event.start:.3f}s] {event.text}")
        print(f"      Length: {len(text)}, Has who/what: {has_who_what}, Has ?: {has_question}, Substantial: {is_substantial}")
        
        if is_substantial and has_who_what and has_question and first_dialogue_embedded is None:
            first_dialogue_embedded = i
            print(f"      ^^^ ENGLISH DIALOGUE ANCHOR")
    
    # Find first substantial dialogue in external track (Chinese)
    first_dialogue_external = None
    print("\nChinese track - first 3 events:")
    for j, event in enumerate(chinese_file.events[:3]):
        text = event.text.strip()
        has_chinese_question = ('你' in text or '什么' in text)
        has_question_mark = ('?' in text or '？' in text)
        is_substantial = len(text) > 5
        
        print(f"  {j}: [{event.start:.3f}s] {event.text}")
        print(f"      Length: {len(text)}, Has 你/什么: {has_chinese_question}, Has ?/？: {has_question_mark}, Substantial: {is_substantial}")
        
        if is_substantial and has_chinese_question and has_question_mark and first_dialogue_external is None:
            first_dialogue_external = j
            print(f"      ^^^ CHINESE DIALOGUE ANCHOR")
    
    if first_dialogue_embedded is not None and first_dialogue_external is not None:
        english_event = english_file.events[first_dialogue_embedded]
        chinese_event = chinese_file.events[first_dialogue_external]
        
        time_offset = english_event.start - chinese_event.start
        
        print(f"\n=== POSITION-BASED ANCHOR RESULT ===")
        print(f"English anchor: [{first_dialogue_embedded}] at {english_event.start:.3f}s")
        print(f"  Text: {english_event.text}")
        print(f"Chinese anchor: [{first_dialogue_external}] at {chinese_event.start:.3f}s")
        print(f"  Text: {chinese_event.text}")
        print(f"Time offset: {time_offset:.3f}s")
        print(f"Confidence: 0.95 (position-based)")
        
        # Compare with current wrong detection
        print(f"\n=== COMPARISON WITH CURRENT DETECTION ===")
        print("Current wrong detection:")
        print("  English: 'I have no idea' at ~116.818s")
        print("  Chinese: '我不知道' at ~132.985s")
        print("  Offset: ~16.167s")
        print()
        print("Position-based detection should find:")
        print(f"  English: '{english_event.text}' at {english_event.start:.3f}s")
        print(f"  Chinese: '{chinese_event.text}' at {chinese_event.start:.3f}s")
        print(f"  Offset: {time_offset:.3f}s")
        
        # This should be the correct semantic match
        if abs(abs(time_offset) - 16.665) < 1:
            print("✅ This matches the expected semantic anchor timing!")
        else:
            print("❌ This doesn't match expected timing")
            
    else:
        print("❌ Position-based heuristic failed to find dialogue pair")
        print(f"English dialogue found: {first_dialogue_embedded}")
        print(f"Chinese dialogue found: {first_dialogue_external}")

if __name__ == "__main__":
    debug_anchor_detection()
