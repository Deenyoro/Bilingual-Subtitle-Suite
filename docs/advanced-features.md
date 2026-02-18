# Advanced Features Guide

Comprehensive guide to the advanced capabilities of the Bilingual Subtitle Suite.

## Table of Contents
- [Enhanced Alignment System](#enhanced-alignment-system)
- [Translation-Assisted Alignment](#translation-assisted-alignment)
- [Manual Synchronization Interface](#manual-synchronization-interface)
- [Intelligent Track Selection](#intelligent-track-selection)
- [Global Track Synchronization](#global-track-synchronization)
- [Confidence Scoring and Thresholds](#confidence-scoring-and-thresholds)
- [Advanced Configuration](#advanced-configuration)

## Enhanced Alignment System

The enhanced alignment system uses a sophisticated two-phase approach for optimal subtitle synchronization.

### Phase 1: Global Track Synchronization

**Purpose**: Correct large timing offsets between subtitle tracks before detailed alignment.

**How it works**:
1. **Reference Track Identification**: Embedded tracks or earlier timestamps used as reference
2. **Anchor Point Detection**: Multiple strategies to find matching subtitle pairs
3. **Offset Calculation**: Calculate global time difference between tracks
4. **Global Alignment**: Apply offset to entire target track

### Phase 2: Detailed Event Alignment

After global synchronization, the system performs detailed alignment:
1. **Time-Based Alignment**: Match events within ±0.5s (configurable)
2. **Content-Based Fallback**: Use similarity analysis for unmatched events
3. **Translation-Assisted Matching**: Optional semantic matching
4. **Event Merging**: Create bilingual subtitle events
5. **Timing Optimization**: Adjust timing for optimal display

### Enabling Enhanced Alignment

**CLI:**
```bash
biss merge movie.mkv --auto-align
```

**Interactive Mode:**
```
Enhanced Alignment Options:
Enable enhanced alignment? (y/n): y
```

### Sync Strategies

#### Strategy A: First-Line Comparison
```bash
biss merge movie.mkv --auto-align --sync-strategy first-line
```
- Compares first subtitle from each track
- Uses if timing difference ≤ 2.0 seconds
- Fast and simple, works for well-aligned tracks

#### Strategy B: Scan Forward
```bash
biss merge movie.mkv --auto-align --sync-strategy scan
```
- Scans first 10 entries from each track
- Finds closest matching pair within ±2.0 seconds
- Better for tracks with intro/credits timing differences

#### Strategy C: Translation-Assisted
```bash
biss merge movie.mkv --auto-align --sync-strategy translation --use-translation
```
- Uses Google Translate API for semantic matching
- Identifies content-based matches within first 10 entries
- Most accurate for cross-language alignment

#### Strategy D: Manual Selection
```bash
biss merge movie.mkv --auto-align --manual-align
```
- Interactive user interface
- Shows first 5 subtitle options with translations
- User selects best matching pair

## Translation-Assisted Alignment

### Setup

**Environment Variable:**
```bash
export GOOGLE_TRANSLATE_API_KEY="your-api-key-here"
```

**CLI Parameter:**
```bash
biss merge movie.mkv --use-translation --translation-api-key "your-key"
```

### How It Works

1. **Limited Translation Scope**: Translates only 5-10 entries to find initial sync point
2. **Semantic Matching**: Uses translated content for cross-language alignment
3. **Anchor Point Detection**: Finds best semantic match for global synchronization
4. **Cost Optimization**: Minimal API usage to reduce costs while maintaining accuracy

### Benefits

- **Cross-Language Accuracy**: Better alignment for bilingual subtitle pairs
- **Context Understanding**: Semantic matching beyond literal translation
- **Reduced Manual Intervention**: Automatic detection of matching content
- **Quality Validation**: Bidirectional translation for verification

### Usage Examples

**Basic translation-assisted alignment:**
```bash
biss merge anime.mkv --auto-align --use-translation
```

**High-precision with translation:**
```bash
biss merge movie.mkv --auto-align --use-translation \
  --sync-strategy translation --alignment-threshold 0.95
```

**Batch processing with translation:**
```bash
biss batch-merge "Season 01" --auto-align --use-translation \
  --auto-confirm
```

## Manual Synchronization Interface

### When to Use Manual Alignment

- **Large timing differences** between tracks (>5 seconds)
- **Complex content** with non-linear dialogue
- **Multiple language tracks** requiring semantic matching
- **Quality control** for critical projects
- **Learning/debugging** alignment issues

### Interface Overview

The manual synchronization interface provides:
- **Side-by-side comparison** of subtitle options
- **Bidirectional translation display** (when available)
- **Flexible anchor point selection** from different track indices
- **Millisecond-precise time shifting** with clear reference indication
- **Pre-anchor deletion** of mistimed content

### Step-by-Step Workflow

#### 1. Enable Manual Mode
```bash
biss merge video.mkv --auto-align --manual-align
```

#### 2. Review Anchor Options
```
================================================================================
MANUAL ANCHOR POINT SELECTION
================================================================================
Please select matching subtitle pairs for global synchronization.
Analyzing first 5 subtitle entries from each track.

Option 1:
  Track 1 [5.100s - 7.206s]: 我現在依然清楚地記得
  Track 2 [0.000s - 2.880s]: I still remember it clearly.
  Time difference: 5.100s
  Match quality: Good

Option 2:
  Track 1 [8.061s - 10.417s]: 那裡彷彿不屬於這個世界
  Track 2 [2.880s - 5.470s]: It was like something not of this world.
  Time difference: 5.181s
  Match quality: Excellent
```

#### 3. Selection Options
```
Selection Options:
  1-5: Select matching pair number
  0: No good match found (skip global synchronization)
  d: Show detailed view
  q: Quit manual selection

Enter your choice: 2
```

#### 4. Detailed Analysis (Optional)
Press `d` for detailed information:
```
--------------------------------------------------------------------------------
DETAILED ANCHOR OPTIONS
--------------------------------------------------------------------------------

Option 2 Details:
  Track 1:
    Time: 8.061s - 10.417s (2.356s duration)
    Text: 那裡彷彿不屬於這個世界
    Translation: It was like something not of this world.
  Track 2:
    Time: 2.880s - 5.470s (2.590s duration)
    Text: It was like something not of this world.
  Time Analysis:
    Difference: 5.181s
    Required offset: 5.181s (Track 2 will be shifted)
    Match quality: Excellent (semantic match + similar duration)
```

### Selection Best Practices

#### Content Analysis
- **Look for unique phrases** that are unlikely to repeat
- **Avoid generic dialogue** like "Yes", "No", "What?"
- **Prefer longer sentences** with specific content
- **Consider context** and scene information

#### Timing Analysis
- **Consistent offset** across options suggests good alignment
- **Large variations** may indicate complex timing issues
- **Very small differences** (<1s) often indicate good sync
- **Very large differences** (>10s) may indicate wrong tracks

#### Quality Indicators
- **Excellent** (≤0.5s): Tracks are well synchronized
- **Good** (≤1.0s): Minor timing adjustment needed
- **Fair** (≤2.0s): Moderate synchronization required
- **Poor** (>2.0s): Significant timing issues present

## Intelligent Track Selection

### Multi-Criteria Scoring System

The system uses a sophisticated scoring algorithm to identify the best subtitle tracks:

**Event Count Analysis (40%)**:
- Main dialogue tracks typically have 300+ events
- Forced English tracks usually have <50 events
- Signs/songs tracks have irregular event patterns

**Title Pattern Matching (35%)**:
- Detects keywords like "forced", "foreign parts", "signs & songs"
- Identifies positive indicators like "full", "complete", "dialogue"
- Language-specific pattern recognition

**Content Analysis (25%)**:
- Analyzes subtitle text for dialogue characteristics
- Detects punctuation patterns and sentence structure
- Identifies conversational vs descriptive content

### Enhanced Keyword Detection

**Forced English Detection**:
- "forced", "foreign", "parts only"
- "signs", "songs", "commentary"
- Event count thresholds and content patterns

**Positive Dialogue Indicators**:
- "full", "complete", "dialogue"
- "main", "primary", "standard"
- High event counts with conversational patterns

### Track Selection Examples

**Automatic Selection:**
```bash
biss merge movie.mkv --list-tracks

Track Analysis Results:
Track 0: English (Score: 95.2) - Main dialogue track
  Events: 1,247 | Title: "English" | Dialogue patterns detected
Track 1: English (Score: 15.8) - Forced/Signs track
  Events: 23 | Title: "English (Forced)" | Signs patterns detected
Track 2: Chinese (Score: 92.1) - Main dialogue track
  Events: 1,251 | Title: "Chinese Simplified" | Dialogue patterns detected

Recommended: English Track 0, Chinese Track 2
```

**Manual Override:**
```bash
biss merge movie.mkv --english-track 1 --chinese-track 2
```

## Global Track Synchronization

### Reference Track Prioritization

The system automatically prioritizes tracks for timing reference:

1. **Embedded subtitle tracks** over external files (in automatic mode)
2. **Earlier timestamps** when track types are mixed
3. **User-specified reference** with `--reference-language` flag
4. **Highest confidence score** for same-type tracks

### Synchronization Strategies

**Simple Strategy**: Direct first-line comparison
```bash
biss merge movie.mkv --auto-align --sync-strategy first-line
```

**Scan Strategy**: Multi-point analysis
```bash
biss merge movie.mkv --auto-align --sync-strategy scan
```

**Translation Strategy**: Semantic matching
```bash
biss merge movie.mkv --auto-align --sync-strategy translation --use-translation
```

**Manual Strategy**: User-guided selection
```bash
biss merge movie.mkv --auto-align --sync-strategy manual
```

### Mixed Track Type Handling

When processing mixed embedded and external tracks:
1. **Embedded tracks** used as timing reference
2. **External tracks** aligned to embedded timing
3. **Confidence scoring** applied to all combinations
4. **User override** available with manual flags

## Confidence Scoring and Thresholds

### Alignment Confidence Metrics

**Time-Based Confidence**:
- Perfect match (0.0s difference): 1.0
- Good match (≤0.5s difference): 0.8-0.9
- Fair match (≤1.0s difference): 0.6-0.7
- Poor match (>1.0s difference): <0.6

**Content-Based Confidence**:
- Exact text match: 1.0
- High similarity (>90%): 0.9
- Good similarity (70-90%): 0.7-0.8
- Low similarity (<70%): <0.6

**Translation-Assisted Confidence**:
- Semantic match confirmed: +0.1 bonus
- Bidirectional consistency: +0.1 bonus
- Context validation: +0.05 bonus

### Threshold Configuration

**Default Thresholds**:
```bash
--alignment-threshold 0.8      # General alignment confidence
--time-threshold 0.5           # Time matching window (seconds)
--similarity-threshold 0.7     # Text similarity minimum
```

**High-Precision Settings**:
```bash
biss merge movie.mkv --auto-align \
  --alignment-threshold 0.95 \
  --time-threshold 0.3 \
  --similarity-threshold 0.8
```

**Flexible Settings**:
```bash
biss merge movie.mkv --auto-align \
  --alignment-threshold 0.6 \
  --time-threshold 1.0 \
  --similarity-threshold 0.5
```

## Advanced Configuration

### Environment Variables

```bash
# Google Translation API
export GOOGLE_TRANSLATE_API_KEY="your-api-key"

# FFmpeg timeout (seconds)
export FFMPEG_TIMEOUT=1800

# Translation cache directory
export TRANSLATION_CACHE_DIR="/tmp/subtitle-translations"

# Debug logging level
export SUBTITLE_DEBUG_LEVEL="INFO"
```

### Configuration File Support

Create `.subtitle-processor.json` in your home directory:
```json
{
  "alignment": {
    "default_threshold": 0.8,
    "time_threshold": 0.5,
    "similarity_threshold": 0.7
  },
  "translation": {
    "api_key": "your-api-key",
    "cache_enabled": true,
    "max_requests_per_alignment": 10
  },
  "output": {
    "default_format": "srt",
    "backup_enabled": true,
    "naming_convention": "auto"
  },
  "processing": {
    "parallel_enabled": true,
    "max_workers": 4,
    "ffmpeg_timeout": 900
  }
}
```

### Advanced CLI Patterns

**Complex Workflow Example**:
```bash
# High-precision anime processing with all features
biss merge anime.mkv \
  --auto-align \
  --manual-align \
  --use-translation \
  --sync-strategy translation \
  --alignment-threshold 0.95 \
  --time-threshold 0.3 \
  --translation-limit 15 \
  --debug \
  --output "anime.zh-en.srt"
```

**Batch Processing with Fallbacks**:
```bash
# Process with PGS fallback and translation assistance
biss batch-merge "Season 01" \
  --auto-align \
  --use-translation \
  --force-pgs \
  --pgs-language chi_sim \
  --auto-confirm \
  --recursive
```

**Debugging and Analysis**:
```bash
# Comprehensive analysis mode
biss merge movie.mkv \
  --list-tracks \
  --debug \
  --verbose \
  --auto-align \
  --manual-align \
  --sync-strategy manual
```

### Performance Optimization

**Parallel Processing**:
```bash
biss batch-convert /media/subtitles --parallel --max-workers 8
```

**Translation Caching**:
```bash
biss merge movie.mkv --use-translation --translation-cache
```

**Memory Management**:
```bash
# For large files, use streaming mode
biss merge large-movie.mkv --stream-mode --chunk-size 1000
```

### Integration with External Tools

**Plex Integration**:
```bash
# Plex-compatible naming and format
biss batch-merge /media/plex-library \
  --format srt \
  --plex-naming \
  --recursive
```

**Media Server Workflows**:
```bash
# Automated processing for media servers
biss batch-merge /media/incoming \
  --auto-align \
  --auto-confirm \
  --cleanup-backups \
  --older-than 7
```
