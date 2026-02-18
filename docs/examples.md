# Real-World Usage Examples

Practical examples and workflows for common subtitle processing scenarios.

## Table of Contents
- [Anime Processing](#anime-processing)
- [Misaligned Subtitle Processing](#misaligned-subtitle-processing)
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
biss merge "Made in Abyss S02E01.mkv"

# Output: Made in Abyss S02E01.zh-en.srt
```

**Interactive Approach**:
1. Launch: `biss`
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
biss merge "Made in Abyss S02E02.mkv" --auto-align --manual-align --debug
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
biss merge anime.mkv --list-tracks

Track 0: English (Score: 95.2) - Main dialogue track
  Events: 1,247 | Title: "English" | Dialogue patterns
Track 1: English (Score: 15.8) - Forced/Signs track
  Events: 23 | Title: "English (Forced)" | Signs patterns
Track 2: Japanese (Score: 88.5) - Main dialogue track
  Events: 1,251 | Title: "Japanese"
```

**Automatic Selection**: System correctly chooses Track 0 for English
**Manual Override**: `biss merge anime.mkv --english-track 0`

## Misaligned Subtitle Processing

### Scenario 1: Made in Abyss Season 02 - Individual Episode Processing

**Setup**: Anime episodes with embedded English subtitles and misaligned external Chinese subtitles

**File Structure**:
```
Season 02/
├── Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].mkv
├── Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt
├── Made in Abyss S02E02-Capital of the Unreturned [1080p Dual Audio BD Remux FLAC-TTGA].mkv
└── Made in Abyss S02E02-Capital of the Unreturned [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt
```

**Problem**: Chinese subtitles are significantly misaligned (several seconds off) compared to embedded English subtitles

**Single Episode Processing**:
```bash
biss merge "Season 02/Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].mkv" \
  --auto-align \
  --use-translation \
  --sync-strategy translation \
  --reference-language english \
  --alignment-threshold 0.8
```

**Process Explanation**:
1. **Extract embedded English subtitles** from .mkv file (immutable timing reference)
2. **Load external Chinese subtitles** from .zh.srt file
3. **Auto-detect alignment anchor point** using content similarity with translation API
4. **Calculate global time offset** needed to align Chinese to English timing
5. **Apply global time shift** to ALL Chinese subtitle timestamps
6. **Merge with anti-jitter logic** to prevent subtitle flickering
7. **Output bilingual file** with exact video filename + `.zh-en.srt`

**Expected Output**:
```
Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh-en.srt
```

**Key Features Demonstrated**:
- ✅ Embedded English subtitles preserved as timing reference
- ✅ Translation-assisted content similarity matching
- ✅ Global time offset calculation and application
- ✅ Complete video filename preservation
- ✅ Automatic Plex-compatible naming (`.zh-en.srt`)

### Scenario 2: Made in Abyss Season 02 - Batch Processing

**Setup**: Process multiple episodes with misaligned subtitles automatically

**Batch Processing Command**:
```bash
biss batch-merge "Season 02" \
  --auto-align \
  --use-translation \
  --sync-strategy translation \
  --reference-language english \
  --alignment-threshold 0.8 \
  --auto-confirm
```

**Batch Process Output**:
```
================================================================================
BATCH PROCESSING: FILE 3/4
================================================================================
Current file: Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].mkv

Analyzing video file...
Detected subtitle tracks:
  - Track 3: eng (ass) - Signs & Songs
  - Track 4: eng (ass) - Dialogue
  - Track 5: eng (ass) - Honorific
External subtitle files:
  - Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh.srt

⚠️ MASSIVE MISALIGNMENT DETECTED: Using enhanced alignment (timing will be modified)
⚠️ This should only be used for external files with major timing issues
✅ Successfully processed: Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].mkv
```

**Final Results**:
```
Season 02/
├── Made in Abyss S02E01-The Compass Pointed to the Darkness [1080p Dual Audio BD Remux FLAC-TTGA].zh-en.srt
├── Made in Abyss S02E02-Capital of the Unreturned [1080p Dual Audio BD Remux FLAC-TTGA].zh-en.srt
└── ... (original files preserved)
```

**Batch Processing Benefits**:
- ✅ Processes multiple episodes automatically
- ✅ Consistent alignment strategy across all files
- ✅ No manual intervention required with `--auto-confirm`
- ✅ Detailed progress reporting for each file
- ✅ Preserves exact video filenames for all outputs

### Scenario 3: Advanced Misalignment with Manual Verification

**Setup**: Critical content requiring manual anchor point verification

**Interactive Processing**:
```bash
biss merge "Made in Abyss S02E01.mkv" \
  --auto-align \
  --use-translation \
  --manual-align \
  --sync-strategy translation \
  --alignment-threshold 0.9 \
  --debug
```

**Manual Alignment Interface**:
```
Manual Anchor Point Selection:

Translation-Assisted Alignment Results:
╔══════════════════════════════════════════════════════════════════════════════╗
║                            ANCHOR POINT CANDIDATES                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Option 1: [Confidence: 92.5%]
  Chinese [12.500s]: 我在遇到妳之前
  English  [7.400s]: You know, until I met you,
  Translation: "Before I met you"
  Time difference: +5.100s

Option 2: [Confidence: 89.3%]
  Chinese [25.800s]: 收養了孤苦無依的我的這個男人
  English [20.700s]: The man who took me in when I had no relatives
  Translation: "The man who adopted helpless me"
  Time difference: +5.100s

Option 3: [Confidence: 87.1%]
  Chinese [45.200s]: 據說那是在某個風平浪靜的日子
  English [40.100s]: One calm day,
  Translation: "It is said that it was on a calm day"
  Time difference: +5.100s

Enter your choice (1-3) or 'a' for automatic: 1
```

**Result**: Precise 5.100s offset applied to all Chinese subtitles

### Scenario 4: Bulk Alignment Without Merging

**Setup**: Align Chinese subtitles to English timing without creating bilingual files

**Use Case**: When you want aligned Chinese subtitles but not bilingual format

**Command**:
```bash
biss batch-align "Season 02" \
  --source-pattern "*.zh.srt" \
  --reference-pattern "*.mkv" \
  --auto-align \
  --use-translation \
  --auto-confirm
```

**Process**:
1. Finds all `.zh.srt` files in directory
2. Matches each with corresponding `.mkv` file
3. Extracts embedded English subtitles as reference
4. Aligns Chinese timing to English timing
5. Overwrites original `.zh.srt` files with aligned versions
6. Creates `.bak` backup files automatically

**Output**:
```
Season 02/
├── Made in Abyss S02E01.zh.srt (aligned to embedded English timing)
├── Made in Abyss S02E01.zh.srt.bak (original backup)
├── Made in Abyss S02E02.zh.srt (aligned to embedded English timing)
└── Made in Abyss S02E02.zh.srt.bak (original backup)
```

## Movie Processing

### Scenario 1: Blu-ray Movie with PGS Subtitles

**Setup**: Movie file with only PGS (image-based) subtitles

**File**: `Batman Ninja (2018).mkv`
**Available Tracks**: PGS Chinese, PGS English

**Step 1: Setup PGS Conversion**
```bash
biss setup-pgsrip install
```

**Step 2: Convert and Merge**
```bash
biss merge "Batman Ninja (2018).mkv" --force-pgs --pgs-language chi_sim
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
biss merge "important-movie.mkv" \
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
biss merge --chinese "Movie (2023).zh.srt" --english "Movie (2023).en.srt" \
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
biss batch-merge "Season 01" --auto-align --auto-confirm
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
biss batch-merge "Season 01" --auto-align --manual-align
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
biss batch-merge "Season 01" --chinese-pattern "*.zh.srt" \
  --english-pattern "*.en.srt"

# Japanese-English bilingual
biss batch-merge "Season 01" --chinese-pattern "*.ja.srt" \
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
biss batch-merge Movies/ --chinese-pattern "*chinese.srt"
biss batch-merge Movies/ --chinese-pattern "*.zh.srt"
biss batch-merge Movies/ --chinese-pattern "*_chs.srt"
biss batch-merge Movies/ --prefer-embedded
```

### Scenario 2: Mixed Video Formats

**Setup**: Directory with various video container formats

**Universal Processing**:
```bash
biss batch-merge /media/mixed --pattern "*.mkv *.mp4 *.avi *.m4v" \
  --recursive --auto-align
```

**Format-Specific Processing**:
```bash
# High-quality MKV files with enhanced alignment
biss batch-merge /media/mkv --pattern "*.mkv" --auto-align --manual-align

# Standard MP4 files with basic processing
biss batch-merge /media/mp4 --pattern "*.mp4" --auto-align
```

## Batch Processing Strategies

### Strategy 1: Progressive Quality Levels

**Level 1: Basic Batch Processing**
```bash
biss batch-merge "Content/" --auto-confirm
```

**Level 2: Enhanced Alignment**
```bash
biss batch-merge "Content/" --auto-align --auto-confirm
```

**Level 3: Manual Quality Control**
```bash
biss batch-merge "Content/" --auto-align --manual-align
```

**Level 4: Maximum Precision**
```bash
biss batch-merge "Content/" --auto-align --manual-align \
  --use-translation --alignment-threshold 0.95
```

### Strategy 2: Content-Type Specific Processing

**Anime Content**:
```bash
biss batch-merge "Anime/" --auto-align --manual-align \
  --prefer-external --format srt
```

**Movie Content**:
```bash
biss batch-merge "Movies/" --auto-align --force-pgs \
  --pgs-language chi_sim --use-translation
```

**Documentary Content**:
```bash
biss batch-merge "Documentaries/" --auto-align \
  --alignment-threshold 0.9 --use-translation
```

### Strategy 3: Incremental Processing

**Phase 1: Quick Pass**
```bash
biss batch-merge "Content/" --auto-align --auto-confirm \
  --alignment-threshold 0.9
```

**Phase 2: Manual Review of Failures**
```bash
# Process only files that failed in Phase 1
biss batch-merge "Content/" --auto-align --manual-align \
  --pattern "*_failed.mkv"
```

**Phase 3: Quality Verification**
```bash
# Spot-check random files
biss merge "random-sample.mkv" --auto-align --manual-align \
  --use-translation --debug
```

## Quality Control Workflows

### Workflow 1: Pre-Processing Analysis

**Step 1: Track Analysis**
```bash
biss merge sample.mkv --list-tracks --debug
```

**Step 2: Test Processing**
```bash
biss merge sample.mkv --auto-align --manual-align --debug
```

**Step 3: Batch Application**
```bash
biss batch-merge "Content/" --auto-align --auto-confirm
```

### Workflow 2: Post-Processing Verification

**Step 1: Batch Processing**
```bash
biss batch-merge "Season 01/" --auto-align --auto-confirm
```

**Step 2: Random Sampling**
```bash
# Manually verify random files
biss merge "Season 01/Episode 05.mkv" --auto-align --manual-align
```

**Step 3: Issue Resolution**
```bash
# Re-process problematic files with higher precision
biss merge "problematic-episode.mkv" --auto-align --manual-align \
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
biss batch-merge "/media/incoming" \
  --auto-align \
  --auto-confirm \
  --recursive

# Clean up old backups
biss cleanup-backups "/media" \
  --older-than 7 \
  --recursive

# Generate processing report
biss --verbose batch-merge "/media/processed" \
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
        'biss', 'batch-merge', directory,
        '--auto-align', '--auto-confirm', '--alignment-threshold', '0.9'
    ])

    if result.returncode != 0:
        # Phase 2: Manual intervention for failures
        subprocess.run([
            'biss', 'batch-merge', directory,
            '--auto-align', '--manual-align'
        ])

if __name__ == "__main__":
    process_with_quality_control("/media/new-content")
```

### Script 3: Multi-Language Processing

**PowerShell Script** (`multi-lang.ps1`):
```powershell
# Chinese-English processing
biss batch-merge "Content/" --auto-align --auto-confirm

# Japanese-English processing
biss batch-merge "Content/" --chinese-pattern "*.ja.srt" `
  --output-suffix ".ja-en" --auto-align --auto-confirm

# Korean-English processing
biss batch-merge "Content/" --chinese-pattern "*.ko.srt" `
  --output-suffix ".ko-en" --auto-align --auto-confirm
```
