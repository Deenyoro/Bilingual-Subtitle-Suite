# Python Chinese Bilingual Subtitle Merger

A powerful Python tool that merges **Chinese** and **English** subtitles into perfectly synchronized bilingual subtitle tracks.

## Key Features

### Core Functionality
- **Multi-Format Support**: Handles SRT, ASS/SSA, and WebVTT subtitle formats with automatic conversion
- **Smart Language Detection**: Uses Unicode character analysis for accurate Chinese/English detection
- **Dual Output Modes**:
  - **SRT**: Merges subtitles with optimized timing to reduce flickering
  - **ASS**: Creates professional dual-style subtitles (Chinese top, English bottom)
- **Automatic Extraction**: Extracts embedded subtitles from video containers using FFmpeg

### Advanced Features
- **Parallel Processing**: Process multiple videos simultaneously with configurable worker threads
- **Intelligent Timing Optimization**: Reduces subtitle flickering by merging adjacent identical subtitles
- **Encoding Auto-Detection**: Automatically detects and handles various text encodings (UTF-8, GBK, Big5, etc.)
- **Progress Tracking**: Real-time progress updates during bulk operations
- **Forced Subtitle Detection**: Automatically identifies and warns about forced/partial subtitle tracks

## Screenshots

| Image                                             | Description                                       |
|---------------------------------------------------|---------------------------------------------------|
| ![Official Combined Subtitles](example/houseofficial.jpg) | An example of official combined subtitles. |
| ![Script Output](example/fma03script.png)                 | An example produced by the script.      |

