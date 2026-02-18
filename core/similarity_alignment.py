#!/usr/bin/env python3
"""
Automatic subtitle alignment using sentence similarity algorithms.

This module provides functionality to automatically align subtitles by analyzing
text similarity between source and reference subtitle events.
"""

import re
import math
import statistics
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, field
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


class ProperNounExtractor:
    """Extracts translation-invariant tokens (proper nouns, numbers, acronyms) from subtitle text."""

    # Expanded stop words - common words that happen to be capitalized at sentence start
    STOP_WORDS = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'him', 'his', 'her', 'in', 'is', 'it', 'its', 'of',
        'on', 'that', 'the', 'to', 'was', 'will', 'with', 'i', 'you', 'we',
        'they', 'this', 'but', 'or', 'not', 'have', 'had', 'do', 'does',
        'did', 'can', 'could', 'should', 'would', 'may', 'might', 'must',
        'shall', 'if', 'then', 'so', 'no', 'yes', 'ok', 'oh', 'ah', 'um',
        'uh', 'well', 'just', 'like', 'know', 'think', 'want', 'need',
        'come', 'go', 'get', 'got', 'make', 'take', 'see', 'look', 'tell',
        'say', 'said', 'let', 'me', 'my', 'your', 'our', 'their', 'what',
        'who', 'how', 'why', 'when', 'where', 'which', 'there', 'here',
        'all', 'any', 'some', 'every', 'each', 'been', 'being', 'were',
        'about', 'after', 'before', 'between', 'into', 'through', 'during',
        'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under',
        'again', 'then', 'once', 'too', 'very', 'also', 'only', 'own',
        'same', 'than', 'other', 'such', 'more', 'most', 'now', 'way',
        'really', 'right', 'still', 'back', 'even', 'thing', 'things',
        'don', 'didn', 'doesn', 'won', 'wouldn', 'couldn', 'shouldn',
        'isn', 'aren', 'wasn', 'weren', 'hasn', 'haven', 'hadn',
    }

    # Common subtitle artifacts and interjections
    SUBTITLE_NOISE = {
        'hmm', 'huh', 'hey', 'wow', 'whoa', 'ugh', 'ooh', 'aah', 'heh',
        'ha', 'ho', 'shh', 'psst', 'tch', 'tsk', 'grr', 'argh',
    }

    @staticmethod
    def _strip_formatting(text: str) -> str:
        """Remove ASS/SSA and HTML formatting tags from text."""
        # Remove ASS/SSA override tags like {\b1}, {\an8}, {\pos(x,y)}
        text = re.sub(r'\{[^}]*\}', '', text)
        # Remove HTML tags like <b>, <i>, <font color="...">
        text = re.sub(r'<[^>]+>', '', text)
        return text

    def extract_keywords(self, text: str) -> Set[str]:
        """
        Extract translation-invariant keywords from a single subtitle line.

        Extracts:
        - Capitalized words that are NOT sentence-initial (high-confidence proper nouns)
        - ALL-CAPS words of 2+ characters (acronyms like FBI, NASA)
        - Numbers with 2+ digits (years, addresses, quantities)

        Args:
            text: Subtitle text (may contain formatting)

        Returns:
            Set of extracted keyword strings
        """
        text = self._strip_formatting(text)
        keywords = set()

        # Split on common subtitle line breaks
        lines = re.split(r'\\[Nn]|\n', text)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect if line contains CJK characters (Chinese/Japanese/Korean)
            # In CJK text, Latin words are almost always proper nouns
            has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', line))

            # Extract words (sequences of word characters)
            words = re.findall(r"[A-Za-z']+|\d+", line)
            if not words:
                continue

            for idx, word in enumerate(words):
                lower = word.lower()

                # Skip stop words and noise
                if lower in self.STOP_WORDS or lower in self.SUBTITLE_NOISE:
                    continue

                # Numbers with 2+ digits
                if re.match(r'^\d{2,}$', word):
                    keywords.add(word)
                    continue

                # ALL-CAPS words (2+ chars) - acronyms
                if len(word) >= 2 and word.isupper() and word.isalpha():
                    keywords.add(word)
                    continue

                # Capitalized words that are NOT sentence-initial
                if (word[0].isupper() and len(word) >= 2 and not word.isupper()
                        and word.isalpha()):
                    # In CJK text, Latin words are nearly always proper nouns
                    # regardless of position in extracted word list
                    if has_cjk or idx > 0:
                        keywords.add(word)

        return keywords

    def build_keyword_index(self, events) -> Dict[str, List[int]]:
        """
        Build an inverted index mapping keywords to event indices.

        Keywords are case-folded for matching (so "MATSUMURA" and "Matsumura"
        both map to "matsumura"), while extraction still requires capitalization.

        Args:
            events: List of SubtitleEvent objects

        Returns:
            Dict mapping case-folded keyword -> list of event indices containing it
        """
        index: Dict[str, List[int]] = {}
        for i, event in enumerate(events):
            for kw in self.extract_keywords(event.text):
                index.setdefault(kw.lower(), []).append(i)
        return index


