# Bilingual Subtitle Suite (BISS)

![Bilingual Subtitle Suite Logo](images/biss-logo.png)

A powerful toolkit for creating bilingual subtitles from video files and standalone subtitle files. Supports Chinese-English, Japanese-English, Korean-English and other language combinations with automatic language detection, intelligent track selection, and timing alignment.

## Example Output

![Example Bilingual Subtitle Output](images/biss-fma03.png)
*Bilingual Chinese-English subtitles created by BISS*

## Features

### Bilingual Subtitle Creation
- **Automatic Language Detection**: Identifies languages from filenames and content analysis
- **Smart Track Selection**: Distinguishes main dialogue from forced/signs-only tracks
- **Timing Alignment**: Handles timing differences between tracks automatically
- **Translation-Assisted Matching**: Optional Google Cloud Translation API for semantic alignment
- **Multiple Language Support**: Chinese, Japanese, Korean paired with English

### Processing Capabilities
- **Video Container Support**: Extract embedded subtitles from MKV, MP4, AVI, MOV, WebM, TS
- **Subtitle Formats**: SRT, ASS/SSA, VTT input and output
- **PGS Conversion**: OCR-based conversion of image subtitles (requires setup)
- **Encoding Conversion**: Automatic detection and UTF-8 conversion
- **Timing Adjustment**: Shift subtitles by offset or set specific start times
- **Batch Processing**: Process entire directories with single commands

### User Interfaces
- **Graphical Interface**: Full-featured GUI with drag-and-drop, preview, and visual feedback
- **Command Line**: Scriptable CLI with comprehensive options
- **Interactive Mode**: Menu-driven text interface for guided workflows

## Installation

### Requirements
- Python 3.8 or higher (3.10+ recommended)
- FFmpeg installed and available in PATH
- Git (for cloning)

### Setup
```bash
git clone <repository-url>
cd chsub
pip install -r requirements.txt

# Verify installation
python biss.py --version
```

### Optional: PGS Subtitle Conversion
```bash
python biss.py setup-pgsrip install
```

## Usage

### Graphical Interface (Recommended for Beginners)
```bash
python biss.py gui
# Or simply:
python biss.py
```

The GUI provides:
- Tabbed interface for Merge, Shift, Convert, and Batch operations
- File preview with Ctrl+P
- Automatic language detection labels
- Quick offset buttons for timing adjustment
- Real-time operation logging

### Command Line

**Merge subtitles from two files:**
```bash
python biss.py merge chinese.srt english.srt
```
Languages are detected automatically from filenames (.zh, .chi, .en, .eng, etc.) or content.

**Extract and merge from video:**
```bash
python biss.py merge movie.mkv
```
Extracts embedded Chinese and English tracks and creates bilingual output.

**Shift subtitle timing:**
```bash
# Shift back 2.5 seconds
python biss.py shift subtitle.srt --offset="-2.5s"

# Shift forward 500 milliseconds
python biss.py shift subtitle.srt --offset 500ms

# Set first subtitle to specific timestamp
python biss.py shift subtitle.srt --first-line-at "00:01:23,456"
```

**Convert encoding:**
```bash
python biss.py convert subtitle.srt
```
Automatically detects encoding and converts to UTF-8.

**Preview changes without executing:**
```bash
python biss.py --dry-run merge chinese.srt english.srt
```

**Batch operations:**
```bash
# Merge all videos in directory
python biss.py batch-merge "Season 01" --auto-confirm

# Convert all subtitles to UTF-8
python biss.py batch-convert /path/to/subtitles --recursive
```

### Interactive Mode
```bash
python biss.py interactive
```
Presents a menu-driven interface for all operations.

## Advanced Options

### Alignment for Timing Mismatches
When subtitle tracks have different timing:
```bash
python biss.py merge movie.mkv --auto-align
```

For large timing offsets (50+ seconds):
```bash
python biss.py merge movie.mkv --auto-align --alignment-threshold 0.3
```

With translation assistance for better cross-language matching:
```bash
python biss.py merge movie.mkv --auto-align --use-translation
```

### Track Selection
```bash
# List available tracks
python biss.py merge movie.mkv --list-tracks

# Force specific track IDs
python biss.py merge movie.mkv --chinese-track 3 --english-track 5

# Prefer external files over embedded
python biss.py merge movie.mkv --prefer-external
```

### Output Control
```bash
# Specify output path
python biss.py merge file1.srt file2.srt -o output.srt

# Choose output format
python biss.py merge file1.srt file2.srt --format ass
```

## Project Structure

```
biss/
├── biss.py                 # Main entry point
├── core/                   # Core processing modules
│   ├── subtitle_formats.py # SRT, ASS, VTT parsing
│   ├── video_containers.py # FFmpeg integration
│   ├── language_detection.py
│   ├── encoding_detection.py
│   └── translation_service.py
├── processors/             # High-level operations
│   ├── merger.py           # Bilingual merging
│   ├── converter.py        # Encoding conversion
│   ├── timing_adjuster.py  # Timing adjustment
│   ├── realigner.py        # Subtitle alignment
│   └── batch_processor.py  # Batch operations
├── ui/                     # User interfaces
│   ├── gui.py              # Tkinter GUI
│   ├── cli.py              # Command-line interface
│   └── interactive.py      # Interactive text mode
├── utils/                  # Utilities
│   ├── backup_manager.py   # Backup handling
│   ├── file_operations.py
│   └── logging_config.py
└── third_party/            # External integrations
    └── pgsrip_wrapper.py   # PGS conversion
```

## Supported Formats

| Type | Formats |
|------|---------|
| Video | MKV, MP4, AVI, M4V, MOV, WebM, TS, MPG, MPEG |
| Subtitles | SRT, ASS, SSA, VTT |
| Encodings | UTF-8, UTF-16, GB18030, GBK, Big5, Shift-JIS, and more |
| Languages | Chinese (Simplified/Traditional), English, Japanese, Korean |

## Configuration

### Environment Variables
```bash
# Google Translation API key (optional, for --use-translation)
export GOOGLE_TRANSLATE_API_KEY="your-api-key"

# FFmpeg timeout in seconds (default: 900)
export FFMPEG_TIMEOUT=1800
```

### Backup Management
Backups are created automatically when modifying files in-place. The backup manager keeps the 5 most recent backups per file by default.

```bash
# Clean up old backups
python biss.py cleanup-backups /path/to/directory --older-than 30
```

## Troubleshooting

### Common Issues

**FFmpeg not found:**
Install FFmpeg and ensure it's in your system PATH. Test with `ffmpeg -version`.

**Encoding detection fails:**
```bash
pip install charset-normalizer
```

**Garbled characters in output:**
The source file may have incorrect encoding. Try:
```bash
python biss.py convert subtitle.srt --force
```

**Timing mismatch after merge:**
Use alignment options:
```bash
python biss.py merge file1.srt file2.srt --auto-align
```

### Debug Mode
For detailed logging:
```bash
python biss.py --debug merge movie.mkv
```

## Acknowledgments

This project integrates several excellent open-source tools:

- **[PGSRip](https://github.com/ratoaq2/pgsrip)** by ratoaq2 - PGS subtitle extraction (Apache 2.0)
- **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)** - Optical character recognition (Apache 2.0)
- **[FFmpeg](https://ffmpeg.org/)** - Video/audio processing (LGPL/GPL)
