#!/usr/bin/env python3
"""
Subtitle Track Analyzer

This module provides intelligent analysis of subtitle tracks to identify the main dialogue track
while avoiding forced, signs, and songs tracks.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from utils.logging_config import get_logger
from core.subtitle_formats import SubtitleFormatFactory

logger = get_logger(__name__)


@dataclass
class TrackScore:
    """Represents the analysis score for a subtitle track."""
    track_id: str
    title: str
    language: str
    event_count: int
    event_count_score: float
    title_score: float
    content_score: float
    total_score: float
    is_dialogue_candidate: bool
    reasoning: List[str]


class SubtitleTrackAnalyzer:
    """Analyzes subtitle tracks to identify the main dialogue track."""
    
    # Keywords that indicate non-dialogue tracks
    NEGATIVE_KEYWORDS = {
        'signs', 'songs', 'commentary', 'sdh', 'cc', 'closed caption',
        'hearing impaired', 'full', 'complete', 'director', 'cast', 'crew',
        'karaoke', 'lyrics', 'opening', 'ending', 'op', 'ed', 'insert',
        'background', 'bgm', 'sfx', 'sound effects', 'narrator'
    }

    # Keywords that specifically indicate forced English subtitles (foreign dialogue only)
    FORCED_ENGLISH_KEYWORDS = {
        'forced', 'forced english', 'forced eng', 'foreign', 'foreign only',
        'foreign dialogue', 'foreign parts', 'non-english', 'alien language',
        'foreign language', 'parts only', 'foreign parts only'
    }

    # Keywords that indicate dialogue tracks
    POSITIVE_KEYWORDS = {
        'dialogue', 'dialog', 'main', 'primary', 'default', 'regular',
        'standard', 'normal', 'full dialogue', 'conversation', 'english dialogue',
        'eng dialogue', 'full english', 'complete english'
    }
    
    # Event count thresholds for dialogue classification
    MIN_DIALOGUE_EVENTS = 100
    TYPICAL_DIALOGUE_EVENTS = 300
    SIGNS_SONGS_MAX_EVENTS = 80
    
    def __init__(self):
        """Initialize the track analyzer."""
        pass
    
    def analyze_tracks(self, tracks: List[Dict], video_path: Optional[Path] = None) -> List[TrackScore]:
        """
        Analyze subtitle tracks and score them for dialogue likelihood.
        
        Args:
            tracks: List of subtitle track information
            video_path: Optional path to video file for content analysis
            
        Returns:
            List of TrackScore objects sorted by dialogue likelihood (highest first)
        """
        scores = []
        
        for track in tracks:
            score = self._analyze_single_track(track, video_path)
            scores.append(score)
        
        # Sort by total score (highest first)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Log analysis results
        self._log_analysis_results(scores)
        
        return scores
    
    def _analyze_single_track(self, track: Dict, video_path: Optional[Path] = None) -> TrackScore:
        """Analyze a single subtitle track."""
        track_id = track.get('track_id', track.get('index', 'unknown'))
        title = track.get('title', '').lower()
        language = track.get('language', '').lower()
        
        reasoning = []
        
        # Initialize scores
        event_count_score = 0.0
        title_score = 0.0
        content_score = 0.0
        
        # Get event count (try to extract if possible)
        event_count = self._get_event_count(track, video_path)
        
        # 1. Event Count Analysis (40% weight)
        event_count_score = self._score_event_count(event_count, reasoning)
        
        # 2. Title Pattern Matching (35% weight)
        title_score = self._score_title(title, reasoning)
        
        # 3. Content Analysis (25% weight)
        content_score = self._score_content(track, video_path, reasoning)
        
        # Calculate weighted total score
        total_score = (
            event_count_score * 0.40 +
            title_score * 0.35 +
            content_score * 0.25
        )
        
        # Determine if this is a dialogue candidate
        is_dialogue_candidate = (
            total_score > 0.5 and
            event_count >= self.MIN_DIALOGUE_EVENTS and
            title_score >= -0.5  # Not heavily penalized by title
        )
        
        return TrackScore(
            track_id=str(track_id),
            title=track.get('title', ''),
            language=language,
            event_count=event_count,
            event_count_score=event_count_score,
            title_score=title_score,
            content_score=content_score,
            total_score=total_score,
            is_dialogue_candidate=is_dialogue_candidate,
            reasoning=reasoning
        )
    
    def _get_event_count(self, track: Dict, video_path: Optional[Path] = None) -> int:
        """Get the number of subtitle events in a track."""
        # If event count is already provided
        if 'event_count' in track:
            return track['event_count']

        # Try to estimate from track metadata
        if 'duration' in track and 'avg_duration_per_event' in track:
            estimated_count = int(track['duration'] / track['avg_duration_per_event'])
            return estimated_count

        # Try to extract and count events from the actual track
        if video_path and video_path.exists():
            try:
                count = self._extract_and_count_events(track, video_path)
                if count > 0:
                    return count
            except Exception as e:
                logger.debug(f"Could not extract track for counting: {e}")

        # Intelligent estimation based on track characteristics
        return self._estimate_event_count(track)

    def _extract_and_count_events(self, track: Dict, video_path: Path) -> int:
        """Extract a sample of the track and count events."""
        import tempfile
        import subprocess
        from core.subtitle_formats import SubtitleFormatFactory

        track_id = track.get('track_id', track.get('index'))
        if not track_id:
            return 0

        try:
            with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as tmp_file:
                # Extract first 10 minutes of the track for sampling
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
                    "-map", f"0:{track_id}",
                    "-t", "600",  # First 10 minutes
                    "-c:s", "srt",
                    tmp_file.name
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=60)

                if result.returncode == 0:
                    # Parse the sample and count events
                    sample_sub = SubtitleFormatFactory.parse_file(Path(tmp_file.name))
                    if sample_sub and sample_sub.events:
                        sample_count = len(sample_sub.events)
                        # Estimate total based on 10-minute sample
                        # Assume typical movie is 90-120 minutes
                        estimated_total = int(sample_count * 9)  # 90 minutes / 10 minutes
                        logger.debug(f"Extracted {sample_count} events from 10-minute sample, "
                                   f"estimated total: {estimated_total}")
                        return estimated_total

        except Exception as e:
            logger.debug(f"Failed to extract sample for counting: {e}")

        return 0

    def _estimate_event_count(self, track: Dict) -> int:
        """Estimate event count based on track characteristics."""
        title = track.get('title', '').lower()
        is_default = track.get('is_default', False)
        is_forced = track.get('is_forced', False)

        # Forced tracks are typically signs/songs or forced English (foreign dialogue)
        if is_forced:
            return 25

        # Check for forced English keywords (foreign dialogue only)
        forced_english_matches = sum(1 for keyword in self.FORCED_ENGLISH_KEYWORDS if keyword in title)
        if forced_english_matches > 0:
            # Forced English tracks typically have very few events (foreign dialogue only)
            return max(10, 30 - (forced_english_matches * 5))

        # Check title for other negative keywords
        negative_matches = sum(1 for keyword in self.NEGATIVE_KEYWORDS if keyword in title)
        if negative_matches > 0:
            # More negative keywords = more likely to be signs/songs
            return max(15, 50 - (negative_matches * 10))

        # Check for positive keywords
        positive_matches = sum(1 for keyword in self.POSITIVE_KEYWORDS if keyword in title)
        if positive_matches > 0:
            return 450  # Likely dialogue track

        # Default tracks are often dialogue
        if is_default:
            return 400

        # No clear indicators - assume moderate dialogue track
        return 350
    
    def _score_event_count(self, event_count: int, reasoning: List[str]) -> float:
        """Score based on event count analysis."""
        if event_count <= 0:
            reasoning.append(f"No event count available")
            return 0.0
        
        if event_count < self.SIGNS_SONGS_MAX_EVENTS:
            reasoning.append(f"Low event count ({event_count}) suggests signs/songs track")
            return -0.8
        elif event_count < self.MIN_DIALOGUE_EVENTS:
            reasoning.append(f"Below minimum dialogue threshold ({event_count} < {self.MIN_DIALOGUE_EVENTS})")
            return -0.3
        elif event_count >= self.TYPICAL_DIALOGUE_EVENTS:
            reasoning.append(f"High event count ({event_count}) indicates dialogue track")
            return 1.0
        else:
            # Linear scaling between MIN_DIALOGUE_EVENTS and TYPICAL_DIALOGUE_EVENTS
            score = (event_count - self.MIN_DIALOGUE_EVENTS) / (self.TYPICAL_DIALOGUE_EVENTS - self.MIN_DIALOGUE_EVENTS)
            reasoning.append(f"Moderate event count ({event_count}) - dialogue likelihood: {score:.2f}")
            return score
    
    def _score_title(self, title: str, reasoning: List[str]) -> float:
        """Score based on title pattern matching."""
        if not title:
            reasoning.append("No title information")
            return 0.0

        title_lower = title.lower()

        # Check for forced English keywords (highest priority negative)
        forced_matches = [kw for kw in self.FORCED_ENGLISH_KEYWORDS if kw in title_lower]
        if forced_matches:
            reasoning.append(f"Title indicates forced English subtitles (foreign dialogue only): {forced_matches}")
            return -1.0

        # Check for other negative keywords
        negative_matches = [kw for kw in self.NEGATIVE_KEYWORDS if kw in title_lower]
        if negative_matches:
            reasoning.append(f"Title contains negative keywords: {negative_matches}")
            return -1.0

        # Check for positive keywords
        positive_matches = [kw for kw in self.POSITIVE_KEYWORDS if kw in title_lower]
        if positive_matches:
            reasoning.append(f"Title contains positive keywords: {positive_matches}")
            return 1.0

        # Neutral title
        reasoning.append(f"Neutral title: '{title}'")
        return 0.0
    
    def _score_content(self, track: Dict, video_path: Optional[Path] = None, reasoning: List[str] = None) -> float:
        """Score based on content analysis."""
        if reasoning is None:
            reasoning = []

        # Try to extract and analyze content
        if video_path and video_path.exists():
            try:
                content_score = self._analyze_subtitle_content(track, video_path)
                if content_score is not None:
                    if content_score > 0.5:
                        reasoning.append(f"Content analysis suggests dialogue track (score: {content_score:.2f})")
                    elif content_score < -0.5:
                        reasoning.append(f"Content analysis suggests signs/songs track (score: {content_score:.2f})")
                    else:
                        reasoning.append(f"Content analysis inconclusive (score: {content_score:.2f})")
                    return content_score
            except Exception as e:
                logger.debug(f"Content analysis failed: {e}")

        # Fallback to heuristic analysis
        reasoning.append("Using heuristic content analysis")
        return self._heuristic_content_analysis(track)

    def _analyze_subtitle_content(self, track: Dict, video_path: Path) -> Optional[float]:
        """Analyze actual subtitle content to determine if it's dialogue."""
        import tempfile
        import subprocess
        from core.subtitle_formats import SubtitleFormatFactory

        track_id = track.get('track_id', track.get('index'))
        if not track_id:
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as tmp_file:
                # Extract first 5 minutes for content analysis
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
                    "-map", f"0:{track_id}",
                    "-t", "300",  # First 5 minutes
                    "-c:s", "srt",
                    tmp_file.name
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=30)

                if result.returncode == 0:
                    # Parse and analyze content
                    sample_sub = SubtitleFormatFactory.parse_file(Path(tmp_file.name))
                    if sample_sub and sample_sub.events:
                        return self._analyze_text_patterns(sample_sub.events)

        except Exception as e:
            logger.debug(f"Failed to extract content for analysis: {e}")

        return None

    def _analyze_text_patterns(self, events) -> float:
        """Analyze text patterns to determine dialogue likelihood."""
        if not events:
            return 0.0

        dialogue_indicators = 0
        signs_indicators = 0
        forced_english_indicators = 0
        total_chars = 0
        total_events = min(len(events), 20)

        for event in events[:20]:  # Analyze first 20 events
            text = event.text.strip()
            if not text:
                continue

            total_chars += len(text)

            # Dialogue indicators
            if any(char in text for char in '.,!?'):
                dialogue_indicators += 2
            if any(word in text.lower() for word in ['i', 'you', 'we', 'they', 'he', 'she']):
                dialogue_indicators += 1
            if len(text.split()) > 5:  # Longer sentences
                dialogue_indicators += 1
            if '"' in text or "'" in text:  # Quoted speech
                dialogue_indicators += 2

            # Forced English indicators (foreign dialogue patterns)
            if text.startswith('(') and text.endswith(')'):  # (Foreign language)
                forced_english_indicators += 3
            if any(phrase in text.lower() for phrase in ['speaking', 'in ', 'language']):  # Language indicators
                forced_english_indicators += 2
            if len(text.split()) <= 4 and total_events < 50:  # Short phrases in sparse track
                forced_english_indicators += 1
            if any(word in text.lower() for word in ['alien', 'foreign', 'untranslated']):  # Foreign content
                forced_english_indicators += 2

            # Signs/Songs indicators
            if text.isupper() and len(text) > 3:  # ALL CAPS (often signs)
                signs_indicators += 2
            if any(char in text for char in '♪♫♬'):  # Music symbols
                signs_indicators += 3
            if text.startswith('[') and text.endswith(']'):  # [Sound effects]
                signs_indicators += 2
            if len(text.split()) <= 2 and len(text) < 15:  # Very short text
                signs_indicators += 1

        # Calculate score
        if total_chars == 0:
            return 0.0

        dialogue_score = dialogue_indicators / total_events
        signs_score = signs_indicators / total_events
        forced_score = forced_english_indicators / total_events

        # If forced English indicators are high, penalize heavily
        if forced_score > 0.3:  # More than 30% of events show forced patterns
            return -0.8

        # Normalize to -1 to 1 range
        net_score = (dialogue_score - signs_score - (forced_score * 0.5)) / 5.0
        return max(-1.0, min(1.0, net_score))

    def _heuristic_content_analysis(self, track: Dict) -> float:
        """Heuristic content analysis based on track metadata."""
        title = track.get('title', '').lower()
        is_forced = track.get('is_forced', False)

        # Forced tracks are typically not main dialogue
        if is_forced:
            return -0.8

        # Check for forced English keywords (foreign dialogue only)
        forced_english_matches = [kw for kw in self.FORCED_ENGLISH_KEYWORDS if kw in title]
        if forced_english_matches:
            return -0.9  # Strongly penalize forced English tracks

        # Check for positive content-related keywords in title
        if any(word in title for word in ['full', 'complete', 'dialogue', 'dialog', 'main', 'primary']):
            return 0.6

        # Check for negative content-related keywords
        if any(word in title for word in ['signs', 'songs', 'karaoke', 'lyrics']):
            return -0.7

        # Neutral
        return 0.0
    
    def _log_analysis_results(self, scores: List[TrackScore]) -> None:
        """Log the analysis results for debugging."""
        logger.info("Subtitle track analysis results:")
        logger.info("-" * 80)
        
        for i, score in enumerate(scores, 1):
            status = "✅ DIALOGUE" if score.is_dialogue_candidate else "❌ NON-DIALOGUE"
            logger.info(f"#{i} Track {score.track_id}: {status} (Score: {score.total_score:.3f})")
            logger.info(f"    Title: '{score.title}'")
            logger.info(f"    Events: {score.event_count}")
            logger.info(f"    Scores: Event={score.event_count_score:.2f}, Title={score.title_score:.2f}, Content={score.content_score:.2f}")
            
            for reason in score.reasoning:
                logger.info(f"    - {reason}")
            logger.info("")
    
    def select_best_dialogue_track(self, scores: List[TrackScore]) -> Optional[TrackScore]:
        """
        Select the best dialogue track from analyzed scores.
        
        Args:
            scores: List of TrackScore objects (should be sorted by score)
            
        Returns:
            Best dialogue track or None if no suitable track found
        """
        if not scores:
            logger.warning("No tracks to analyze")
            return None
        
        # Find dialogue candidates
        dialogue_candidates = [s for s in scores if s.is_dialogue_candidate]
        
        if dialogue_candidates:
            best_track = dialogue_candidates[0]
            logger.info(f"✅ Selected dialogue track: {best_track.track_id} '{best_track.title}' (Score: {best_track.total_score:.3f})")
            return best_track
        
        # Fallback: select track with highest event count
        best_by_events = max(scores, key=lambda x: x.event_count)
        logger.warning(f"⚠️ No clear dialogue candidates found. Selecting track with most events: {best_by_events.track_id} ({best_by_events.event_count} events)")
        return best_by_events
