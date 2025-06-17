#!/usr/bin/env python3
"""
Debug script to test semantic anchor detection between Chinese and English subtitles.
"""

import sys
import os
sys.path.append('C:/chsub')

from core.translation_service import GoogleTranslationService
from core.similarity_alignment import SimilarityAligner

def test_anchor_detection():
    """Test the exact anchor detection issue."""
    
    # The exact texts that should match
    chinese_text = "你觉得他们是谁?"
    english_text = "Who do you think they are to each other?"
    
    print("=== SEMANTIC ANCHOR DETECTION DEBUG ===")
    print(f"Chinese: \"{chinese_text}\"")
    print(f"English: \"{english_text}\"")
    print()
    
    # Test translation
    api_key = os.getenv('GOOGLE_CLOUD_API_KEY')
    if not api_key:
        print("❌ No Google Cloud API key found in environment")
        return
    
    try:
        translator = GoogleTranslationService(api_key)
        
        # Translate Chinese to English
        print("🔄 Translating Chinese to English...")
        translated = translator.translate_text(chinese_text, target_language='en')
        print(f"Translation result: \"{translated}\"")
        
        # Test similarity
        print("\n🔍 Testing similarity...")
        aligner = SimilarityAligner()
        similarity = aligner.calculate_similarity(translated, english_text)
        print(f"Raw similarity score: {similarity:.4f}")
        
        # Test with position bonus (first position)
        position_bonus = max(0, 0.1 - (0 + 0) * 0.005)
        adjusted_similarity = similarity + position_bonus
        print(f"Position bonus: {position_bonus:.4f}")
        print(f"Adjusted similarity: {adjusted_similarity:.4f}")
        
        # Test threshold
        threshold = 0.5
        print(f"\nThreshold: {threshold}")
        print(f"Passes threshold: {'✅ YES' if adjusted_similarity >= threshold else '❌ NO'}")
        
        if adjusted_similarity < threshold:
            print(f"\n🔧 ISSUE IDENTIFIED:")
            print(f"   The similarity score {adjusted_similarity:.4f} is below threshold {threshold}")
            print(f"   This is why the anchor point is not being detected!")
            
            # Test with lower threshold
            lower_threshold = 0.3
            print(f"\n🧪 Testing with lower threshold: {lower_threshold}")
            print(f"Would pass: {'✅ YES' if adjusted_similarity >= lower_threshold else '❌ NO'}")
        
    except Exception as e:
        print(f"❌ Translation test failed: {e}")
        import traceback
        traceback.print_exc()

def test_other_pairs():
    """Test other potential anchor pairs."""
    
    pairs = [
        ("嗯……我不知道。", "I don't know."),
        ("是的，这是个难题。", "Yeah, this is a hard one."),
        ("我认为……白人男孩和亚洲女孩是一对，而亚洲男孩…是她的哥哥。", "I think...")
    ]
    
    print("\n=== TESTING OTHER POTENTIAL PAIRS ===")
    
    api_key = os.getenv('GOOGLE_CLOUD_API_KEY')
    if not api_key:
        print("❌ No Google Cloud API key found")
        return
    
    try:
        translator = GoogleTranslationService(api_key)
        aligner = SimilarityAligner()
        
        for i, (chinese, english) in enumerate(pairs):
            print(f"\nPair {i+1}:")
            print(f"Chinese: \"{chinese}\"")
            print(f"English: \"{english}\"")
            
            translated = translator.translate_text(chinese, target_language='en')
            print(f"Translated: \"{translated}\"")
            
            similarity = aligner.calculate_similarity(translated, english)
            position_bonus = max(0, 0.1 - i * 0.005)
            adjusted = similarity + position_bonus
            
            print(f"Similarity: {similarity:.4f} + {position_bonus:.4f} = {adjusted:.4f}")
            print(f"Passes 0.5 threshold: {'✅' if adjusted >= 0.5 else '❌'}")
            
    except Exception as e:
        print(f"❌ Error testing pairs: {e}")

if __name__ == "__main__":
    test_anchor_detection()
    test_other_pairs()
