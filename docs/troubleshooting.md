# Troubleshooting Guide

Comprehensive troubleshooting guide for common issues and their solutions.

## Table of Contents
- [Installation Issues](#installation-issues)
- [Processing Errors](#processing-errors)
- [Alignment Problems](#alignment-problems)
- [PGS Conversion Issues](#pgs-conversion-issues)
- [Performance Problems](#performance-problems)
- [File Format Issues](#file-format-issues)
- [Environment and Configuration](#environment-and-configuration)

## Installation Issues

### Issue: Python Version Compatibility

**Symptoms**:
```
SyntaxError: invalid syntax
TypeError: unsupported operand type(s)
```

**Solution**:
```bash
# Check Python version
python --version

# Minimum required: Python 3.8
# Recommended: Python 3.10+

# Install correct version if needed
# Windows: Download from python.org
# macOS: brew install python@3.10
# Linux: sudo apt install python3.10
```

### Issue: Missing Dependencies

**Symptoms**:
```
ModuleNotFoundError: No module named 'charset_normalizer'
ImportError: cannot import name 'Path'
```

**Solution**:
```bash
# Install all dependencies
pip install -r requirements.txt

# Install specific missing packages
pip install charset-normalizer pathlib typing dataclasses

# For Windows curses support
pip install windows-curses
```

### Issue: FFmpeg Not Found

**Symptoms**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
FFmpeg not found in system PATH
```

**Solutions**:

**Windows**:
```bash
# Using Chocolatey
choco install ffmpeg

# Or download from https://ffmpeg.org/download.html
# Add to PATH environment variable
```

**macOS**:
```bash
# Using Homebrew
brew install ffmpeg
```

**Linux**:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# CentOS/RHEL/Fedora
sudo dnf install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

### Issue: Permission Errors

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied
Access is denied
```

**Solutions**:
```bash
# Check file permissions
ls -la file.mkv

# Fix permissions (Linux/macOS)
chmod 644 subtitle.srt
chmod 755 directory/

# Run as administrator (Windows)
# Right-click Command Prompt → "Run as administrator"

# Check disk space
df -h  # Linux/macOS
dir    # Windows
```

## Processing Errors

### Issue: Video File Not Recognized

**Symptoms**:
```
Error: No subtitle tracks found in video file
Unsupported video format
```

**Solutions**:
```bash
# Check file format
ffprobe -v quiet -show_format movie.mkv

# Verify file integrity
ffmpeg -v error -i movie.mkv -f null -

# Supported formats: MKV, MP4, AVI, M4V, MOV, WebM, TS, MPG

# Convert if necessary
ffmpeg -i input.avi -c copy output.mkv
```

### Issue: Subtitle Track Detection Failure

**Symptoms**:
```
No Chinese/English subtitle tracks found
Unable to detect subtitle language
```

**Solutions**:
```bash
# List all tracks manually
python biss.py merge movie.mkv --list-tracks

# Force track selection
python biss.py merge movie.mkv --chinese-track 2 --english-track 1

# Check external files
ls *.srt *.ass *.vtt

# Verify subtitle file format
file subtitle.srt
head -n 5 subtitle.srt
```

### Issue: Encoding Detection Problems

**Symptoms**:
```
UnicodeDecodeError: 'utf-8' codec can't decode
Encoding detection failed
```

**Solutions**:
```bash
# Install better encoding detection
pip install charset-normalizer

# Force specific encoding
python biss.py convert subtitle.srt --encoding gb18030 --force

# Check file encoding manually
file -i subtitle.srt  # Linux/macOS
chardet subtitle.srt  # If chardet installed

# Common Chinese encodings: gb18030, gbk, big5
```

### Issue: Output File Creation Failure

**Symptoms**:
```
Failed to create output file
Permission denied writing to output directory
```

**Solutions**:
```bash
# Check output directory permissions
ls -la output/

# Create directory if missing
mkdir -p output/

# Specify different output location
python biss.py merge movie.mkv --output /tmp/output.srt

# Check disk space
df -h /output/path
```

## Alignment Problems

### Issue: Large Timing Differences

**Symptoms**:
```
Anchor options show >10 second differences
No good alignment points found
```

**Solutions**:
```bash
# Use scan strategy for better detection
python biss.py merge movie.mkv --auto-align --sync-strategy scan

# Enable manual alignment
python biss.py merge movie.mkv --auto-align --manual-align

# Check if tracks are from same source
python biss.py merge movie.mkv --list-tracks --debug

# Try different alignment strategies
python biss.py merge movie.mkv --auto-align --sync-strategy translation --use-translation
```

### Issue: Major Timing Offsets (50+ Seconds)

**Symptoms**:
```
Chinese and English subtitles appear at completely different times
Timing differences of 50+ seconds between tracks
Semantic alignment anchor finding fails
```

**Real-World Example**: Made in Abyss episodes where external Chinese subtitles (.zh.srt) have major timing differences from embedded English tracks.

**Enhanced Solutions**:
```bash
# Enable enhanced mixed track realignment
python biss.py merge movie.mkv --auto-align --enable-mixed-realignment

# Use low confidence threshold for large offsets
python biss.py merge movie.mkv --auto-align --use-translation --alignment-threshold 0.3

# Combined approach for maximum success rate
python biss.py merge movie.mkv --auto-align --use-translation \
  --alignment-threshold 0.3 --enable-mixed-realignment

# Debug the alignment process
python biss.py --debug merge movie.mkv --auto-align --use-translation \
  --alignment-threshold 0.3 --enable-mixed-realignment
```

**What This Does**:
- **Mixed Track Realignment**: Detects embedded vs external track scenarios
- **Low Confidence Threshold**: Accepts weaker matches for initial anchor detection
- **Translation-Assisted Matching**: Uses Google Translate for cross-language content similarity
- **Pre-Anchor Deletion**: Removes mistimed content before the anchor point
- **Global Time Shift**: Applies calculated offset to align entire external track

**Expected Results**:
```
✅ Found semantic anchor point: embedded[4] ↔ external[3]
   Embedded: This compass... (11.730s)
   External: 在這個羅盤... (68.497s)
   Confidence: 0.45, Time offset: -56.767s
🔧 Applying global time shift: -56.767s to external track
🗑️ Pre-anchor deletion: 3 entries removed from external track
✅ Successfully created aligned bilingual subtitles
```

### Issue: Poor Alignment Quality

**Symptoms**:
```
Subtitles still misaligned after processing
Low confidence scores in alignment
```

**Solutions**:
```bash
# Increase alignment threshold
python biss.py merge movie.mkv --auto-align --alignment-threshold 0.9

# Use manual alignment for precision
python biss.py merge movie.mkv --auto-align --manual-align

# Enable translation assistance
python biss.py merge movie.mkv --auto-align --use-translation

# Debug alignment process
python biss.py --debug merge movie.mkv --auto-align
```

### Issue: Manual Interface Not Responding

**Symptoms**:
```
Interactive prompts don't appear
Input not accepted in manual alignment
```

**Solutions**:
```bash
# Use different terminal
# PowerShell instead of Command Prompt (Windows)
# Terminal.app instead of iTerm2 (macOS)

# Check for input redirection
python biss.py merge movie.mkv --manual-align < /dev/null

# Disable colors if causing issues
python biss.py --no-colors merge movie.mkv --manual-align

# Try interactive mode instead
python biss.py interactive
```

### Issue: Translation Service Unavailable

**Symptoms**:
```
Translation service not available
Google Translate API error
```

**Solutions**:
```bash
# Set API key environment variable
export GOOGLE_TRANSLATE_API_KEY="your-key-here"

# Or pass directly
python biss.py merge movie.mkv --translation-api-key "your-key"

# Verify API key format and permissions
# Check Google Cloud Console for quota/billing

# Use without translation as fallback
python biss.py merge movie.mkv --auto-align --sync-strategy scan
```

## PGS Conversion Issues

### Issue: PGSRip Installation Failure

**Symptoms**:
```
PGSRip installation failed
Unable to download components
```

**Solutions**:
```bash
# Check internet connection
ping google.com

# Retry installation
python biss.py setup-pgsrip install

# Manual installation
# Download components manually and place in third_party/pgsrip_install/

# Check antivirus software
# Add exclusion for third_party/ directory
```

### Issue: OCR Quality Problems

**Symptoms**:
```
Poor text recognition quality
Many incorrect characters in output
```

**Solutions**:
```bash
# Try different language model
python biss.py convert-pgs movie.mkv --language eng

# Use high quality mode
python biss.py convert-pgs movie.mkv --language chi_sim --quality high

# Enable preprocessing
python biss.py convert-pgs movie.mkv --language chi_sim --denoise --enhance-contrast

# Check source image quality
# Higher resolution PGS generally produces better OCR results
```

### Issue: No PGS Tracks Found

**Symptoms**:
```
No PGS tracks detected in video file
Unable to extract PGS subtitles
```

**Solutions**:
```bash
# Verify track types
ffprobe -v quiet -show_streams movie.mkv | grep codec_name

# List all subtitle tracks
python biss.py convert-pgs movie.mkv --list-tracks

# Check for SUP files (external PGS)
ls *.sup

# Some "PGS" tracks might be different formats
# Try: dvd_subtitle, hdmv_pgs_subtitle
```

## Performance Problems

### Issue: Slow Processing Speed

**Symptoms**:
```
Processing takes very long time
High CPU/memory usage
```

**Solutions**:
```bash
# Enable parallel processing
python biss.py batch-convert /media --parallel --max-workers 4

# Use fast mode for PGS
python biss.py convert-pgs movie.mkv --quality fast

# Process smaller batches
python biss.py batch-merge "subset/" --auto-confirm

# Check system resources
top    # Linux/macOS
taskmgr  # Windows
```

### Issue: Memory Issues

**Symptoms**:
```
Out of memory errors
System becomes unresponsive
```

**Solutions**:
```bash
# Process files individually instead of batch
python biss.py merge movie.mkv

# Reduce worker count
python biss.py batch-convert /media --parallel --max-workers 2

# Close other applications
# Increase virtual memory (Windows)
# Add swap space (Linux)

# For very large files
python biss.py merge huge-movie.mkv --stream-mode
```

### Issue: Network/API Timeouts

**Symptoms**:
```
Translation API timeout
Network connection errors
```

**Solutions**:
```bash
# Check internet connection
ping translate.googleapis.com

# Increase timeout values
export TRANSLATION_TIMEOUT=60

# Reduce translation requests
python biss.py merge movie.mkv --translation-limit 5

# Use offline mode
python biss.py merge movie.mkv --auto-align --sync-strategy scan
```

## File Format Issues

### Issue: Unsupported Subtitle Format

**Symptoms**:
```
Unsupported subtitle format: .idx/.sub
Cannot parse subtitle file
```

**Solutions**:
```bash
# Convert to supported format first
# Use subtitle conversion tools:
# - SubtitleEdit
# - Aegisub
# - FFmpeg

# Supported formats: SRT, ASS, VTT, PGS

# For IDX/SUB files, use OCR tools to convert to SRT
```

### Issue: Corrupted Subtitle Files

**Symptoms**:
```
Malformed subtitle file
Parsing error at line X
```

**Solutions**:
```bash
# Check file integrity
head -n 20 subtitle.srt
tail -n 20 subtitle.srt

# Validate SRT format
# Each subtitle should have:
# 1. Number
# 2. Timestamp
# 3. Text
# 4. Blank line

# Fix common issues
# Remove BOM: sed -i '1s/^\xEF\xBB\xBF//' subtitle.srt
# Fix line endings: dos2unix subtitle.srt
```

### Issue: Video Container Problems

**Symptoms**:
```
Cannot open video file
Corrupted video container
```

**Solutions**:
```bash
# Check file integrity
ffmpeg -v error -i movie.mkv -f null -

# Repair container if possible
ffmpeg -i broken.mkv -c copy repaired.mkv

# Extract subtitles manually
ffmpeg -i movie.mkv -map 0:s:0 subtitle.srt

# Use different extraction method
mkvextract tracks movie.mkv 2:subtitle.srt
```

## Environment and Configuration

### Issue: Path and Environment Problems

**Symptoms**:
```
Command not found
Environment variable not set
```

**Solutions**:
```bash
# Check PATH
echo $PATH  # Linux/macOS
echo %PATH%  # Windows

# Add to PATH temporarily
export PATH=$PATH:/path/to/biss  # Linux/macOS
set PATH=%PATH%;C:\path\to\biss  # Windows

# Set environment variables
export GOOGLE_TRANSLATE_API_KEY="key"
export FFMPEG_TIMEOUT=1800

# Create .env file for persistent settings
echo "GOOGLE_TRANSLATE_API_KEY=your-key" > .env
```

### Issue: Configuration File Problems

**Symptoms**:
```
Configuration file not found
Invalid configuration format
```

**Solutions**:
```bash
# Create default configuration
python biss.py --create-config

# Validate JSON configuration
python -m json.tool .subtitle-processor.json

# Reset to defaults
rm .subtitle-processor.json
python biss.py --create-config
```

### Issue: Logging and Debug Information

**Enable comprehensive debugging**:
```bash
# Maximum debug information
python biss.py --debug --verbose merge movie.mkv --auto-align --manual-align

# Log to file
python biss.py --debug merge movie.mkv --log-file debug.log

# Check log files
tail -f debug.log

# System information
python biss.py --version
python biss.py setup-pgsrip check
```

## Getting Help

### Collect Debug Information

When reporting issues, include:

```bash
# System information
python biss.py --version
python --version
ffmpeg -version

# Error reproduction
python biss.py --debug --verbose [your-command] 2>&1 | tee error.log

# File information
ffprobe -v quiet -show_format -show_streams movie.mkv
file subtitle.srt
ls -la problematic-files/
```

### Community Resources

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Check docs/ directory for detailed guides
- **Examples**: Review docs/examples.md for similar use cases
- **Debug Mode**: Always use --debug for detailed error information