@dataclass
class AnchorPair:
    """Represents a matched anchor point between source and reference subtitle tracks."""
    source_index: int
    reference_index: int
    time_offset: float
    confidence: float
    match_method: str
    matched_keywords: List[str] = field(default_factory=list)


class MultiAnchorAligner:
    """
    Find multiple anchor points between two subtitle tracks using
    proper noun matching, same-language similarity, and number matching.
    Computes a robust median offset from all anchors.
    """

    def __init__(self, min_anchors: int = 3):
        """
        Args:
            min_anchors: Desired minimum number of anchors for high confidence.
        """
        self.min_anchors = min_anchors
        self.extractor = ProperNounExtractor()
        self.similarity_aligner = SimilarityAligner(min_confidence=0.6)

    def find_anchors(self, source_events, reference_events,
                     same_language: bool = False) -> List[AnchorPair]:
        """
        Find anchor points between source and reference events.

        Runs three strategies in order:
        1. Keyword anchoring (proper nouns / acronyms)
        2. Number matching (2+ digit numbers)
        3. Same-language similarity sampling (only if same_language=True)

        Args:
            source_events: Source subtitle events
            reference_events: Reference subtitle events
            same_language: Whether both tracks are the same language

        Returns:
            List of AnchorPair objects sorted by source_index
        """
        anchors: List[AnchorPair] = []

        # Strategy 1: Keyword anchoring
        kw_anchors = self._find_keyword_anchors(source_events, reference_events)
        anchors.extend(kw_anchors)
        logger.info(f"Keyword anchoring found {len(kw_anchors)} anchors")

        # Strategy 2: Number matching
        num_anchors = self._find_number_anchors(source_events, reference_events)
        # Deduplicate against existing anchors
        existing_pairs = {(a.source_index, a.reference_index) for a in anchors}
        for a in num_anchors:
            if (a.source_index, a.reference_index) not in existing_pairs:
                anchors.append(a)
        logger.info(f"Number matching found {len(num_anchors)} anchors")

        # Strategy 3: Same-language similarity (if applicable)
        if same_language:
            sim_anchors = self._find_same_language_anchors(
                source_events, reference_events)
            existing_pairs = {(a.source_index, a.reference_index) for a in anchors}
            for a in sim_anchors:
                if (a.source_index, a.reference_index) not in existing_pairs:
                    anchors.append(a)
            logger.info(f"Same-language similarity found {len(sim_anchors)} anchors")

        # Sort by source index for monotonic ordering
        anchors.sort(key=lambda a: a.source_index)

        logger.info(f"Total anchors found: {len(anchors)}")
        return anchors

    def _find_keyword_anchors(self, source_events, reference_events) -> List[AnchorPair]:
        """Find anchors by matching proper nouns and acronyms across tracks."""
        src_index = self.extractor.build_keyword_index(source_events)
        ref_index = self.extractor.build_keyword_index(reference_events)

        # Find keywords present in both tracks
        common_keywords = set(src_index.keys()) & set(ref_index.keys())
        if not common_keywords:
            return []

        logger.debug(f"Common keywords between tracks: {common_keywords}")

        # For each source event, find best matching reference event by shared keywords
        # Group by source event: which keywords does it share with which ref events?
        src_event_matches: Dict[int, Dict[int, List[str]]] = {}
        for kw in common_keywords:
            for si in src_index[kw]:
                for ri in ref_index[kw]:
                    src_event_matches.setdefault(si, {}).setdefault(ri, []).append(kw)

        anchors = []
        used_refs = set()

        # Score each (source, ref) pair by keyword overlap count
        scored_pairs = []
        for si, ref_map in src_event_matches.items():
            for ri, keywords in ref_map.items():
                scored_pairs.append((len(keywords), si, ri, keywords))

        # Sort by keyword count descending (best matches first)
        scored_pairs.sort(key=lambda x: x[0], reverse=True)

        used_sources = set()
        for count, si, ri, keywords in scored_pairs:
            if si in used_sources or ri in used_refs:
                continue

            # Calculate confidence based on keyword count
            confidence = min(1.0, 0.5 + count * 0.2)  # 1 kw=0.7, 2 kw=0.9, 3+=1.0

            time_offset = reference_events[ri].start - source_events[si].start
            anchors.append(AnchorPair(
                source_index=si,
                reference_index=ri,
                time_offset=time_offset,
                confidence=confidence,
                match_method='keyword',
                matched_keywords=keywords,
            ))
            used_sources.add(si)
            used_refs.add(ri)

            logger.debug(f"Keyword anchor: src[{si}] <-> ref[{ri}] "
                        f"keywords={keywords} offset={time_offset:.3f}s")

        return anchors

    def _find_number_anchors(self, source_events, reference_events) -> List[AnchorPair]:
        """Find anchors by matching events containing the same multi-digit numbers."""
        def extract_numbers(text: str) -> Set[str]:
            cleaned = ProperNounExtractor._strip_formatting(text)
            return set(re.findall(r'\d{2,}', cleaned))

        # Build number index for reference
        ref_num_index: Dict[str, List[int]] = {}
        for i, event in enumerate(reference_events):
            for num in extract_numbers(event.text):
                ref_num_index.setdefault(num, []).append(i)

        anchors = []
        used_sources = set()
        used_refs = set()

        for si, event in enumerate(source_events):
            src_nums = extract_numbers(event.text)
            if not src_nums:
                continue

            # Find reference events sharing numbers
            best_ri = None
            best_shared = []
            best_count = 0

            for num in src_nums:
                if num not in ref_num_index:
                    continue
                for ri in ref_num_index[num]:
                    if ri in used_refs:
                        continue
                    ref_nums = extract_numbers(reference_events[ri].text)
                    shared = src_nums & ref_nums
                    if len(shared) > best_count:
                        best_count = len(shared)
                        best_ri = ri
                        best_shared = list(shared)

            if best_ri is not None and si not in used_sources and best_ri not in used_refs:
                time_offset = reference_events[best_ri].start - source_events[si].start
                confidence = min(1.0, 0.4 + best_count * 0.2)
                anchors.append(AnchorPair(
                    source_index=si,
                    reference_index=best_ri,
                    time_offset=time_offset,
                    confidence=confidence,
                    match_method='number',
                    matched_keywords=best_shared,
                ))
                used_sources.add(si)
                used_refs.add(best_ri)

        return anchors

    def _find_same_language_anchors(self, source_events, reference_events) -> List[AnchorPair]:
        """Find anchors by sampling positions and using text similarity (same-language only)."""
        n_src = len(source_events)
        n_ref = len(reference_events)
        if n_src == 0 or n_ref == 0:
            return []

        # Sample ~20 positions spread across the file
        n_samples = min(20, n_src)
        step = max(1, n_src // n_samples)
        sample_indices = list(range(0, n_src, step))[:n_samples]

        anchors = []
        used_refs = set()

        for si in sample_indices:
            src_text = source_events[si].text.strip()
            if len(src_text) < 5:
                continue

            # Proportional search window in reference (assumes monotonic ordering)
            proportion = si / max(1, n_src - 1)
            center_ri = int(proportion * (n_ref - 1))
            window = max(10, n_ref // 10)
            ri_start = max(0, center_ri - window)
            ri_end = min(n_ref, center_ri + window)

            best_score = 0.0
            best_ri = None

            for ri in range(ri_start, ri_end):
                if ri in used_refs:
                    continue
                ref_text = reference_events[ri].text.strip()
                if len(ref_text) < 5:
                    continue

                score = self.similarity_aligner.calculate_similarity(src_text, ref_text)
                if score > best_score:
                    best_score = score
                    best_ri = ri

            if best_ri is not None and best_score >= 0.6:
                time_offset = reference_events[best_ri].start - source_events[si].start
                anchors.append(AnchorPair(
                    source_index=si,
                    reference_index=best_ri,
                    time_offset=time_offset,
                    confidence=best_score,
                    match_method='similarity',
                    matched_keywords=[],
                ))
                used_refs.add(best_ri)

        return anchors

    @staticmethod
    def compute_robust_offset(anchors: List[AnchorPair]) -> Optional[Tuple[float, float]]:
        """
        Compute the median offset and a consistency-based confidence score.

        Uses a two-pass approach: first computes a preliminary median, then
        filters outliers (>5s from median when 3+ anchors exist), and
        recomputes the final median from inliers only.

        Args:
            anchors: List of AnchorPair objects

        Returns:
            Tuple of (median_offset, confidence) or None if no anchors
        """
        if not anchors:
            return None

        offsets = [a.time_offset for a in anchors]

        # Pass 1: preliminary median for outlier detection
        preliminary_median = statistics.median(offsets)

        # Pass 2: filter outliers if we have enough anchors
        if len(offsets) >= 3:
            inlier_offsets = [o for o in offsets if abs(o - preliminary_median) < 5.0]
            outlier_count = len(offsets) - len(inlier_offsets)
            if outlier_count > 0:
                logger.info(f"Filtered {outlier_count} outlier anchor(s) "
                            f"(>5s from preliminary median {preliminary_median:.3f}s)")
            # Fall back to all offsets if filtering removed everything
            if not inlier_offsets:
                inlier_offsets = offsets
        else:
            inlier_offsets = offsets

        median_offset = statistics.median(inlier_offsets)

        # Compute MAD (median absolute deviation) on inliers
        if len(inlier_offsets) >= 2:
            mad = statistics.median([abs(o - median_offset) for o in inlier_offsets])
        else:
            mad = 0.0

        # Consistency-based confidence from MAD
        if mad < 0.1:
            consistency_conf = 1.0
        elif mad < 0.5:
            consistency_conf = 0.9
        elif mad < 1.0:
            consistency_conf = 0.7
        elif mad < 2.0:
            consistency_conf = 0.5
        else:
            consistency_conf = 0.3

        # Anchor count factor (scales up to min_anchors=3 by default)
        count_factor = min(1.0, len(inlier_offsets) / 3.0)

        confidence = consistency_conf * (0.5 + 0.5 * count_factor)

        logger.info(f"Robust offset: median={median_offset:.3f}s, MAD={mad:.3f}s, "
                    f"inliers={len(inlier_offsets)}/{len(offsets)}, confidence={confidence:.3f}")

        return (median_offset, confidence)
