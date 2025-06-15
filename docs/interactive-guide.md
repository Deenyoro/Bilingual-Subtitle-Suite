# Interactive Mode Guide

Complete guide to using the Bilingual Subtitle Suite's interactive menu-driven interface.

## Table of Contents
- [Getting Started](#getting-started)
- [Main Menu Overview](#main-menu-overview)
- [Bilingual Subtitle Merging](#bilingual-subtitle-merging)
- [Encoding Conversion](#encoding-conversion)
- [Subtitle Realignment](#subtitle-realignment)
- [Batch Operations](#batch-operations)
- [Video Processing](#video-processing)
- [PGS Conversion](#pgs-conversion)
- [Tips and Best Practices](#tips-and-best-practices)

## Getting Started

### Launching Interactive Mode
```bash
# Default launch (interactive mode)
python biss.py

# Explicit interactive mode
python biss.py interactive

# Interactive mode without colors
python biss.py --no-colors interactive
```

### Navigation
- **Enter numbers** to select menu options
- **Press Enter** to continue after operations
- **Ctrl+C** to cancel current operation and return to menu
- **Enter 0 or 'q'** to exit from any menu

## Main Menu Overview

When you launch interactive mode, you'll see the main menu:

```
================================================================================
Bilingual Subtitle Suite v2.0.0
================================================================================

Main Menu:
1. Merge Bilingual Subtitles
2. Convert Subtitle Encoding
3. Realign Subtitle Timing
4. Batch Operations
5. Video Processing
6. PGS Subtitle Conversion
7. Help & Information
0. Exit

Enter your choice (0-7):
```

### Menu Options Explained

1. **Merge Bilingual Subtitles** - Create Chinese-English bilingual subtitle files
2. **Convert Subtitle Encoding** - Convert subtitle files to UTF-8 encoding
3. **Realign Subtitle Timing** - Fix timing issues between subtitle tracks
4. **Batch Operations** - Process multiple files at once
5. **Video Processing** - Extract and analyze subtitle tracks from videos
6. **PGS Subtitle Conversion** - Convert image-based PGS subtitles to text
7. **Help & Information** - System information and usage help

## Bilingual Subtitle Merging

### Submenu Options
```
==================================================
BILINGUAL SUBTITLE MERGING
==================================================

Choose input method:
1. Merge two subtitle files
2. Extract and merge from video file
0. Back to main menu
```

### Option 1: Merge Two Subtitle Files

**Step-by-step workflow:**

1. **Select Chinese subtitle file** (optional)
   ```
   Enter path to Chinese subtitle file (optional):
   > /path/to/chinese.zh.srt
   ```

2. **Select English subtitle file** (optional)
   ```
   Enter path to English subtitle file (optional):
   > /path/to/english.en.srt
   ```

3. **Enhanced alignment options**
   ```
   Enable enhanced alignment? (y/n): y
   Enable manual anchor selection? (y/n): n
   Use translation service for alignment? (y/n): n
   Alignment confidence threshold (0.0-1.0) [0.8]: 0.9
   ```

4. **Output configuration**
   ```
   Enter output file path [auto-generated]: custom-output.srt
   Select output format:
   1. SRT (SubRip)
   2. ASS (Advanced SubStation Alpha)
   3. VTT (WebVTT)
   Enter choice (1-3) [1]: 1
   ```

5. **Processing and results**
   ```
   Merging subtitles...
   ✓ Successfully created: custom-output.srt
   ```

### Option 2: Extract and Merge from Video File

**Step-by-step workflow:**

1. **Select video file**
   ```
   Enter path to video file:
   > /path/to/movie.mkv
   ```

2. **Optional external subtitle files**
   ```
   Optional external subtitle files:
   Enter path to Chinese subtitle file (optional):
   > /path/to/external.zh.srt
   
   Enter path to English subtitle file (optional):
   > [Enter for none]
   ```

3. **Processing options**
   ```
   Processing options:
   Prefer external subtitles over embedded? (y/n): n
   ```

4. **Enhanced alignment configuration**
   ```
   Enhanced Alignment Options:
   Enable enhanced alignment? (y/n): y
   Enable manual anchor selection? (y/n): y
   Use translation service? (y/n): n
   Alignment confidence threshold [0.8]: 0.9
   ```

5. **Output format selection**
   ```
   Select output format:
   1. SRT (SubRip)
   2. ASS (Advanced SubStation Alpha)
   3. VTT (WebVTT)
   Enter choice (1-3) [1]: 1
   ```

### Enhanced Alignment Options Explained

- **Enhanced alignment**: Enables two-phase alignment system with global sync and detailed matching
- **Manual anchor selection**: Interactive interface for precise timing control
- **Translation service**: Uses Google Translate API for semantic matching
- **Confidence threshold**: Minimum confidence for automatic alignment (0.0-1.0)

## Encoding Conversion

### Submenu Options
```
==================================================
SUBTITLE ENCODING CONVERSION
==================================================

Choose operation:
1. Convert single file
2. Convert directory
0. Back to main menu
```

### Single File Conversion

**Workflow:**
1. **Select file**
   ```
   Enter path to subtitle file to convert:
   > /path/to/chinese_subtitle.srt
   ```

2. **Conversion options**
   ```
   Target encoding (default: utf-8): utf-8
   Create backup of original file? (y/n): y
   Force conversion even if already target encoding? (y/n): n
   ```

3. **Processing**
   ```
   Converting: chinese_subtitle.srt
   ✓ File converted successfully
   ```

### Directory Conversion

**Workflow:**
1. **Select directory**
   ```
   Enter path to directory to process:
   > /media/chinese-subtitles
   ```

2. **Processing options**
   ```
   Process subdirectories recursively? (y/n): y
   Target encoding (default: utf-8): utf-8
   Create backup files? (y/n): y
   Force conversion? (y/n): n
   Use parallel processing? (y/n): y
   ```

3. **Processing results**
   ```
   Processing directory: /media/chinese-subtitles
   Found 15 subtitle files
   
   Processing files...
   ✓ Converted: movie1.srt
   ✓ Converted: movie2.srt
   - Skipped: movie3.srt (already UTF-8)
   
   Conversion complete: 12 converted, 3 skipped
   ```

## Subtitle Realignment

### Submenu Options
```
==================================================
SUBTITLE REALIGNMENT
==================================================

Choose operation:
1. Realign single pair
2. Batch realign directory
3. Interactive alignment
4. Auto-align using similarity analysis
5. Translation-assisted alignment
0. Back to main menu
```

### Single Pair Realignment

**Workflow:**
1. **Select files**
   ```
   Enter path to source subtitle file:
   > /path/to/source.srt
   
   Enter path to reference subtitle file:
   > /path/to/reference.srt
   ```

2. **Alignment points**
   ```
   Source alignment point index [auto-detect]: 5
   Reference alignment point index [auto-detect]: 3
   ```

3. **Backup option**
   ```
   Create backup before overwriting? (y/n) [y]: y
   ```

### Interactive Alignment

**Advanced alignment with user control:**
1. **File selection** (same as above)
2. **Interactive anchor selection**
   ```
   ================================================================================
   MANUAL ANCHOR POINT SELECTION
   ================================================================================
   
   Option 1:
     Track 1 [5.100s - 7.206s]: 我現在依然清楚地記得
     Track 2 [0.000s - 2.880s]: I still remember it clearly.
     Time difference: 5.100s
   
   Option 2:
     Track 1 [8.061s - 10.417s]: 那裡彷彿不屬於這個世界
     Track 2 [2.880s - 5.470s]: It was like something not of this world.
     Time difference: 5.181s
   
   Selection Options:
     1-5: Select matching pair number
     0: No good match found
     d: Show detailed view
     q: Quit manual selection
   
   Enter your choice: 2
   ```

3. **Confirmation and processing**
   ```
   Selected anchor pair 2:
     Track 1 [8.061s]: 那裡彷彿不屬於這個世界
     Track 2 [2.880s]: It was like something not of this world.
     This will apply a 5.181s offset to Track 2
   Confirm this selection? (y/n): y
   
   ✓ Subtitles realigned successfully
   ```

## Batch Operations

### Submenu Options
```
==================================================
BATCH OPERATIONS
==================================================

Choose operation:
1. Batch convert encodings
2. Batch merge from videos
3. Batch realign subtitles
4. Bulk subtitle alignment (non-combined)
0. Back to main menu
```

### Batch Merge from Videos

**Workflow:**
1. **Select directory**
   ```
   Enter path to directory containing video files:
   > /media/anime/Season 01
   ```

2. **Processing options**
   ```
   Process subdirectories recursively? (y/n): n
   File pattern [*.mkv *.mp4 *.avi]: *.mkv
   Prefer external subtitle files? (y/n): n
   ```

3. **Enhanced alignment options**
   ```
   Enhanced Alignment Options:
   Enable enhanced alignment for all files? (y/n): y
   Enable manual alignment when needed? (y/n): y
   Use translation service? (y/n): n
   Confidence threshold [0.8]: 0.8
   ```

4. **Confirmation and processing**
   ```
   Found 12 video files to process:
   - Made in Abyss S01E01.mkv
   - Made in Abyss S01E02.mkv
   [... more files ...]

   Proceed with batch processing? (y/n): y

   Processing files...
   [1/12] Made in Abyss S01E01.mkv
   ✓ Created: Made in Abyss S01E01.zh-en.srt

   [2/12] Made in Abyss S01E02.mkv
   ⚠ Manual alignment required
   [Manual alignment interface appears...]
   ✓ Created: Made in Abyss S01E02.zh-en.srt

   Batch processing complete: 12 processed, 12 successful
   ```

### Batch Realign Subtitles

**Workflow:**
1. **Select directory and patterns**
   ```
   Enter path to directory:
   > /media/subtitles

   Source file extension (e.g., .zh.srt): .zh.srt
   Reference file extension (e.g., .en.srt): .en.srt
   Output suffix [.aligned]: .synced
   Process subdirectories recursively? (y/n): y
   ```

2. **Processing**
   ```
   Found 8 subtitle pairs to realign:
   - movie1.zh.srt + movie1.en.srt
   - movie2.zh.srt + movie2.en.srt
   [... more pairs ...]

   Processing pairs...
   ✓ Realigned: movie1.zh.synced.srt
   ✓ Realigned: movie2.zh.synced.srt

   Batch realignment complete: 8 processed, 8 successful
   ```

## Video Processing

### Submenu Options
```
==================================================
VIDEO PROCESSING
==================================================

Choose operation:
1. Process single video
2. Batch process videos
3. List video subtitle tracks
0. Back to main menu
```

### List Video Subtitle Tracks

**Workflow:**
1. **Select video file**
   ```
   Enter path to video file:
   > /path/to/movie.mkv
   ```

2. **Track analysis results**
   ```
   ================================================================================
   SUBTITLE TRACK ANALYSIS: movie.mkv
   ================================================================================

   Track 0: English (Subtitle)
     Language: eng
     Title: English
     Codec: subrip
     Events: 1,247
     Score: 95.2 (Main dialogue track)
     Reasoning: High event count, clear title, dialogue patterns

   Track 1: English (Subtitle)
     Language: eng
     Title: English (Forced)
     Codec: subrip
     Events: 23
     Score: 15.8 (Forced/Signs track)
     Reasoning: Low event count, "forced" keyword, signs patterns

   Track 2: Chinese (Subtitle)
     Language: chi
     Title: Chinese Simplified
     Codec: subrip
     Events: 1,251
     Score: 92.1 (Main dialogue track)
     Reasoning: High event count, matches dialogue patterns

   Recommended selection:
   - English: Track 0 (Main dialogue)
   - Chinese: Track 2 (Main dialogue)
   ```

## PGS Conversion

### Submenu Options
```
==================================================
PGS SUBTITLE CONVERSION
==================================================

Choose operation:
1. Convert PGS from single video
2. Batch convert PGS from multiple videos
3. List PGS tracks in video
4. Check PGSRip installation
0. Back to main menu
```

### Check PGSRip Installation

**Installation status check:**
```
PGSRip Installation Status:
✓ PGSRip: Installed (v1.0.2)
✓ Tesseract OCR: Installed (v5.3.0)
✓ MKVToolNix: Installed (v70.0.0)
✓ Language Data: English, Chinese Simplified, Chinese Traditional

Installation directory: third_party/pgsrip_install/
All components ready for PGS conversion.
```

### Convert PGS from Single Video

**Workflow:**
1. **Select video and options**
   ```
   Enter path to video file:
   > /path/to/movie.mkv

   Available PGS tracks:
   Track 3: PGS (Chinese)
   Track 4: PGS (English)

   Select track index: 3
   OCR language (eng, chi_sim, chi_tra) [chi_sim]: chi_sim
   ```

2. **Processing**
   ```
   Converting PGS track 3 to SRT...
   Extracting PGS subtitles...
   Running OCR with Chinese Simplified...
   ✓ Conversion complete: movie.chi_sim.srt
   ```

## Tips and Best Practices

### File Path Input
- **Drag and drop**: Most terminals support dragging files to auto-fill paths
- **Tab completion**: Use Tab key for path auto-completion
- **Quotes**: Use quotes for paths with spaces: `"/path/with spaces/file.mkv"`
- **Relative paths**: Use `./` for current directory, `../` for parent directory

### Enhanced Alignment Best Practices
- **Start with auto-align**: Enable enhanced alignment for better results
- **Use manual alignment**: For complex timing issues or critical content
- **Translation service**: Helpful for cross-language content but requires API key
- **Confidence threshold**: Higher values (0.9+) for precision, lower (0.7) for flexibility

### Batch Processing Tips
- **Test first**: Process a single file before batch operations
- **Use backups**: Always enable backup creation for safety
- **Check patterns**: Verify file patterns match your content
- **Monitor progress**: Watch for manual alignment prompts in batch mode

### Troubleshooting in Interactive Mode
- **File not found**: Check file paths and permissions
- **No tracks found**: Verify video file has subtitle tracks
- **Encoding issues**: Try force conversion for problematic files
- **PGS not available**: Run PGSRip installation check

### Keyboard Shortcuts
- **Ctrl+C**: Cancel current operation (returns to menu)
- **Enter**: Continue/confirm (when prompted)
- **Tab**: Auto-complete file paths (terminal dependent)
- **Up/Down arrows**: Command history (terminal dependent)
