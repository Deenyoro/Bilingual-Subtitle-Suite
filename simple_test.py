#!/usr/bin/env python3
"""Simple test of similarity scoring."""

import sys
import re
import math
from difflib import SequenceMatcher

def clean_text(text):
    """Clean and normalize text for comparison."""
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove punctuation and special characters
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def calculate_similarity(text1, text2):
    """Calculate similarity between two texts."""
    clean1 = clean_text(text1)
    clean2 = clean_text(text2)
    
    if not clean1 or not clean2:
        return 0.0
    
    # Use sequence matcher
    return SequenceMatcher(None, clean1, clean2).ratio()

def test_pairs():
    """Test the specific pairs."""
    
    # Test the expected match
    chinese_manual = "Who do you think they are?"  # Manual translation
    english = "Who do you think they are to each other?"
    
    print("=== MANUAL TRANSLATION TEST ===")
    print(f"Chinese (translated): '{chinese_manual}'")
    print(f"English: '{english}'")
    
    similarity = calculate_similarity(chinese_manual, english)
    print(f"Similarity: {similarity:.4f}")
    
    # Add position bonus
    position_bonus = 0.1  # First position gets full bonus
    adjusted = similarity + position_bonus
    print(f"With position bonus: {adjusted:.4f}")
    print(f"Passes 0.5 threshold: {adjusted >= 0.5}")
    
    print("\n=== OTHER PAIRS ===")
    
    pairs = [
        ("I don't know", "I don't know."),
        ("I don't know", "I have no idea"),
        ("Yeah this is a hard one", "Yeah, this is a hard one."),
    ]
    
    for i, (text1, text2) in enumerate(pairs):
        print(f"\nPair {i+1}: '{text1}' vs '{text2}'")
        sim = calculate_similarity(text1, text2)
        bonus = max(0, 0.1 - i * 0.005)
        adj = sim + bonus
        print(f"Similarity: {sim:.4f} + {bonus:.4f} = {adj:.4f}")

if __name__ == "__main__":
    test_pairs()
