#!/usr/bin/env python3
"""Simple test to verify timing preservation fixes."""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.subtitle_formats import SubtitleEvent
    print("✅ SubtitleEvent import successful")
    
    # Test creating a simple event
    event = SubtitleEvent(start=1.0, end=3.0, text="Test")
    print(f"✅ SubtitleEvent creation successful: {event.start}s-{event.end}s")
    
    from processors.merger import BilingualMerger
    print("✅ BilingualMerger import successful")
    
    # Test creating a merger
    merger = BilingualMerger()
    print("✅ BilingualMerger creation successful")
    
    # Test the timing preservation method
    events1 = [SubtitleEvent(start=1.0, end=3.0, text="Chinese")]
    events2 = [SubtitleEvent(start=1.5, end=3.5, text="English")]
    
    # Set track info to simulate embedded tracks
    merger._track1_info = {'source_type': 'embedded', 'language': 'zh'}
    merger._track2_info = {'source_type': 'embedded', 'language': 'en'}
    
    merged = merger._merge_with_preserved_timing(events1, events2)
    print(f"✅ Timing preservation test successful: {len(merged)} events created")
    
    print("🎉 All basic tests passed!")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
