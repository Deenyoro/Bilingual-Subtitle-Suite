# CLI Reference Guide

Complete command-line interface documentation for the Bilingual Subtitle Suite.

## Table of Contents
- [Global Options](#global-options)
- [Main Commands](#main-commands)
- [Merge Command](#merge-command)
- [Convert Command](#convert-command)
- [Realign Command](#realign-command)
- [Batch Commands](#batch-commands)
- [PGS Commands](#pgs-commands)
- [Utility Commands](#utility-commands)

## Global Options

Available for all commands:

```bash
--version                    # Show version information
-v, --verbose               # Enable verbose output
-d, --debug                 # Enable debug logging
--no-colors                 # Disable colored output
```

## Main Commands

### Overview
```bash
python biss.py <command> [options]

# Available commands:
merge                       # Merge bilingual subtitles
convert                     # Convert subtitle encoding
realign                     # Realign subtitle timing
batch-merge                 # Batch merge from videos
batch-convert               # Batch convert encodings
batch-realign               # Batch realign subtitles
batch-align                 # Bulk alignment (non-combined)
convert-pgs                 # Convert PGS subtitles
batch-convert-pgs           # Batch convert PGS
setup-pgsrip               # Setup PGS conversion
cleanup-backups            # Clean backup files
interactive                # Launch interactive mode
```

## Merge Command

Create bilingual subtitle files by combining Chinese and English tracks.

### Basic Syntax
```bash
python biss.py merge <input> [options]
```

### Input Sources
```bash
# From video file (auto-detect embedded subtitles)
python biss.py merge movie.mkv

# From specific subtitle files
python biss.py merge --chinese file.zh.srt --english file.en.srt

# Mixed sources
python biss.py merge movie.mkv --chinese external.zh.srt
```

### Output Options
```bash
--output PATH               # Specify output file path
--format FORMAT             # Output format: srt, ass, vtt (default: srt)
```

### Track Selection
```bash
--chinese-track N           # Select Chinese track by index
--english-track N           # Select English track by index
--list-tracks              # List available tracks and exit
--prefer-external          # Prefer external files over embedded tracks
```

### Enhanced Alignment Options
```bash
--auto-align               # Enable enhanced alignment system
--manual-align             # Enable interactive anchor selection
--alignment-threshold N    # Confidence threshold (0.0-1.0, default: 0.8, use 0.3 for large offsets)
--time-threshold N         # Time matching window in seconds (default: 0.5)
--sync-strategy STRATEGY   # Global sync strategy (see below)
--use-translation         # Enable translation-assisted alignment for cross-language content
--enable-mixed-realignment # Enable enhanced realignment for mixed embedded+external tracks
--translation-api-key KEY # Google Translate API key
```

### Sync Strategies
```bash
--sync-strategy auto        # Automatic strategy selection (default)
--sync-strategy first-line  # Compare first subtitle entries
--sync-strategy scan        # Scan first 10 entries for best match
--sync-strategy translation # Use translation for semantic matching
--sync-strategy manual      # Interactive user selection
```

### PGS Integration
```bash
--force-pgs                # Force PGS conversion even if text subs available
--no-pgs                   # Disable PGS conversion fallback
--pgs-language LANG        # OCR language for PGS conversion
```

### Examples
```bash
# Basic merge with auto-detection
python biss.py merge "Movie (2023).mkv"

# Enhanced alignment with manual control
python biss.py merge movie.mkv --auto-align --manual-align

# Large timing offset handling (50+ second differences)
python biss.py merge movie.mkv --auto-align --use-translation \
  --alignment-threshold 0.3 --enable-mixed-realignment

# Translation-assisted alignment for cross-language content
python biss.py merge movie.mkv --auto-align --use-translation \
  --sync-strategy translation --alignment-threshold 0.9

# Mixed track realignment (embedded + external scenarios)
python biss.py merge movie.mkv --auto-align --enable-mixed-realignment

# Force PGS conversion
python biss.py merge movie.mkv --force-pgs --pgs-language chi_sim

# Specify tracks and output
python biss.py merge movie.mkv --chinese-track 2 --english-track 1 \
  --output "Movie.bilingual.srt" --format srt
```

## Convert Command

Convert subtitle file encodings to UTF-8.

### Basic Syntax
```bash
python biss.py convert <input> [options]
```

### Options
```bash
--encoding ENCODING         # Target encoding (default: utf-8)
--backup                   # Create backup of original file
--force                    # Force conversion even if already target encoding
```

### Examples
```bash
# Convert to UTF-8 with backup
python biss.py convert "chinese_subtitle.srt" --backup

# Force conversion
python biss.py convert subtitle.srt --encoding utf-8 --force
```

## Realign Command

Realign subtitle timing based on reference files.

### Basic Syntax
```bash
python biss.py realign <source> <reference> [options]
```

### Options
```bash
--output PATH              # Output file path
--source-index N           # Source alignment point index
--reference-index N        # Reference alignment point index
--offset SECONDS           # Apply time offset in seconds
--scale FACTOR             # Apply time scaling factor
```

### Examples
```bash
# Basic realignment
python biss.py realign source.srt reference.srt --output aligned.srt

# Specify alignment points
python biss.py realign source.srt reference.srt \
  --source-index 5 --reference-index 3

# Apply time offset
python biss.py realign source.srt --offset 2.5
```

## Batch Commands

Process multiple files efficiently with batch operations.

### Batch Merge
```bash
python biss.py batch-merge <directory> [options]

# Options
--recursive                # Process subdirectories
--pattern PATTERN          # File pattern (default: *.mkv *.mp4 *.avi)
--format FORMAT            # Output format
--prefer-external          # Prefer external subtitle files
--auto-confirm             # Skip confirmation prompts
--auto-align               # Enable enhanced alignment for all files
--manual-align             # Enable manual alignment when needed

# Examples
python biss.py batch-merge "Season 01" --auto-align --auto-confirm
python biss.py batch-merge /media/movies --recursive --prefer-external
```

### Batch Convert
```bash
python biss.py batch-convert <directory> [options]

# Options
--recursive                # Process subdirectories
--encoding ENCODING        # Target encoding (default: utf-8)
--backup                   # Create backup files
--force                    # Force conversion
--parallel                 # Use parallel processing

# Examples
python biss.py batch-convert /media/chinese-subs --backup --parallel
python biss.py batch-convert . --recursive --encoding utf-8 --force
```

### Batch Realign
```bash
python biss.py batch-realign <directory> [options]

# Options
--source-ext EXT           # Source file extension (e.g., .zh.srt)
--reference-ext EXT        # Reference file extension (e.g., .en.srt)
--output-suffix SUFFIX     # Output file suffix (default: .aligned)
--recursive                # Process subdirectories

# Examples
python biss.py batch-realign /media --source-ext .zh.srt --reference-ext .en.srt
python biss.py batch-realign . --recursive --output-suffix .synced
```

### Batch Align (Bulk)
```bash
python biss.py batch-align <directory> [options]

# Options
--reference-language LANG  # Reference language for alignment
--recursive                # Process subdirectories
--auto-confirm             # Skip confirmation prompts

# Examples
python biss.py batch-align /media/subtitles --reference-language en
```

## PGS Commands

Convert PGS (Presentation Graphic Stream) subtitles to text format.

> **Note**: PGS conversion functionality is powered by [PGSRip by ratoaq2](https://github.com/ratoaq2/pgsrip). Install with `python biss.py setup-pgsrip install`.

### Setup PGSRip
```bash
python biss.py setup-pgsrip <action>

# Actions
install                    # Install PGSRip and dependencies
check                      # Check installation status
uninstall                  # Remove PGSRip installation

# Examples
python biss.py setup-pgsrip install
python biss.py setup-pgsrip check
```

### Convert PGS
```bash
python biss.py convert-pgs <input> [options]

# Options
--language LANG            # OCR language (eng, chi_sim, chi_tra)
--output PATH              # Output SRT file path

# Examples
python biss.py convert-pgs movie.mkv --language chi_sim
python biss.py convert-pgs movie.mkv --language eng --output movie.en.srt
```

### Batch Convert PGS
```bash
python biss.py batch-convert-pgs <directory> [options]

# Options
--recursive                # Process subdirectories
--language LANG            # OCR language
--auto-confirm             # Skip confirmation prompts

# Examples
python biss.py batch-convert-pgs /media/movies --language chi_sim --recursive
```

## Utility Commands

### Cleanup Backups
```bash
python biss.py cleanup-backups <directory> [options]

# Options
--older-than DAYS          # Remove backups older than N days
--dry-run                  # Show what would be deleted without deleting
--recursive                # Process subdirectories

# Examples
python biss.py cleanup-backups . --older-than 30
python biss.py cleanup-backups /media --dry-run --recursive
```

### Interactive Mode
```bash
python biss.py interactive

# Launch the interactive menu-driven interface
# All CLI functionality available through guided menus
```

## Advanced Usage Patterns

### Complex Workflows
```bash
# High-precision anime processing
python biss.py merge anime.mkv --auto-align --manual-align \
  --use-translation --alignment-threshold 0.95 --debug

# Large timing offset scenarios (Made in Abyss style)
python biss.py merge "Made in Abyss S02E01.mkv" --auto-align \
  --use-translation --alignment-threshold 0.3 --enable-mixed-realignment

# Batch process with enhanced alignment for large offsets
python biss.py batch-merge "Season 02" --auto-align --use-translation \
  --alignment-threshold 0.3 --auto-confirm

# Batch process with PGS fallback
python biss.py batch-merge "Season 01" --auto-align --force-pgs \
  --pgs-language chi_sim --auto-confirm

# Translation-assisted batch processing
python biss.py batch-merge /media/anime --auto-align --use-translation \
  --sync-strategy translation --recursive
```

### Debugging and Troubleshooting
```bash
# Debug mode with verbose output
python biss.py --debug --verbose merge movie.mkv --auto-align

# List tracks for analysis
python biss.py merge movie.mkv --list-tracks

# Check PGS installation
python biss.py setup-pgsrip check

# Test alignment without creating output
python biss.py merge movie.mkv --auto-align --manual-align --debug
```

### Environment Integration
```bash
# Set API key for translation
export GOOGLE_TRANSLATE_API_KEY="your-api-key"
python biss.py merge movie.mkv --auto-align --use-translation

# Custom FFmpeg timeout
export FFMPEG_TIMEOUT=1800
python biss.py merge large-movie.mkv

# Disable colors for scripting
python biss.py --no-colors batch-merge /media --auto-confirm
```
