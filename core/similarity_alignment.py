#!/usr/bin/env python3
"""
Automatic subtitle alignment using sentence similarity algorithms.

This module provides functionality to automatically align subtitles by analyzing
text similarity between source and reference subtitle events.
"""

import re
import math
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import Counter
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class AlignmentMatch:
    """Represents a potential alignment match between two subtitle events."""
    source_index: int
    reference_index: int
    confidence: float
    similarity_score: float
    method: str
    source_text: str
    reference_text: str


class SimilarityAligner:
    """Automatic subtitle alignment using text similarity."""
    
    def __init__(self, min_confidence: float = 0.6):
        """
        Initialize the similarity aligner.
        
        Args:
            min_confidence: Minimum confidence threshold for automatic alignment
        """
        self.min_confidence = min_confidence
        self.stop_words = self._get_stop_words()
        
        logger.info(f"Similarity aligner initialized with min_confidence={min_confidence}")
    
    def find_alignments(self, source_texts: List[str], reference_texts: List[str],
                       progress_callback: Optional[callable] = None) -> List[AlignmentMatch]:
        """
        Find the best alignments between source and reference texts.
        
        Args:
            source_texts: List of source subtitle texts
            reference_texts: List of reference subtitle texts
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of AlignmentMatch objects sorted by confidence
        """
        logger.info(f"Finding alignments between {len(source_texts)} source and {len(reference_texts)} reference texts")
        
        matches = []
        total_comparisons = len(source_texts) * len(reference_texts)
        current_comparison = 0
        
        for i, source_text in enumerate(source_texts):
            best_match = None
            best_score = 0.0
            
            for j, reference_text in enumerate(reference_texts):
                if progress_callback:
                    progress_callback(current_comparison, total_comparisons)
                current_comparison += 1
                
                # Calculate multiple similarity scores
                scores = self._calculate_similarity_scores(source_text, reference_text)
                
                # Combine scores with weights
                combined_score = self._combine_scores(scores)
                
                if combined_score > best_score:
                    best_score = combined_score
                    confidence = self._calculate_confidence(scores, i, j, len(source_texts), len(reference_texts))
                    
                    best_match = AlignmentMatch(
                        source_index=i,
                        reference_index=j,
                        confidence=confidence,
                        similarity_score=combined_score,
                        method="similarity_analysis",
                        source_text=source_text,
                        reference_text=reference_text
                    )
            
            if best_match and best_match.confidence >= self.min_confidence:
                matches.append(best_match)
                logger.debug(f"Found alignment: {i} -> {best_match.reference_index} (confidence: {best_match.confidence:.3f})")
        
        if progress_callback:
            progress_callback(total_comparisons, total_comparisons)
        
        # Sort by confidence (highest first)
        matches.sort(key=lambda x: x.confidence, reverse=True)
        
        # Remove conflicts (one-to-one mapping)
        final_matches = self._resolve_conflicts(matches)
        
        logger.info(f"Found {len(final_matches)} high-confidence alignments")
        return final_matches

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate overall similarity between two texts using weighted scoring.

        Args:
            text1: First text to compare
            text2: Second text to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not text1.strip() or not text2.strip():
            return 0.0

        scores = self._calculate_similarity_scores(text1, text2)

        # Use the same scoring approach as _combine_scores
        return self._combine_scores(scores)
    
    def _calculate_similarity_scores(self, text1: str, text2: str) -> Dict[str, float]:
        """Calculate multiple similarity scores between two texts."""
        # Clean and normalize texts
        clean1 = self._clean_text(text1)
        clean2 = self._clean_text(text2)
        
        scores = {}
        
        # 1. Sequence similarity (difflib)
        scores['sequence'] = SequenceMatcher(None, clean1, clean2).ratio()
        
        # 2. Jaccard similarity (word-based)
        scores['jaccard'] = self._jaccard_similarity(clean1, clean2)
        
        # 3. Cosine similarity (TF-IDF-like)
        scores['cosine'] = self._cosine_similarity(clean1, clean2)
        
        # 4. Edit distance similarity
        scores['edit_distance'] = self._edit_distance_similarity(clean1, clean2)
        
        # 5. Length similarity
        scores['length'] = self._length_similarity(clean1, clean2)
        
        # 6. Common words ratio
        scores['common_words'] = self._common_words_ratio(clean1, clean2)
        
        return scores
    
    def _combine_scores(self, scores: Dict[str, float]) -> float:
        """Combine multiple similarity scores with weights."""
        weights = {
            'sequence': 0.25,
            'jaccard': 0.20,
            'cosine': 0.20,
            'edit_distance': 0.15,
            'length': 0.10,
            'common_words': 0.10
        }
        
        combined = sum(scores[method] * weight for method, weight in weights.items())
        return combined
    
    def _calculate_confidence(self, scores: Dict[str, float], source_idx: int, ref_idx: int,
                            source_total: int, ref_total: int) -> float:
        """Calculate confidence score for an alignment match."""
        # Base confidence from similarity scores
        base_confidence = self._combine_scores(scores)
        
        # Position penalty (prefer alignments that maintain relative order)
        position_penalty = self._position_penalty(source_idx, ref_idx, source_total, ref_total)
        
        # Score variance penalty (prefer consistent scores across methods)
        variance_penalty = self._variance_penalty(scores)
        
        # Combine factors
        confidence = base_confidence * (1 - position_penalty) * (1 - variance_penalty)
        
        return max(0.0, min(1.0, confidence))
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for comparison."""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove formatting codes (ASS/SSA)
        text = re.sub(r'\{[^}]+\}', '', text)
        
        # Remove punctuation and special characters
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _cosine_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between two texts."""
        words1 = text1.split()
        words2 = text2.split()
        
        if not words1 or not words2:
            return 0.0
        
        # Create word frequency vectors
        all_words = set(words1 + words2)
        vec1 = [words1.count(word) for word in all_words]
        vec2 = [words2.count(word) for word in all_words]
        
        # Calculate cosine similarity
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def _edit_distance_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity based on edit distance."""
        if not text1 and not text2:
            return 1.0
        
        max_len = max(len(text1), len(text2))
        if max_len == 0:
            return 1.0
        
        # Calculate Levenshtein distance
        distance = self._levenshtein_distance(text1, text2)
        
        # Convert to similarity (0-1 scale)
        similarity = 1.0 - (distance / max_len)
        return max(0.0, similarity)
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _length_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity based on text length."""
        len1, len2 = len(text1), len(text2)
        
        if len1 == 0 and len2 == 0:
            return 1.0
        
        max_len = max(len1, len2)
        min_len = min(len1, len2)
        
        return min_len / max_len if max_len > 0 else 0.0
    
    def _common_words_ratio(self, text1: str, text2: str) -> float:
        """Calculate ratio of common words."""
        words1 = set(word for word in text1.split() if word not in self.stop_words)
        words2 = set(word for word in text2.split() if word not in self.stop_words)
        
        if not words1 and not words2:
            return 1.0
        
        if not words1 or not words2:
            return 0.0
        
        common = words1.intersection(words2)
        total_unique = words1.union(words2)
        
        return len(common) / len(total_unique) if total_unique else 0.0
    
    def _position_penalty(self, source_idx: int, ref_idx: int, 
                         source_total: int, ref_total: int) -> float:
        """Calculate penalty for position mismatch."""
        # Normalize positions to 0-1 range
        source_pos = source_idx / max(1, source_total - 1)
        ref_pos = ref_idx / max(1, ref_total - 1)
        
        # Calculate position difference
        position_diff = abs(source_pos - ref_pos)
        
        # Convert to penalty (0-0.3 range)
        return min(0.3, position_diff * 0.5)
    
    def _variance_penalty(self, scores: Dict[str, float]) -> float:
        """Calculate penalty for high variance in similarity scores."""
        score_values = list(scores.values())
        
        if len(score_values) < 2:
            return 0.0
        
        mean_score = sum(score_values) / len(score_values)
        variance = sum((score - mean_score) ** 2 for score in score_values) / len(score_values)
        
        # Convert variance to penalty (0-0.2 range)
        return min(0.2, variance * 2.0)
    
    def _resolve_conflicts(self, matches: List[AlignmentMatch]) -> List[AlignmentMatch]:
        """Resolve conflicts to ensure one-to-one mapping."""
        used_sources = set()
        used_references = set()
        final_matches = []
        
        for match in matches:
            if (match.source_index not in used_sources and 
                match.reference_index not in used_references):
                final_matches.append(match)
                used_sources.add(match.source_index)
                used_references.add(match.reference_index)
        
        return final_matches
    
    def _get_stop_words(self) -> Set[str]:
        """Get common stop words for filtering."""
        return {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
            'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
            'to', 'was', 'will', 'with', 'i', 'you', 'we', 'they', 'this',
            'but', 'or', 'not', 'have', 'had', 'do', 'does', 'did', 'can',
            'could', 'should', 'would', 'may', 'might', 'must', 'shall'
        }
