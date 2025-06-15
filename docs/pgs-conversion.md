# PGS Subtitle Conversion Guide

Comprehensive guide to converting PGS (Presentation Graphic Stream) subtitles to text format using OCR technology.

> **Powered by PGSRip**: This functionality is made possible by integrating [PGSRip by ratoaq2](https://github.com/ratoaq2/pgsrip), an excellent tool for reliable PGS subtitle extraction and processing. We gratefully acknowledge ratoaq2's contribution to the subtitle processing community.

## Table of Contents
- [Overview](#overview)
- [Installation and Setup](#installation-and-setup)
- [Basic Usage](#basic-usage)
- [Advanced Configuration](#advanced-configuration)
- [Integration with Bilingual Merging](#integration-with-bilingual-merging)
- [Troubleshooting](#troubleshooting)
- [Platform-Specific Notes](#platform-specific-notes)

## Overview

### What are PGS Subtitles?

PGS (Presentation Graphic Stream) subtitles are image-based subtitle tracks commonly found in Blu-ray discs and high-quality video files. Unlike text-based formats (SRT, ASS), PGS subtitles are rendered as bitmap images, making them incompatible with standard subtitle processing tools.

### Why Convert PGS to Text?

- **Editability**: Text-based subtitles can be modified, translated, and styled
- **Compatibility**: Works with all media players and subtitle processors
- **Integration**: Can be merged with other subtitle tracks for bilingual output
- **Accessibility**: Better support for screen readers and accessibility tools
- **File Size**: Text subtitles are significantly smaller than image-based ones

### OCR Technology

The Chinese Subtitle Processor uses Tesseract OCR with specialized language models:
- **English**: High accuracy for Latin characters
- **Chinese Simplified**: Optimized for simplified Chinese characters
- **Chinese Traditional**: Support for traditional Chinese characters
- **Multi-language**: Can process mixed-language content

## Installation and Setup

### Automated Installation (Recommended)

The easiest way to set up PGS conversion is using the automated installer:

```bash
# One-command installation
python biss.py setup-pgsrip install
```

This command automatically:
1. Downloads and installs PGSRip
2. Installs Tesseract OCR
3. Downloads language data files
4. Configures MKVToolNix integration
5. Sets up the complete processing pipeline

### Installation Process

**Step 1: Check Prerequisites**
```bash
python biss.py setup-pgsrip check
```

**Step 2: Install Components**
```bash
python biss.py setup-pgsrip install

Installing PGS conversion components...
✓ Downloading PGSRip...
✓ Installing Tesseract OCR...
✓ Downloading language data (English)...
✓ Downloading language data (Chinese Simplified)...
✓ Downloading language data (Chinese Traditional)...
✓ Installing MKVToolNix...
✓ Configuring integration...

Installation complete! PGS conversion is now available.
```

**Step 3: Verify Installation**
```bash
python biss.py setup-pgsrip check

PGSRip Installation Status:
✓ PGSRip: Installed (v1.0.2)
✓ Tesseract OCR: Installed (v5.3.0)
✓ MKVToolNix: Installed (v70.0.0)
✓ Language Data: English, Chinese Simplified, Chinese Traditional

Installation directory: third_party/pgsrip_install/
All components ready for PGS conversion.
```

### Manual Installation

If automatic installation fails, you can install components manually:

**Windows:**
```bash
# Using Chocolatey
choco install tesseract mkvtoolnix

# Download language data manually
# Place in: C:\Program Files\Tesseract-OCR\tessdata\
```

**macOS:**
```bash
# Using Homebrew
brew install tesseract mkvtoolnix

# Install language data
brew install tesseract-lang
```

**Linux (Ubuntu/Debian):**
```bash
# Install packages
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra mkvtoolnix

# Verify installation
tesseract --list-langs
```

## Basic Usage

### Single File Conversion

**CLI Command:**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim
```

**Interactive Mode:**
1. Select "PGS Subtitle Conversion" from main menu
2. Choose "Convert PGS from single video"
3. Enter video file path
4. Select PGS track and OCR language
5. Wait for conversion to complete

### Supported Languages

- `eng` - English
- `chi_sim` - Chinese Simplified
- `chi_tra` - Chinese Traditional

### Output Files

PGS conversion creates SRT files with language-specific naming:
```
movie.mkv → movie.chi_sim.srt (Chinese Simplified)
movie.mkv → movie.eng.srt (English)
movie.mkv → movie.chi_tra.srt (Chinese Traditional)
```

### Batch Conversion

**Process multiple files:**
```bash
python biss.py batch-convert-pgs /media/movies --language chi_sim --recursive
```

**Interactive batch processing:**
1. Select "PGS Subtitle Conversion" → "Batch convert PGS from multiple videos"
2. Enter directory path
3. Configure options (recursive, language, confirmation)
4. Monitor progress

## Advanced Configuration

### OCR Quality Settings

**High Quality (Slower):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim --quality high
```

**Fast Processing (Lower Quality):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim --quality fast
```

### Custom Output Paths

```bash
python biss.py convert-pgs movie.mkv --language chi_sim --output custom-name.srt
```

### Track Selection

**List available PGS tracks:**
```bash
python biss.py convert-pgs movie.mkv --list-tracks

Available PGS tracks:
Track 3: PGS (Chinese) - 1,247 images
Track 4: PGS (English) - 23 images (likely forced/signs)
Track 5: PGS (Japanese) - 1,251 images
```

**Select specific track:**
```bash
python biss.py convert-pgs movie.mkv --track 3 --language chi_sim
```

### Processing Options

**Preprocessing filters:**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim \
  --denoise \
  --enhance-contrast \
  --upscale 2x
```

**OCR confidence threshold:**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim --confidence 0.8
```

## Integration with Bilingual Merging

### Automatic PGS Fallback

When no text-based subtitles are available, the system automatically attempts PGS conversion:

```bash
python biss.py merge movie.mkv
# If no SRT/ASS tracks found, automatically converts PGS
```

### Force PGS Conversion

```bash
python biss.py merge movie.mkv --force-pgs --pgs-language chi_sim
```

### PGS + External File Merging

```bash
# Convert PGS to Chinese, merge with external English
python biss.py merge movie.mkv --force-pgs --pgs-language chi_sim \
  --english external-english.srt
```

### Batch Processing with PGS

```bash
python biss.py batch-merge "Season 01" --force-pgs --pgs-language chi_sim \
  --auto-confirm
```

## Troubleshooting

### Common Issues

#### Issue: "PGSRip not installed"
**Solution:**
```bash
python biss.py setup-pgsrip install
```

#### Issue: "No PGS tracks found"
**Solution:**
```bash
# List all tracks to verify
python biss.py convert-pgs movie.mkv --list-tracks

# Check if tracks are actually SUP format
ffprobe -v quiet -show_streams movie.mkv | grep codec_name
```

#### Issue: "OCR quality is poor"
**Solutions:**
```bash
# Try different language model
python biss.py convert-pgs movie.mkv --language eng

# Use high quality mode
python biss.py convert-pgs movie.mkv --language chi_sim --quality high

# Enable preprocessing
python biss.py convert-pgs movie.mkv --language chi_sim --denoise --enhance-contrast
```

#### Issue: "Conversion is very slow"
**Solutions:**
```bash
# Use fast mode
python biss.py convert-pgs movie.mkv --language chi_sim --quality fast

# Process smaller segments
python biss.py convert-pgs movie.mkv --language chi_sim --segment-size 100
```

### Debug Mode

Enable detailed logging for troubleshooting:
```bash
python biss.py --debug convert-pgs movie.mkv --language chi_sim
```

### Log Analysis

Check conversion logs:
```
PGS Conversion Log:
✓ Extracted 1,247 subtitle images
✓ Preprocessed images (denoising, contrast enhancement)
✓ OCR processing: 1,247/1,247 images
⚠ Low confidence: 23 images (1.8%)
✓ Generated SRT file: movie.chi_sim.srt
```

## Platform-Specific Notes

### Windows

**Installation Location:**
```
third_party/pgsrip_install/
├── pgsrip/
├── tesseract/
└── mkvtoolnix/
```

**Path Configuration:**
The installer automatically configures PATH variables for the session.

**Antivirus Considerations:**
Some antivirus software may flag downloaded components. Add exclusions for:
- `third_party/pgsrip_install/`
- Tesseract OCR installation directory

### Linux

**Distribution Support:**
- Ubuntu/Debian: Full automated installation
- CentOS/RHEL/Fedora: Full automated installation
- Arch Linux: Full automated installation
- openSUSE: Full automated installation

**Package Managers:**
The installer automatically detects and uses the appropriate package manager.

**Permissions:**
Some distributions may require sudo access for package installation.

### macOS

**Homebrew Integration:**
The installer uses Homebrew for component installation.

**Apple Silicon (M1/M2):**
All components are compatible with Apple Silicon Macs.

**Xcode Command Line Tools:**
Required for some compilation steps. Install with:
```bash
xcode-select --install
```

## Performance Optimization

### Hardware Acceleration

**GPU Acceleration (NVIDIA):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim --gpu-acceleration
```

**Multi-threading:**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim --threads 8
```

### Memory Management

**Large Files:**
```bash
python biss.py convert-pgs large-movie.mkv --language chi_sim --memory-limit 4GB
```

**Batch Processing:**
```bash
python biss.py batch-convert-pgs /media/movies --language chi_sim \
  --parallel --max-workers 4
```

### Quality vs Speed Trade-offs

**Maximum Quality (Slowest):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim \
  --quality maximum \
  --denoise \
  --enhance-contrast \
  --upscale 2x \
  --confidence 0.9
```

**Balanced (Recommended):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim \
  --quality high \
  --confidence 0.8
```

**Speed Priority (Fastest):**
```bash
python biss.py convert-pgs movie.mkv --language chi_sim \
  --quality fast \
  --confidence 0.6
```
