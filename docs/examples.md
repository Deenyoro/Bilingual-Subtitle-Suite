# Real-World Usage Examples

Practical examples and workflows for common subtitle processing scenarios.

## Table of Contents
- [Anime Processing](#anime-processing)
- [Movie Processing](#movie-processing)
- [TV Series Workflows](#tv-series-workflows)
- [Mixed Content Scenarios](#mixed-content-scenarios)
- [Batch Processing Strategies](#batch-processing-strategies)
- [Quality Control Workflows](#quality-control-workflows)
- [Automation Scripts](#automation-scripts)

## Anime Processing

### Scenario 1: Standard Anime Episode

**Setup**: Anime episode with embedded English subtitles and external Chinese .zh.srt file

**File Structure**:
```
Made in Abyss S02E01.mkv
Made in Abyss S02E01.zh.srt
```

**CLI Approach**:
```bash
# Basic processing with auto-detection
python biss.py merge "Made in Abyss S02E01.mkv"

# Output: Made in Abyss S02E01.zh-en.srt
```

**Interactive Approach**:
1. Launch: `python biss.py`
2. Select: "1. Merge Bilingual Subtitles"
3. Choose: "2. Extract and merge from video file"
4. Enter video path
5. System auto-detects external Chinese file
6. Enable enhanced alignment: Yes
7. Result: Bilingual subtitle file created

**Expected Results**:
- Automatic language detection
- Intelligent track selection (main English dialogue)
- External Chinese file integration
- Optimized timing for bilingual display

### Scenario 2: Complex Timing Issues

**Setup**: Anime with significant timing offset between tracks

**Problem**: Chinese subtitles are 5+ seconds ahead of English

**Solution with Manual Alignment**:
```bash
python biss.py merge "Made in Abyss S02E02.mkv" --auto-align --manual-align --debug
```

**Manual Alignment Process**:
```
Manual Anchor Point Selection:

Option 1:
  Track 1 [5.100s]: 我現在依然清楚地記得
  Track 2 [0.000s]: I still remember it clearly.
  Time difference: 5.100s

Option 2:
  Track 1 [8.061s]: 那裡彷彿不屬於這個世界  
  Track 2 [2.880s]: It was like something not of this world.
  Time difference: 5.181s

Enter your choice: 2
```

**Result**: Perfect synchronization with 5.181s offset applied

### Scenario 3: Forced English Subtitles

**Setup**: Anime with multiple English tracks (main dialogue + forced/signs)

**Track Analysis**:
```bash
python biss.py merge anime.mkv --list-tracks

Track 0: English (Score: 95.2) - Main dialogue track
  Events: 1,247 | Title: "English" | Dialogue patterns
Track 1: English (Score: 15.8) - Forced/Signs track
  Events: 23 | Title: "English (Forced)" | Signs patterns
Track 2: Japanese (Score: 88.5) - Main dialogue track
  Events: 1,251 | Title: "Japanese"
```

**Automatic Selection**: System correctly chooses Track 0 for English
**Manual Override**: `python biss.py merge anime.mkv --english-track 0`

## Movie Processing

### Scenario 1: Blu-ray Movie with PGS Subtitles

**Setup**: Movie file with only PGS (image-based) subtitles

**File**: `Batman Ninja (2018).mkv`
**Available Tracks**: PGS Chinese, PGS English

**Step 1: Setup PGS Conversion**
```bash
python biss.py setup-pgsrip install
```

**Step 2: Convert and Merge**
```bash
python biss.py merge "Batman Ninja (2018).mkv" --force-pgs --pgs-language chi_sim
```

**Process**:
1. System detects no text-based subtitles
2. Automatically extracts PGS tracks
3. Converts Chinese PGS to SRT using OCR
4. Converts English PGS to SRT using OCR
5. Merges both into bilingual file

**Output**: `Batman Ninja (2018).zh-en.srt`

### Scenario 2: High-Precision Movie Processing

**Setup**: Critical content requiring maximum accuracy

**Command**:
```bash
python biss.py merge "important-movie.mkv" \
  --auto-align \
  --manual-align \
  --use-translation \
  --sync-strategy translation \
  --alignment-threshold 0.95 \
  --debug
```

**Features Used**:
- Enhanced alignment system
- Manual anchor point selection
- Translation-assisted semantic matching
- High confidence threshold (95%)
- Detailed debug logging

**Use Cases**:
- Educational content
- Professional presentations
- Archival material
- Quality control verification

### Scenario 3: Movie with External Subtitle Files

**Setup**: Movie with separate Chinese and English subtitle files

**File Structure**:
```
Movie (2023).mkv
Movie (2023).zh.srt
Movie (2023).en.srt
```

**CLI Processing**:
```bash
python biss.py merge --chinese "Movie (2023).zh.srt" --english "Movie (2023).en.srt" \
  --output "Movie (2023).bilingual.srt" --auto-align
```

**Interactive Processing**:
1. Select: "1. Merge Bilingual Subtitles" → "1. Merge two subtitle files"
2. Enter Chinese file path
3. Enter English file path
4. Enable enhanced alignment
5. Specify output path

## TV Series Workflows

### Scenario 1: Complete Season Processing

**Setup**: TV series season with consistent subtitle structure

**Directory Structure**:
```
Season 01/
├── Episode 01.mkv
├── Episode 01.zh.srt
├── Episode 02.mkv
├── Episode 02.zh.srt
└── ... (more episodes)
```

**Batch Processing**:
```bash
python biss.py batch-merge "Season 01" --auto-align --auto-confirm
```

**Process**:
1. Scans directory for video files
2. Auto-detects external Chinese subtitles
3. Extracts embedded English subtitles
4. Applies enhanced alignment to all files
5. Creates bilingual files for entire season

**Output**:
```
Season 01/
├── Episode 01.zh-en.srt
├── Episode 02.zh-en.srt
└── ... (bilingual subtitles)
```

### Scenario 2: Mixed Quality Episodes

**Setup**: Some episodes have good timing, others need manual adjustment

**Strategy**: Batch processing with manual intervention
```bash
python biss.py batch-merge "Season 01" --auto-align --manual-align
```

**Process**:
- Episodes with good alignment: Automatic processing
- Episodes with timing issues: Manual alignment interface appears
- User selects anchor points for problematic episodes
- Batch continues after manual intervention

### Scenario 3: Multi-Language Series

**Setup**: Series with Chinese, English, and Japanese subtitles

**Selective Processing**:
```bash
# Chinese-English bilingual
python biss.py batch-merge "Season 01" --chinese-pattern "*.zh.srt" \
  --english-pattern "*.en.srt"

# Japanese-English bilingual
python biss.py batch-merge "Season 01" --chinese-pattern "*.ja.srt" \
  --english-pattern "*.en.srt" --output-suffix ".ja-en"
```

## Mixed Content Scenarios

### Scenario 1: Inconsistent File Naming

**Setup**: Files with various naming conventions

**File Structure**:
```
Movies/
├── Movie1.mkv + Movie1.chinese.srt
├── Movie2.mkv + Movie2.zh.srt  
├── Movie3.mkv + Movie3_chs.srt
└── Movie4.mkv (embedded only)
```

**Flexible Processing**:
```bash
# Process each type separately
python biss.py batch-merge Movies/ --chinese-pattern "*chinese.srt"
python biss.py batch-merge Movies/ --chinese-pattern "*.zh.srt"
python biss.py batch-merge Movies/ --chinese-pattern "*_chs.srt"
python biss.py batch-merge Movies/ --prefer-embedded
```

### Scenario 2: Mixed Video Formats

**Setup**: Directory with various video container formats

**Universal Processing**:
```bash
python biss.py batch-merge /media/mixed --pattern "*.mkv *.mp4 *.avi *.m4v" \
  --recursive --auto-align
```

**Format-Specific Processing**:
```bash
# High-quality MKV files with enhanced alignment
python biss.py batch-merge /media/mkv --pattern "*.mkv" --auto-align --manual-align

# Standard MP4 files with basic processing
python biss.py batch-merge /media/mp4 --pattern "*.mp4" --auto-align
```

## Batch Processing Strategies

### Strategy 1: Progressive Quality Levels

**Level 1: Basic Batch Processing**
```bash
python biss.py batch-merge "Content/" --auto-confirm
```

**Level 2: Enhanced Alignment**
```bash
python biss.py batch-merge "Content/" --auto-align --auto-confirm
```

**Level 3: Manual Quality Control**
```bash
python biss.py batch-merge "Content/" --auto-align --manual-align
```

**Level 4: Maximum Precision**
```bash
python biss.py batch-merge "Content/" --auto-align --manual-align \
  --use-translation --alignment-threshold 0.95
```

### Strategy 2: Content-Type Specific Processing

**Anime Content**:
```bash
python biss.py batch-merge "Anime/" --auto-align --manual-align \
  --prefer-external --format srt
```

**Movie Content**:
```bash
python biss.py batch-merge "Movies/" --auto-align --force-pgs \
  --pgs-language chi_sim --use-translation
```

**Documentary Content**:
```bash
python biss.py batch-merge "Documentaries/" --auto-align \
  --alignment-threshold 0.9 --use-translation
```

### Strategy 3: Incremental Processing

**Phase 1: Quick Pass**
```bash
python biss.py batch-merge "Content/" --auto-align --auto-confirm \
  --alignment-threshold 0.9
```

**Phase 2: Manual Review of Failures**
```bash
# Process only files that failed in Phase 1
python biss.py batch-merge "Content/" --auto-align --manual-align \
  --pattern "*_failed.mkv"
```

**Phase 3: Quality Verification**
```bash
# Spot-check random files
python biss.py merge "random-sample.mkv" --auto-align --manual-align \
  --use-translation --debug
```

## Quality Control Workflows

### Workflow 1: Pre-Processing Analysis

**Step 1: Track Analysis**
```bash
python biss.py merge sample.mkv --list-tracks --debug
```

**Step 2: Test Processing**
```bash
python biss.py merge sample.mkv --auto-align --manual-align --debug
```

**Step 3: Batch Application**
```bash
python biss.py batch-merge "Content/" --auto-align --auto-confirm
```

### Workflow 2: Post-Processing Verification

**Step 1: Batch Processing**
```bash
python biss.py batch-merge "Season 01/" --auto-align --auto-confirm
```

**Step 2: Random Sampling**
```bash
# Manually verify random files
python biss.py merge "Season 01/Episode 05.mkv" --auto-align --manual-align
```

**Step 3: Issue Resolution**
```bash
# Re-process problematic files with higher precision
python biss.py merge "problematic-episode.mkv" --auto-align --manual-align \
  --use-translation --alignment-threshold 0.95
```

## Automation Scripts

### Script 1: Daily Processing Pipeline

**Bash Script** (`process-daily.sh`):
```bash
#!/bin/bash

# Set environment variables
export GOOGLE_TRANSLATE_API_KEY="your-api-key"

# Process new content
python biss.py batch-merge "/media/incoming" \
  --auto-align \
  --auto-confirm \
  --recursive

# Clean up old backups
python biss.py cleanup-backups "/media" \
  --older-than 7 \
  --recursive

# Generate processing report
python biss.py --verbose batch-merge "/media/processed" \
  --list-only > daily-report.txt
```

### Script 2: Quality Control Pipeline

**Python Script** (`quality-control.py`):
```python
#!/usr/bin/env python3
import subprocess
import os

def process_with_quality_control(directory):
    # Phase 1: Automatic processing
    result = subprocess.run([
        'python', 'biss.py', 'batch-merge', directory,
        '--auto-align', '--auto-confirm', '--alignment-threshold', '0.9'
    ])

    if result.returncode != 0:
        # Phase 2: Manual intervention for failures
        subprocess.run([
            'python', 'biss.py', 'batch-merge', directory,
            '--auto-align', '--manual-align'
        ])

if __name__ == "__main__":
    process_with_quality_control("/media/new-content")
```

### Script 3: Multi-Language Processing

**PowerShell Script** (`multi-lang.ps1`):
```powershell
# Chinese-English processing
python biss.py batch-merge "Content/" --auto-align --auto-confirm

# Japanese-English processing
python biss.py batch-merge "Content/" --chinese-pattern "*.ja.srt" `
  --output-suffix ".ja-en" --auto-align --auto-confirm

# Korean-English processing
python biss.py batch-merge "Content/" --chinese-pattern "*.ko.srt" `
  --output-suffix ".ko-en" --auto-align --auto-confirm
```