---

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Command-Line Interface](#command-line-interface)
5. [Usage Examples](#usage-examples)
6. [Operation Modes](#operation-modes)
7. [Advanced Features](#advanced-features)
8. [Format Support](#format-support)
9. [Troubleshooting](#troubleshooting)
10. [Performance Optimization](#performance-optimization)

---

## System Requirements

### Required
- **Python 3.6+** (3.8+ recommended for best performance)
- **FFmpeg** (must be in system PATH)
- **Operating System**: Windows, Linux, macOS

### Optional
- **chardet** library for enhanced encoding detection: `pip install chardet`
- Multi-core CPU for parallel processing benefits

### Verification
```bash
# Check Python version
python --version  # Should show 3.6 or higher

# Check FFmpeg installation
ffmpeg -version  # Should display FFmpeg version info
```

---

## Installation

### Step 1: Download the Script
Download `bilingual_subtitle_merger.py` to your preferred location.

### Step 2: Install FFmpeg

**Windows** (using winget):
```powershell
winget install Gyan.FFmpeg
```

**macOS** (using Homebrew):
```bash
brew install ffmpeg
```

**Linux** (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

### Step 3: (Optional) Install Enhanced Dependencies
```bash
# For better encoding detection
pip install chardet
```

### Step 4: Make Executable (Linux/macOS)
```bash
chmod +x bilingual_subtitle_merger.py
```

---

## Quick Start

### Basic Usage
```bash
# Merge two external subtitle files
python bilingual_subtitle_merger.py -c chinese.srt -e english.srt -o output.srt

# Process a video file (auto-detect subtitles)
python bilingual_subtitle_merger.py -v movie.mkv

# Bulk process an entire directory
python bilingual_subtitle_merger.py --bulk /path/to/movies/
```

---

## Command-Line Interface

### Input Options
| Option | Long Form | Description | Example |
|--------|-----------|-------------|---------|
| `-v` | `--video` | Video file to process | `-v "movie.mkv"` |
| `-c` | `--chinese` | External Chinese subtitle file | `-c "movie.chi.srt"` |
| `-e` | `--english` | External English subtitle file | `-e "movie.eng.srt"` |

### Output Options
| Option | Long Form | Description | Default | Example |
|--------|-----------|-------------|---------|---------|
| `-o` | `--output` | Output file path | `<video>.bilingual.<format>` | `-o "output.srt"` |
| `-f` | `--format` | Output format (srt/ass) | `srt` | `-f ass` |
| | `--force` | Overwrite existing files | False | `--force` |

### Track Selection
| Option | Description | Example |
|--------|-------------|---------|
| `--chi-track` | Specific Chinese subtitle track number | `--chi-track 2` |
| `--eng-track` | Specific English subtitle track number | `--eng-track 3` |
| `--remap-chi` | Treat specified language as Chinese | `--remap-chi jpn` |
| `--remap-eng` | Treat specified language as English | `--remap-eng kor` |

### Processing Options
| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `--bulk` | Process all videos in directory | False | `--bulk` |
| `--prefer-external` | Prefer external over embedded subtitles | False | `--prefer-external` |
| `--prefer-embedded` | Prefer embedded over external subtitles | False | `--prefer-embedded` |
| `--workers` | Number of parallel workers for bulk processing | 4 | `--workers 8` |

### Other Options
| Option | Description |
|--------|-------------|
| `--debug` | Enable detailed debug logging |
| `--version` | Show version information |
| `--help` | Display help message |

---

## Usage Examples

### Example 1: Basic Subtitle Merging
```bash
# Merge external Chinese and English subtitles
python bilingual_subtitle_merger.py \
  -c "Movie.chi.srt" \
  -e "Movie.eng.srt" \
  -o "Movie.bilingual.srt"
```

### Example 2: Extract from Video Container
```bash
# Automatically detect and extract subtitles from MKV
python bilingual_subtitle_merger.py \
  -v "Series.S01E01.mkv" \
  -f ass  # Output as ASS format
```

### Example 3: Bulk Processing with Parallel Workers
```bash
# Process entire season with 8 parallel workers
python bilingual_subtitle_merger.py \
  --bulk "/media/TV Shows/Series/Season 01/" \
  --workers 8 \
  --format ass
```

### Example 4: Language Remapping for Anime
```bash
# Treat Japanese track as Chinese (common for anime)
python bilingual_subtitle_merger.py \
  -v "Anime.Episode.01.mkv" \
  --remap-chi jpn \
  --prefer-embedded
```

### Example 5: Force Specific Tracks
```bash
# Use specific subtitle tracks by ID
python bilingual_subtitle_merger.py \
  -v "Movie.mkv" \
  --chi-track 2 \
  --eng-track 4 \
  --force  # Overwrite existing output
```

### Example 6: WebVTT Input
```bash
# Merge WebVTT subtitles
python bilingual_subtitle_merger.py \
  -c "video.chi.vtt" \
  -e "video.eng.vtt" \
  -f srt  # Convert to SRT
```

---

## Operation Modes

### 1. Direct File Merging
When you provide both `-c` and `-e` without `-v`:
- Directly merges the two subtitle files
- No video analysis or extraction
- Fastest operation mode

### 2. Single Video Processing
When you provide `-v` with a video file:
- First searches for external subtitles (`.en.srt`, `.zh.ass`, etc.)
- If not found, analyzes video for embedded subtitles
- Extracts and merges automatically

### 3. Bulk Processing
When you use `--bulk`:
- Processes all video files in the specified directory
- Uses parallel workers for faster processing
- Shows real-time progress updates
- Generates summary report

### 4. Hybrid Mode
You can mix external and embedded:
- Provide one external subtitle and let the script find the other
- Use `--prefer-external` or `--prefer-embedded` to control priority

---

## Advanced Features

### Parallel Processing
The enhanced version supports multi-threaded bulk processing:
```bash
# Use 8 workers for faster processing
python bilingual_subtitle_merger.py --bulk --workers 8

# System will show progress:
# Processing 24 video files with 8 workers...
# Progress: 12/24 completed
```

### Intelligent Timing Optimization
The script automatically optimizes subtitle timing to reduce flickering:
- Merges adjacent subtitles with identical text
- Extends display duration when appropriate
- Maintains synchronization while improving readability

### Enhanced Language Detection
Uses Unicode character ranges for accurate detection:
- Detects Simplified and Traditional Chinese
- Handles mixed-language subtitles
- Provides warnings for ambiguous content

### Encoding Auto-Detection
Automatically handles various text encodings:
- UTF-8, UTF-16, GBK, GB18030, Big5, Shift-JIS
- Optional `chardet` support for improved accuracy
- Fallback mechanisms for corrupted files

### Format Conversion
Seamlessly converts between formats:
```bash
# Convert WebVTT to bilingual SRT
python bilingual_subtitle_merger.py -c subtitle.vtt -o output.srt

# Convert SRT to styled ASS
python bilingual_subtitle_merger.py -c subtitle.srt -f ass
```

---

## Format Support

### Input Formats
| Format | Extensions | Features |
|--------|------------|----------|
| SubRip | `.srt` | Basic timing and text |
| Advanced SubStation | `.ass`, `.ssa` | Styling, positioning, effects |
| WebVTT | `.vtt` | Web-standard format, cue settings |

### Output Formats

#### SRT Output
- Simple, widely compatible format
- Merged lines appear as:
  ```
  1
  00:00:01,000 --> 00:00:04,000
  你好世界
  Hello World
  ```

#### ASS Output
- Professional styling with separate tracks
- Chinese: Top-aligned, larger font
- English: Bottom-aligned, different color
- Fully customizable styles

### Video Containers
Supports all FFmpeg-compatible containers:
- Matroska: `.mkv`
- MP4: `.mp4`, `.m4v`
- QuickTime: `.mov`
- AVI: `.avi`
- Flash Video: `.flv`
- MPEG-TS: `.ts`
- WebM: `.webm`

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: "No subtitle tracks found"
**Solution**: Verify video has embedded subtitles:
```bash
ffprobe -v quiet -print_format json -show_streams video.mkv | grep -A5 subtitle
```

#### Issue: Encoding/Character Display Problems
**Solutions**:
1. Install `chardet`: `pip install chardet`
2. On Windows, set console to UTF-8: `chcp 65001`
3. Use `--debug` to see detected encoding

#### Issue: Wrong Language Detection
**Solution**: Use language remapping:
```bash
# If Japanese is mislabeled as English
python bilingual_subtitle_merger.py -v anime.mkv --remap-eng jpn
```

#### Issue: Forced Subtitles Warning
**Explanation**: One track has significantly fewer lines (likely forced/signs only)
**Solution**: Use `--eng-track` or `--chi-track` to select different tracks

#### Issue: Performance in Bulk Mode
**Solution**: Adjust worker count based on CPU:
```bash
# For 8-core CPU
python bilingual_subtitle_merger.py --bulk --workers 6
```

### Debug Mode
Enable comprehensive logging for troubleshooting:
```bash
python bilingual_subtitle_merger.py -v video.mkv --debug
```

---

## Performance Optimization

### Bulk Processing Tips
1. **Optimal Worker Count**: Use 75% of CPU cores
   ```bash
   # For 8-core system
   --workers 6
   ```

2. **SSD vs HDD**: Place temporary files on SSD:
   ```bash
   # Set TEMP environment variable
   export TMPDIR=/path/to/ssd/temp
   ```

3. **Network Drives**: Copy files locally first for better performance

### Memory Usage
- Each worker uses ~50-100MB RAM
- Large subtitle files may use more
- Monitor with `--debug` flag

### Processing Speed Expectations
- Single file: 2-10 seconds (depending on extraction needs)
- Bulk with 4 workers: ~4x faster than sequential
- SRT output is faster than ASS
