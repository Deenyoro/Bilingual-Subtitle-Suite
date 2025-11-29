"""
Language detection and mapping utilities for subtitle processing.

This module provides functions for:
- Detecting Chinese vs English text content
- Mapping language codes to standard formats
- Finding external subtitle files by language patterns
"""

import re
from pathlib import Path
from typing import List, Optional, Set
from utils.constants import (
    CHINESE_CODES, ENGLISH_CODES, CHINESE_PATTERNS, ENGLISH_PATTERNS
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


class LanguageDetector:
    """Handles language detection and mapping for subtitle files."""
    
    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detect language from text content with enhanced multi-language support.

        Args:
            text: Text to analyze

        Returns:
            Language code ('zh', 'en', 'ja', 'ko', etc.) or 'unknown'

        Example:
            >>> lang = LanguageDetector.detect_language("你好世界")
            >>> print(f"Detected language: {lang}")  # "zh"
        """
        # Check for CJK characters
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # Common Chinese characters
                return 'zh'
            if '\u3400' <= char <= '\u4dbf':  # Extended Chinese characters
                return 'zh'
            if '\u3040' <= char <= '\u309f':  # Hiragana
                return 'ja'
            if '\u30a0' <= char <= '\u30ff':  # Katakana
                return 'ja'
            if '\uac00' <= char <= '\ud7af':  # Korean Hangul
                return 'ko'

        # Check for common English patterns (more comprehensive)
        english_words = ['the', 'and', 'you', 'that', 'was', 'for', 'are', 'with', 'his', 'they',
                         'have', 'this', 'will', 'your', 'from', 'know', 'want', 'been',
                         'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'how',
                         'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than',
                         'them', 'well', 'were', 'what', 'where', 'who', 'would', 'there', 'could']

        text_lower = text.lower()
        english_word_count = sum(1 for word in english_words if word in text_lower)

        # If we find multiple English words or the text is primarily Latin characters, assume English
        if english_word_count >= 2 or (english_word_count >= 1 and len(text) > 10):
            return 'en'

        # Check if text is primarily Latin characters (likely English or other Latin-based language)
        latin_chars = sum(1 for char in text if char.isalpha() and ord(char) < 256)
        total_chars = sum(1 for char in text if char.isalpha())

        if total_chars > 5 and latin_chars / total_chars > 0.8:
            return 'en'  # Default to English for Latin-based text

        return 'unknown'

    @staticmethod
    def detect_language_legacy(text: str) -> str:
        """
        Legacy language detection for backward compatibility.

        Args:
            text: Text to analyze

        Returns:
            'chinese' if Chinese characters detected, 'english' otherwise
        """
        # Check for CJK characters
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # Common Chinese characters
                return 'chinese'
            if '\u3400' <= char <= '\u4dbf':  # Extended Chinese characters
                return 'chinese'
        return 'english'
    
    @staticmethod
    def is_chinese_language_code(lang_code: str) -> bool:
        """
        Check if a language code represents Chinese.
        
        Args:
            lang_code: Language code to check
            
        Returns:
            True if the code represents Chinese
            
        Example:
            >>> is_chinese = LanguageDetector.is_chinese_language_code("zh")
            >>> print(f"Is Chinese: {is_chinese}")  # True
        """
        return lang_code.lower() in CHINESE_CODES
    
    @staticmethod
    def is_english_language_code(lang_code: str) -> bool:
        """
        Check if a language code represents English.
        
        Args:
            lang_code: Language code to check
            
        Returns:
            True if the code represents English
            
        Example:
            >>> is_english = LanguageDetector.is_english_language_code("en")
            >>> print(f"Is English: {is_english}")  # True
        """
        return lang_code.lower() in ENGLISH_CODES
    
    @staticmethod
    def normalize_language_code(lang_code: str) -> Optional[str]:
        """
        Normalize a language code to standard format.
        
        Args:
            lang_code: Language code to normalize
            
        Returns:
            Normalized language code ('chinese', 'english', or None)
            
        Example:
            >>> normalized = LanguageDetector.normalize_language_code("zh-CN")
            >>> print(f"Normalized: {normalized}")  # "chinese"
        """
        lang_lower = lang_code.lower()
        
        if lang_lower in CHINESE_CODES:
            return 'chinese'
        elif lang_lower in ENGLISH_CODES:
            return 'english'
        else:
            return None
    
    @staticmethod
    def find_external_subtitle(video_path: Path, is_chinese: bool = False) -> Optional[Path]:
        """
        Find external subtitle files for a video based on language patterns.
        
        Args:
            video_path: Path to the video file
            is_chinese: True to look for Chinese subtitles, False for English
            
        Returns:
            Path to the best matching subtitle file or None
            
        Example:
            >>> chinese_sub = LanguageDetector.find_external_subtitle(
            ...     Path("movie.mkv"), is_chinese=True
            ... )
        """
        video_dir = video_path.parent
        base_name = video_path.stem
        
        logger.info(f"Searching for external {'Chinese' if is_chinese else 'English'} "
                   f"subtitle for: {video_path.name}")
        
        # Build search patterns
        if is_chinese:
            lang_patterns = CHINESE_PATTERNS
        else:
            lang_patterns = ENGLISH_PATTERNS
        
        # Search for subtitle files
        candidates = []
        
        for file in video_dir.iterdir():
            if not file.name.startswith(base_name):
                continue
            
            file_lower = file.name.lower()
            
            # Check if it's a subtitle file
            if not any(file_lower.endswith(ext) for ext in ['.srt', '.ass', '.ssa', '.vtt']):
                continue
            
            # Check for language patterns
            for pattern in lang_patterns:
                if pattern in file_lower:
                    candidates.append(file)
                    break
        
        # If no language-specific files found, check the default subtitle
        if not candidates:
            for ext in ['.srt', '.ass', '.ssa', '.vtt']:
                default_sub = video_dir / (base_name + ext)
                if default_sub.exists():
                    # Try to detect language from content
                    try:
                        with open(default_sub, 'r', encoding='utf-8', errors='ignore') as f:
                            sample = f.read(4096)
                            detected_lang = LanguageDetector.detect_language(sample)
                            
                            if is_chinese and detected_lang == 'chinese':
                                candidates.append(default_sub)
                            elif not is_chinese and detected_lang == 'english':
                                candidates.append(default_sub)
                    except Exception as e:
                        logger.debug(f"Failed to read {default_sub} for language detection: {e}")
        
        if candidates:
            # Sort by specificity (more specific language codes first)
            candidates.sort(key=lambda x: len(x.name))
            logger.info(f"Found external subtitle: {candidates[0].name}")
            return candidates[0]
        
        logger.info(f"No external {'Chinese' if is_chinese else 'English'} subtitle found")
        return None
    
    @staticmethod
    def get_language_patterns(language: str) -> List[str]:
        """
        Get filename patterns for a specific language.
        
        Args:
            language: Language name ('chinese' or 'english')
            
        Returns:
            List of filename patterns for the language
            
        Raises:
            ValueError: If language is not supported
            
        Example:
            >>> patterns = LanguageDetector.get_language_patterns('chinese')
            >>> print(f"Chinese patterns: {patterns}")
        """
        if language.lower() == 'chinese':
            return CHINESE_PATTERNS.copy()
        elif language.lower() == 'english':
            return ENGLISH_PATTERNS.copy()
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    @staticmethod
    def get_language_codes(language: str) -> Set[str]:
        """
        Get language codes for a specific language.
        
        Args:
            language: Language name ('chinese' or 'english')
            
        Returns:
            Set of language codes for the language
            
        Raises:
            ValueError: If language is not supported
            
        Example:
            >>> codes = LanguageDetector.get_language_codes('chinese')
            >>> print(f"Chinese codes: {codes}")
        """
        if language.lower() == 'chinese':
            return CHINESE_CODES.copy()
        elif language.lower() == 'english':
            return ENGLISH_CODES.copy()
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    @staticmethod
    def detect_subtitle_language(file_path: Path, sample_size: int = 4096) -> str:
        """
        Detect the language of a subtitle file by analyzing its content.

        Args:
            file_path: Path to the subtitle file
            sample_size: Number of characters to sample for detection

        Returns:
            Detected language code ('zh', 'en', 'ja', etc.) or 'unknown'

        Example:
            >>> lang = LanguageDetector.detect_subtitle_language(Path("subtitle.srt"))
            >>> print(f"Subtitle language: {lang}")
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                sample = f.read(sample_size)
                return LanguageDetector.detect_language(sample)
        except Exception as e:
            logger.warning(f"Failed to detect language for {file_path}: {e}")
            return 'unknown'  # Default fallback

    @staticmethod
    def detect_language_from_filename(filename: str) -> str:
        """
        Detect language from filename patterns.

        Args:
            filename: Filename to analyze

        Returns:
            Language code ('zh', 'en', 'ja', etc.) or 'unknown'
        """
        filename_lower = str(filename).lower()

        # Chinese patterns
        if any(pattern in filename_lower for pattern in ['.zh.', '.chi.', '.chs.', '.cht.', '.cn.', '.chinese.', '_zh.', '_chi.', '_chs.', '_cht.', '_cn.', '_chinese.']):
            return 'zh'

        # Japanese patterns
        if any(pattern in filename_lower for pattern in ['.ja.', '.jp.', '.jpn.', '.japanese.', '_ja.', '_jp.', '_jpn.', '_japanese.']):
            return 'ja'

        # Korean patterns
        if any(pattern in filename_lower for pattern in ['.ko.', '.kr.', '.kor.', '.korean.', '_ko.', '_kr.', '_kor.', '_korean.']):
            return 'ko'

        # French patterns
        if any(pattern in filename_lower for pattern in ['.fr.', '.fre.', '.fra.', '.french.', '_fr.', '_fre.', '_fra.', '_french.']):
            return 'fr'

        # German patterns
        if any(pattern in filename_lower for pattern in ['.de.', '.ger.', '.deu.', '.german.', '_de.', '_ger.', '_deu.', '_german.']):
            return 'de'

        # Spanish patterns
        if any(pattern in filename_lower for pattern in ['.es.', '.spa.', '.spanish.', '_es.', '_spa.', '_spanish.']):
            return 'es'

        # English patterns
        if any(pattern in filename_lower for pattern in ['.en.', '.eng.', '.english.', '_en.', '_eng.', '_english.']):
            return 'en'

        return 'unknown'

    @staticmethod
    def generate_bilingual_filename(base_path: Path, lang1: str, lang2: str, format_ext: str) -> Path:
        """
        Generate bilingual filename based on detected languages.

        Args:
            base_path: Base file path (can be video or subtitle file)
            lang1: First language code
            lang2: Second language code
            format_ext: File format extension (without dot)

        Returns:
            Generated filename with language codes

        Example:
            Input: Planet.of.the.Apes.1968.1080p.Bluray.zh.srt, lang1='zh', lang2='en'
            Output: Planet.of.the.Apes.1968.1080p.Bluray.zh-en.srt
        """
        base_name = base_path.stem  # Filename without last extension
        base_dir = base_path.parent

        # Strip existing language codes from the base name
        # Common patterns: .zh, .en, .chi, .eng, .chs, .cht, .jpn, .kor, etc.
        lang_patterns = [
            '.zh', '.en', '.chi', '.eng', '.chs', '.cht', '.cn', '.chinese', '.english',
            '.ja', '.jp', '.jpn', '.japanese', '.ko', '.kr', '.kor', '.korean',
            '.fr', '.fre', '.fra', '.french', '.de', '.ger', '.deu', '.german',
            '.es', '.spa', '.spanish', '.bilingual', '.dual'
        ]

        # Remove language suffix from base name (case insensitive)
        clean_base = base_name
        for pattern in lang_patterns:
            if clean_base.lower().endswith(pattern):
                clean_base = clean_base[:-len(pattern)]
                break  # Only remove one language code

        # Check if both languages were detected
        if lang1 != 'unknown' and lang2 != 'unknown':
            # Order languages with foreign language first, then English
            if lang1 == 'en' and lang2 != 'en':
                languages = [lang2, lang1]  # Foreign first, then English
            elif lang2 == 'en' and lang1 != 'en':
                languages = [lang1, lang2]  # Foreign first, then English
            else:
                # If neither is English or both are non-English, sort alphabetically
                languages = sorted([lang1, lang2])

            lang_suffix = '-'.join(languages)
            return base_dir / f"{clean_base}.{lang_suffix}.{format_ext}"
        else:
            # Fallback to generic bilingual naming
            logger.info(f"Could not detect both languages (detected: {lang1}, {lang2}), using fallback naming")
            return base_dir / f"{clean_base}.bilingual.{format_ext}"

    @staticmethod
    def get_language_code_from_track(track) -> str:
        """
        Get standardized language code from subtitle track.

        Args:
            track: SubtitleTrack object

        Returns:
            Standardized language code ('zh', 'en', 'ja', etc.) or 'unknown'
        """
        if not hasattr(track, 'language') or not track.language:
            return 'unknown'

        lang = track.language.lower()

        # Chinese variants
        if lang in {'chi', 'zho', 'chs', 'cht', 'zh', 'chinese', 'cn', 'cmn', 'yue', 'hak', 'nan'}:
            return 'zh'

        # English variants
        if lang in {'eng', 'en', 'english', 'enm', 'ang'}:
            return 'en'

        # Japanese variants
        if lang in {'jpn', 'ja', 'japanese'}:
            return 'ja'

        # Korean variants
        if lang in {'kor', 'ko', 'korean'}:
            return 'ko'

        # French variants
        if lang in {'fre', 'fr', 'french', 'fra'}:
            return 'fr'

        # German variants
        if lang in {'ger', 'de', 'german', 'deu'}:
            return 'de'

        # Spanish variants
        if lang in {'spa', 'es', 'spanish'}:
            return 'es'

        # Return first 2-3 characters as fallback
        return lang[:2] if len(lang) >= 2 else lang


