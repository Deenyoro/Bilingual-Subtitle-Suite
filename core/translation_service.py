#!/usr/bin/env python3
"""
Google Cloud Translation service for subtitle alignment assistance.

This module provides translation capabilities to help align subtitles
when source and reference subtitles are in different languages.
"""

import os
import time
import requests
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from utils.logging_config import get_logger

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file if it exists
    _dotenv_available = True
except ImportError:
    _dotenv_available = False

logger = get_logger(__name__)


@dataclass
class TranslationResult:
    """Result of a translation operation."""
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    confidence: float = 0.0


class GoogleTranslationService:
    """Google Cloud Translation API service for subtitle alignment."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the translation service.

        Args:
            api_key: Google Cloud Translation API key. If None, will try to get from environment.
        """
        # Try to get API key from multiple sources
        self.api_key = api_key or os.getenv('GOOGLE_TRANSLATE_API_KEY')

        if not self.api_key:
            error_msg = (
                "Google Translation API key not provided. Please:\n"
                "1. Set GOOGLE_TRANSLATE_API_KEY in your .env file, or\n"
                "2. Set GOOGLE_TRANSLATE_API_KEY environment variable, or\n"
                "3. Pass api_key parameter to the constructor\n"
                f"Environment file support: {'Available' if _dotenv_available else 'Not available (install python-dotenv)'}"
            )
            raise ValueError(error_msg)

        # Validate API key format
        if not self.api_key.startswith('AIza'):
            logger.warning("API key format may be invalid. Google API keys typically start with 'AIza'")

        self.base_url = "https://translation.googleapis.com/language/translate/v2"
        self.detect_url = "https://translation.googleapis.com/language/translate/v2/detect"

        # Rate limiting and retry configuration
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        self.max_retries = 3
        self.retry_delay = 1.0
        self.max_retry_delay = 60.0  # Maximum retry delay

        # API quota tracking
        self.request_count = 0
        self.daily_quota_exceeded = False

        logger.info(f"Google Translation service initialized (dotenv: {'available' if _dotenv_available else 'unavailable'})")
    
    def detect_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the given text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Language code (e.g., 'en', 'zh', 'es') or None if detection fails
        """
        if not text or not text.strip():
            return None
        
        try:
            self._rate_limit()
            
            params = {
                'key': self.api_key,
                'q': text[:1000]  # Limit text length for detection
            }
            
            response = requests.post(self.detect_url, data=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and 'detections' in data['data']:
                detections = data['data']['detections'][0]
                if detections:
                    language = detections[0]['language']
                    confidence = detections[0].get('confidence', 0.0)
                    
                    logger.debug(f"Detected language: {language} (confidence: {confidence:.2f})")
                    return language
            
            return None
            
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return None
    
    def translate_text(self, text: str, target_language: str,
                      source_language: Optional[str] = None) -> Optional[TranslationResult]:
        """
        Translate text to the target language with retry logic.

        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'en', 'zh')
            source_language: Source language code (auto-detected if None)

        Returns:
            TranslationResult object or None if translation fails
        """
        if not text or not text.strip():
            return None

        if self.daily_quota_exceeded:
            logger.warning("Daily quota exceeded, skipping translation")
            return None

        for attempt in range(self.max_retries + 1):
            try:
                self._rate_limit()

                params = {
                    'key': self.api_key,
                    'q': text,
                    'target': target_language
                }

                if source_language:
                    params['source'] = source_language

                response = requests.post(self.base_url, data=params, timeout=15)
                self.request_count += 1

                # Handle specific HTTP status codes
                if response.status_code == 429:  # Too Many Requests
                    logger.warning(f"Rate limit exceeded (attempt {attempt + 1})")
                    if attempt < self.max_retries:
                        delay = min(self.retry_delay * (2 ** attempt), self.max_retry_delay)
                        logger.info(f"Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error("Max retries exceeded for rate limiting")
                        return None

                elif response.status_code == 403:  # Quota exceeded
                    error_data = response.json() if response.content else {}
                    error_message = error_data.get('error', {}).get('message', 'Unknown error')

                    if 'quota' in error_message.lower() or 'limit' in error_message.lower():
                        logger.error(f"API quota exceeded: {error_message}")
                        self.daily_quota_exceeded = True
                        return None
                    else:
                        logger.error(f"API access forbidden: {error_message}")
                        return None

                response.raise_for_status()
                data = response.json()

                if 'data' in data and 'translations' in data['data']:
                    translation = data['data']['translations'][0]
                    translated_text = translation['translatedText']
                    detected_source = translation.get('detectedSourceLanguage', source_language or 'unknown')

                    return TranslationResult(
                        original_text=text,
                        translated_text=translated_text,
                        source_language=detected_source,
                        target_language=target_language,
                        confidence=1.0  # Google Translate doesn't provide confidence scores
                    )

                logger.warning("Unexpected response format from translation API")
                return None

            except requests.exceptions.Timeout:
                logger.warning(f"Translation request timeout (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    delay = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error("Max retries exceeded for timeout")
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Translation request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    delay = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error("Max retries exceeded for request error")
                    return None

            except Exception as e:
                logger.error(f"Unexpected translation error: {e}")
                return None

        return None
    
    def translate_batch(self, texts: List[str], target_language: str,
                       source_language: Optional[str] = None,
                       progress_callback: Optional[callable] = None) -> List[Optional[TranslationResult]]:
        """
        Translate multiple texts with progress tracking.
        
        Args:
            texts: List of texts to translate
            target_language: Target language code
            source_language: Source language code (auto-detected if None)
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of TranslationResult objects (None for failed translations)
        """
        results = []
        total = len(texts)
        
        logger.info(f"Starting batch translation of {total} texts to {target_language}")
        
        for i, text in enumerate(texts):
            if progress_callback:
                progress_callback(i, total)
            
            result = self.translate_text(text, target_language, source_language)
            results.append(result)
            
            if result:
                logger.debug(f"Translated ({i+1}/{total}): '{text[:50]}...' -> '{result.translated_text[:50]}...'")
            else:
                logger.warning(f"Failed to translate ({i+1}/{total}): '{text[:50]}...'")
        
        if progress_callback:
            progress_callback(total, total)
        
        successful = sum(1 for r in results if r is not None)
        logger.info(f"Batch translation completed: {successful}/{total} successful")
        
        return results
    
    def _rate_limit(self):
        """Implement rate limiting to avoid API quota issues."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get_supported_languages(self) -> Dict[str, str]:
        """
        Get list of supported languages.
        
        Returns:
            Dictionary mapping language codes to language names
        """
        try:
            self._rate_limit()
            
            params = {
                'key': self.api_key,
                'target': 'en'  # Get language names in English
            }
            
            url = f"{self.base_url}/languages"
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and 'languages' in data['data']:
                languages = {}
                for lang in data['data']['languages']:
                    code = lang['language']
                    name = lang.get('name', code)
                    languages[code] = name
                
                logger.debug(f"Retrieved {len(languages)} supported languages")
                return languages
            
            return {}
            
        except Exception as e:
            logger.warning(f"Failed to get supported languages: {e}")
            return {}
    
    def test_connection(self) -> bool:
        """
        Test the connection to Google Translation API.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            result = self.translate_text("Hello", "es")
            return result is not None
        except Exception as e:
            logger.error(f"Translation service connection test failed: {e}")
            return False

    def translate_subtitle_events(self, events: List, target_language: str = 'en',
                                 source_language: str = None, progress_callback=None,
                                 limit: int = None) -> List[TranslationResult]:
        """
        Translate a list of subtitle events with optional limit for efficiency

        Args:
            events: List of subtitle events to translate
            target_language: Target language code (default: 'en')
            source_language: Source language code (auto-detect if None)
            progress_callback: Optional callback function for progress updates
            limit: Maximum number of events to translate (None for all)

        Returns:
            List of TranslationResult objects
        """
        if not events:
            return []

        # Apply limit if specified for efficiency
        events_to_translate = events[:limit] if limit else events
        total_events = len(events_to_translate)

        results = []

        logger.info(f"Starting translation of {total_events} subtitle events" +
                   (f" (limited from {len(events)})" if limit else ""))

        for i, event in enumerate(events_to_translate):
            if hasattr(event, 'text'):
                text = event.text
            else:
                text = str(event)

            if not text.strip():
                # Skip empty text
                results.append(TranslationResult(
                    original_text=text,
                    translated_text=text,
                    source_language='unknown',
                    target_language=target_language,
                    confidence=1.0
                ))
                continue

            try:
                result = self.translate_text(text, target_language, source_language)
                if result:
                    results.append(result)
                else:
                    # Add failed result
                    results.append(TranslationResult(
                        original_text=text,
                        translated_text=text,  # Fallback to original
                        source_language='unknown',
                        target_language=target_language,
                        confidence=0.0,
                        error="Translation failed"
                    ))

                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_events)

                # Rate limiting
                self._rate_limit()

            except Exception as e:
                logger.error(f"Failed to translate event {i}: {e}")
                # Add failed result
                results.append(TranslationResult(
                    original_text=text,
                    translated_text=text,  # Fallback to original
                    source_language='unknown',
                    target_language=target_language,
                    confidence=0.0,
                    error=str(e)
                ))

        logger.info(f"Translation completed. {len(results)} results generated")
        return results

    def find_alignment_point_with_translation(self, source_events: List, reference_events: List,
                                            target_language: str = 'en', source_language: str = None,
                                            translation_limit: int = 20, confidence_threshold: float = 0.5) -> tuple:
        """
        Find optimal alignment point using enhanced translation approach for large timing offsets.

        This method implements an enhanced alignment strategy:
        1. Try standard limited translation approach first
        2. If no match found, use expanded cross-language sampling
        3. Handle large timing offsets by sampling from different positions
        4. Return the best alignment point with confidence score

        Args:
            source_events: Source subtitle events to align
            reference_events: Reference subtitle events
            target_language: Target language for translation
            source_language: Source language (auto-detect if None)
            translation_limit: Number of source events to translate (default: 20)
            confidence_threshold: Minimum confidence for alignment point (default: 0.5)

        Returns:
            Tuple of (source_index, reference_index, confidence) or (None, None, 0.0) if no good match
        """
        from core.similarity_alignment import SimilarityAligner

        if not source_events or not reference_events:
            return None, None, 0.0

        logger.info(f"Finding alignment point using enhanced translation approach")

        # Phase 1: Try standard limited translation approach
        result = self._find_alignment_standard(source_events, reference_events, target_language,
                                             source_language, translation_limit, confidence_threshold)
        if result[0] is not None:
            return result

        # Phase 2: Enhanced cross-language sampling for large offsets
        logger.info("Standard approach failed, trying enhanced cross-language sampling")
        result = self._find_alignment_cross_language_sampling(source_events, reference_events,
                                                            target_language, source_language, confidence_threshold)
        if result[0] is not None:
            return result

        # Phase 3: Return best effort result
        logger.warning(f"❌ No reliable alignment point found with enhanced approach")
        return None, None, 0.0

    def _find_alignment_standard(self, source_events: List, reference_events: List,
                               target_language: str, source_language: str,
                               translation_limit: int, confidence_threshold: float) -> tuple:
        """Standard alignment approach - translate first N events."""
        from core.similarity_alignment import SimilarityAligner

        logger.info(f"Translating first {translation_limit} source events for alignment detection")

        # Step 1: Translate only the first few source events for efficiency
        translation_results = self.translate_subtitle_events(
            source_events,
            target_language=target_language,
            source_language=source_language,
            limit=translation_limit
        )

        if not translation_results:
            logger.warning("No translation results obtained")
            return None, None, 0.0

        # Step 2: Create translated text list for similarity analysis
        translated_texts = [result.translated_text for result in translation_results]
        reference_texts = [event.text for event in reference_events]

        # Step 3: Use similarity aligner to find best alignment point
        aligner = SimilarityAligner()

        best_source_idx = None
        best_ref_idx = None
        best_confidence = 0.0

        logger.debug(f"Analyzing {len(translated_texts)} translated texts against {len(reference_texts)} reference texts")

        # Try each translated source event against all reference events
        # Prioritize early matches by adding position bonus
        for src_idx, translated_text in enumerate(translated_texts):
            if not translated_text.strip():
                continue

            for ref_idx, ref_text in enumerate(reference_texts):
                if not ref_text.strip():
                    continue

                # Calculate similarity between translated source and reference
                similarity = aligner.calculate_similarity(translated_text, ref_text)

                # Add position bonus to prioritize early matches (first dialogue pairs)
                # Early matches get up to 0.1 bonus, decreasing with position
                position_bonus = max(0, 0.1 - (src_idx + ref_idx) * 0.005)
                adjusted_similarity = similarity + position_bonus

                if adjusted_similarity > best_confidence:
                    best_confidence = adjusted_similarity
                    best_source_idx = src_idx
                    best_ref_idx = ref_idx
                    logger.debug(f"New best match: src[{src_idx}] -> ref[{ref_idx}] "
                               f"(similarity: {similarity:.3f}, bonus: {position_bonus:.3f}, total: {adjusted_similarity:.3f})")
                    logger.debug(f"  Source: '{source_events[src_idx].text}'")
                    logger.debug(f"  Translated: '{translated_text}'")
                    logger.debug(f"  Reference: '{ref_text}'")

        # Step 4: Check if confidence meets threshold
        if best_confidence >= confidence_threshold:
            logger.info(f"✅ Found reliable alignment point: source[{best_source_idx}] -> reference[{best_ref_idx}] "
                       f"(confidence: {best_confidence:.3f})")
            return best_source_idx, best_ref_idx, best_confidence
        else:
            logger.debug(f"Standard approach: Best confidence {best_confidence:.3f} below threshold {confidence_threshold}")
            return None, None, best_confidence

    def _find_alignment_cross_language_sampling(self, source_events: List, reference_events: List,
                                               target_language: str, source_language: str,
                                               confidence_threshold: float) -> tuple:
        """
        Enhanced cross-language sampling for large timing offsets.

        This method samples events from different positions in both tracks to handle
        scenarios where matching content appears at very different timing positions.
        """
        from core.similarity_alignment import SimilarityAligner

        # Sample positions from both tracks to handle large offsets
        max_samples = 15  # Increased sample size for better coverage
        source_len = len(source_events)
        ref_len = len(reference_events)

        # Create sample positions - spread across the entire track
        source_positions = []
        ref_positions = []

        if source_len <= max_samples:
            source_positions = list(range(source_len))
        else:
            # Sample from beginning, middle, and end sections
            step = source_len // max_samples
            source_positions = [i * step for i in range(max_samples)]
            # Ensure we don't exceed bounds
            source_positions = [min(pos, source_len - 1) for pos in source_positions]

        if ref_len <= max_samples:
            ref_positions = list(range(ref_len))
        else:
            step = ref_len // max_samples
            ref_positions = [i * step for i in range(max_samples)]
            ref_positions = [min(pos, ref_len - 1) for pos in ref_positions]

        logger.info(f"Cross-language sampling: {len(source_positions)} source positions, {len(ref_positions)} reference positions")

        # Extract sample events for translation
        sample_source_events = [source_events[pos] for pos in source_positions]

        # Translate sample source events
        translation_results = self.translate_subtitle_events(
            sample_source_events,
            target_language=target_language,
            source_language=source_language,
            limit=len(sample_source_events)
        )

        if not translation_results:
            logger.warning("Cross-language sampling: No translation results obtained")
            return None, None, 0.0

        # Create similarity aligner
        aligner = SimilarityAligner()

        best_source_idx = None
        best_ref_idx = None
        best_confidence = 0.0

        logger.debug(f"Cross-language analysis: {len(translation_results)} translated samples vs {len(ref_positions)} reference samples")

        # Compare each translated sample against all reference samples
        for i, translation_result in enumerate(translation_results):
            if not translation_result.translated_text.strip():
                continue

            translated_text = translation_result.translated_text
            actual_source_idx = source_positions[i]

            for ref_pos in ref_positions:
                ref_event = reference_events[ref_pos]
                if not ref_event.text.strip():
                    continue

                # Calculate similarity
                similarity = aligner.calculate_similarity(translated_text, ref_event.text)

                if similarity > best_confidence:
                    best_confidence = similarity
                    best_source_idx = actual_source_idx
                    best_ref_idx = ref_pos

                    logger.debug(f"Cross-language match: src[{actual_source_idx}] -> ref[{ref_pos}] "
                               f"(confidence: {similarity:.3f})")
                    logger.debug(f"  Source: {source_events[actual_source_idx].text[:50]}...")
                    logger.debug(f"  Translated: {translated_text[:50]}...")
                    logger.debug(f"  Reference: {ref_event.text[:50]}...")

        # Check if we found a good match
        if best_confidence >= confidence_threshold:
            logger.info(f"✅ Cross-language sampling found alignment: source[{best_source_idx}] -> reference[{best_ref_idx}] "
                       f"(confidence: {best_confidence:.3f})")
            return best_source_idx, best_ref_idx, best_confidence
        else:
            logger.info(f"Cross-language sampling: Best confidence {best_confidence:.3f} below threshold {confidence_threshold}")
            return None, None, best_confidence


def get_translation_service(api_key: Optional[str] = None) -> Optional[GoogleTranslationService]:
    """
    Get a translation service instance with enhanced error handling.

    Args:
        api_key: Optional API key. If None, will try environment variable.

    Returns:
        GoogleTranslationService instance or None if initialization fails
    """
    try:
        service = GoogleTranslationService(api_key)

        # Test the connection
        if service.test_connection():
            logger.info("✅ Translation service initialized and tested successfully")
            return service
        else:
            logger.warning("⚠️ Translation service initialized but connection test failed")
            return service  # Return anyway, might work for actual requests

    except ValueError as e:
        # API key related errors
        logger.warning(f"Translation service configuration error: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize translation service: {e}")
        return None
