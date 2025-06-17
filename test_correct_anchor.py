#!/usr/bin/env python3
"""Test the correct anchor detection with proper encoding."""

import sys
sys.path.append('C:/chsub')

from core.subtitle_formats import SubtitleFormatFactory
from pathlib import Path

def test_correct_anchor():
    """Test the correct anchor detection."""
    
    print("=== TESTING CORRECT ANCHOR DETECTION ===")
    
    # Load English file
    english_path = Path("direct_embedded_track2.srt")
    english_file = SubtitleFormatFactory.parse_file(english_path)
    
    print(f"English events: {len(english_file.events)}")
    
    # Manually parse Chinese file to handle BOM correctly
    print("\nManually parsing Chinese file to handle BOM...")
    chinese_events = []
    
    with open("Past.Lives.2023.2160p.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX.zh.srt", 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    # Split into entries
    entries = content.strip().split('\n\n')
    print(f"Found {len(entries)} Chinese entries")
    
    # Parse first few entries manually
    for i, entry in enumerate(entries[:5]):
        lines = entry.strip().split('\n')
        if len(lines) >= 3:
            try:
                # Parse timing
                timing_line = lines[1]
                start_str, end_str = timing_line.split(' --> ')
                
                # Convert to seconds
                def time_to_seconds(time_str):
                    h, m, s = time_str.split(':')
                    s, ms = s.split(',')
                    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
                
                start_time = time_to_seconds(start_str)
                text = '\n'.join(lines[2:])
                
                chinese_events.append({
                    'index': i,
                    'start': start_time,
                    'text': text
                })
                
                print(f"Chinese {i}: [{start_time:.3f}s] {text}")
                
            except Exception as e:
                print(f"Error parsing entry {i}: {e}")
    
    # Now test the anchor detection
    print("\n=== ANCHOR DETECTION TEST ===")
    
    # Find English question
    english_anchor = None
    for i, event in enumerate(english_file.events[:5]):
        text = event.text.strip().lower()
        if 'who' in text and '?' in text and len(text) > 20:
            english_anchor = (i, event.start, event.text)
            print(f"English anchor: [{i}] at {event.start:.3f}s")
            print(f"  Text: {event.text}")
            break
    
    # Find Chinese question
    chinese_anchor = None
    for event in chinese_events:
        text = event['text'].strip()
        if '你觉得' in text and '?' in text:
            chinese_anchor = (event['index'], event['start'], event['text'])
            print(f"Chinese anchor: [{event['index']}] at {event['start']:.3f}s")
            print(f"  Text: {event['text']}")
            break
    
    if english_anchor and chinese_anchor:
        eng_idx, eng_time, eng_text = english_anchor
        chi_idx, chi_time, chi_text = chinese_anchor
        
        time_offset = eng_time - chi_time
        
        print(f"\n=== CORRECT ANCHOR MATCH ===")
        print(f"English: '{eng_text}' at {eng_time:.3f}s")
        print(f"Chinese: '{chi_text}' at {chi_time:.3f}s")
        print(f"Time offset: {time_offset:.3f}s")
        
        # This should be the correct semantic match!
        print("✅ SEMANTIC MATCH: Both are 'who' questions!")
        print("   This is the anchor point that should be detected")
        
        # Compare with wrong detection
        print(f"\n=== COMPARISON ===")
        print("Previous wrong detection:")
        print("  Offset: ~16.167s (later dialogue)")
        print("New correct detection:")
        print(f"  Offset: {time_offset:.3f}s (first dialogue pair)")
        
        if abs(abs(time_offset) - 16.167) < 1:
            print("✅ Offset is very close to previous detection - this confirms the timing relationship")
        
    else:
        print("❌ Could not find both anchor points")

if __name__ == "__main__":
    test_correct_anchor()
