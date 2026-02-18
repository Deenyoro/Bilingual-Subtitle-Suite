# PGSRip Integration for Unified Subtitle Processor

This module provides integration with PGSRip for converting PGS (Presentation Graphic Stream) subtitles to SRT format using OCR technology.

## Overview

PGS subtitles are bitmap-based subtitles commonly found in Blu-ray discs and some streaming content. Unlike text-based subtitles (SRT, ASS), PGS subtitles require Optical Character Recognition (OCR) to convert them to text format.

## Features

- **Automatic PGS Detection**: Identifies PGS subtitle tracks in video containers
- **Multi-language OCR**: Supports Chinese (simplified/traditional) and English OCR
- **Batch Processing**: Convert PGS subtitles from multiple videos simultaneously
- **Integration**: Seamlessly integrates with existing subtitle workflows
- **Clean Installation**: Self-contained installation that doesn't affect the main application

## Installation

### Automatic Installation (Recommended)

```bash
# Install PGSRip and all dependencies
biss setup-pgsrip install

# Or use the setup script directly
python third_party/setup_pgsrip.py install
```

### Manual Installation

If automatic installation fails, you can install dependencies manually:

#### Windows
```bash
# Install Tesseract OCR
choco install tesseract
# Or download from: https://github.com/UB-Mannheim/tesseract/wiki

# Install MKVToolNix
choco install mkvtoolnix
# Or download from: https://mkvtoolnix.download/

# Install PGSRip
python third_party/setup_pgsrip.py install
```

#### macOS
```bash
# Install dependencies via Homebrew
brew install tesseract mkvtoolnix

# Install PGSRip
python third_party/setup_pgsrip.py install
```

#### Linux (Ubuntu/Debian)
```bash
# Install dependencies
sudo apt update
sudo apt install tesseract-ocr mkvtoolnix

# Install PGSRip
python third_party/setup_pgsrip.py install
```

## Usage

### Command Line Interface

#### Convert Single Video
```bash
# Convert PGS subtitles with auto-detection
biss convert-pgs movie.mkv

# Specify OCR language
biss convert-pgs movie.mkv --language chi_sim

# List available PGS tracks
biss convert-pgs movie.mkv --list-tracks

# Convert specific track
biss convert-pgs movie.mkv --track 3 --output subtitle.srt
```

#### Batch Conversion
```bash
# Batch convert all videos in directory
biss batch-convert-pgs /media/movies

# Recursive processing with specific language
biss batch-convert-pgs /media --recursive --language eng

# Use separate output directory
biss batch-convert-pgs /media/movies --output-dir /output/subtitles
```

#### Setup Management
```bash
# Check installation status
biss setup-pgsrip check

# Install with specific languages
biss setup-pgsrip install --languages eng chi_sim

# Uninstall PGSRip
biss setup-pgsrip uninstall
```

### Interactive Interface

Launch the interactive interface and select "PGS Subtitle Conversion":

```bash
biss interactive
```

The interactive interface provides:
- Single video PGS conversion
- Batch processing with progress tracking
- PGS track listing and analysis
- Installation status checking

### Integration with Bilingual Merging

PGS conversion is automatically integrated into the bilingual subtitle merging workflow:

```bash
# If no Chinese/English subtitles are found, PGS tracks will be converted automatically
biss merge movie.mkv --output bilingual.srt
```

## Supported Languages

The integration supports the following OCR languages:

- **English** (`eng`): Standard English text recognition
- **Chinese Simplified** (`chi_sim`): Simplified Chinese characters
- **Chinese Traditional** (`chi_tra`): Traditional Chinese characters

Additional languages can be added by:
1. Downloading the appropriate `.traineddata` files from [tessdata repository](https://github.com/tesseract-ocr/tessdata)
2. Placing them in the `third_party/pgsrip_install/tessdata/` directory
3. Using the language code in conversion commands

## Directory Structure

```
third_party/
├── __init__.py                     # Package initialization
├── setup_pgsrip.py                 # Installation script
├── pgsrip_wrapper.py               # Integration wrapper
├── README.md                       # This documentation
└── pgsrip_install/                 # Installation directory (created during setup)
    ├── pgsrip/                     # PGSRip source code
    ├── tesseract/                  # Tesseract installation info
    ├── mkvtoolnix/                 # MKVToolNix installation info
    ├── tessdata/                   # OCR language data files
    │   ├── eng.traineddata
    │   ├── chi_sim.traineddata
    │   └── chi_tra.traineddata
    ├── python_packages/            # Python dependencies
    └── pgsrip_config.json          # Configuration file
```

## Configuration

The installation creates a configuration file at `third_party/pgsrip_install/pgsrip_config.json`:

```json
{
  "installation_date": "timestamp",
  "system": "windows/darwin/linux",
  "architecture": "x86_64",
  "paths": {
    "pgsrip": "path/to/pgsrip",
    "tesseract": "path/to/tesseract",
    "mkvtoolnix": "path/to/mkvtoolnix",
    "tessdata": "path/to/tessdata",
    "python_packages": "path/to/python_packages"
  },
  "languages": ["eng", "chi_sim", "chi_tra"],
  "version": "1.0.0"
}
```

## Troubleshooting

### Common Issues

1. **"PGSRip is not installed"**
   - Run: `biss setup-pgsrip install`
   - Check: `biss setup-pgsrip check`

2. **"Tesseract not found"**
   - Install Tesseract OCR for your platform
   - Ensure it's in your system PATH

3. **"MKVToolNix not found"**
   - Install MKVToolNix for your platform
   - Ensure `mkvextract` is accessible

4. **OCR accuracy issues**
   - Try different language models
   - Check video quality and subtitle clarity
   - Consider manual correction of output

5. **Conversion timeout**
   - Large video files may take time to process
   - Check available disk space
   - Monitor system resources

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
biss --debug convert-pgs movie.mkv
```

### Manual Cleanup

To completely remove PGSRip installation:

```bash
# Automatic cleanup
biss setup-pgsrip uninstall

# Manual cleanup
rm -rf third_party/pgsrip_install/
```

## Performance Considerations

- **Processing Time**: PGS conversion is CPU-intensive and may take several minutes per video
- **Disk Space**: Temporary files are created during conversion
- **Memory Usage**: Large subtitle tracks may require significant RAM
- **Accuracy**: OCR accuracy depends on video quality and subtitle clarity

## Limitations

- OCR accuracy is not 100% and may require manual correction
- Processing time increases with video length and subtitle density
- Some stylized or decorative fonts may not be recognized accurately
- Requires significant computational resources for batch processing

## Contributing

To add support for additional languages:

1. Download the appropriate `.traineddata` file from [tessdata repository](https://github.com/tesseract-ocr/tessdata)
2. Add the language code to `supported_languages` in `setup_pgsrip.py`
3. Update the language mapping in `pgsrip_wrapper.py`
4. Test the integration and submit a pull request

## License

This integration module follows the same license as the main application. PGSRip and its dependencies have their own licenses:

- **PGSRip**: [MIT License](https://github.com/ratoaq2/pgsrip/blob/main/LICENSE)
- **Tesseract**: [Apache License 2.0](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)
- **MKVToolNix**: [GPL v2](https://gitlab.com/mbunkus/mkvtoolnix/-/blob/main/COPYING)
