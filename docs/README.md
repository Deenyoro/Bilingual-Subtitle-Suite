# Bilingual Subtitle Suite Documentation

Welcome to the comprehensive documentation for the Bilingual Subtitle Suite - a sophisticated Python application for processing, aligning, and merging subtitle files with advanced bilingual subtitle creation capabilities.

## 📚 Documentation Index

### Getting Started
- **[Main README](../README.md)** - Project overview, quick start, and basic usage
- **[Installation Guide](#installation)** - Detailed installation instructions for all platforms
- **[Quick Start Tutorial](#quick-start)** - Step-by-step guide for new users

### User Guides
- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Interactive Mode Guide](interactive-guide.md)** - Step-by-step interactive interface guide
- **[Real-World Examples](examples.md)** - Practical usage scenarios and workflows

### Advanced Features
- **[Advanced Features Guide](advanced-features.md)** - Enhanced alignment, translation integration, manual sync
- **[PGS Conversion Guide](pgs-conversion.md)** - PGS subtitle conversion setup and usage

### Support & Development
- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions
- **[API Reference](api-reference.md)** - Developer reference for extending functionality

## 🚀 Quick Navigation

### By User Type

**New Users**:
1. [Main README](../README.md) - Start here
2. [Interactive Mode Guide](interactive-guide.md) - Learn the GUI
3. [Real-World Examples](examples.md) - See practical usage

**Power Users**:
1. [CLI Reference](cli-reference.md) - Master the command line
2. [Advanced Features Guide](advanced-features.md) - Unlock advanced capabilities
3. [PGS Conversion Guide](pgs-conversion.md) - Handle image-based subtitles

**Developers**:
1. [API Reference](api-reference.md) - Extend and integrate
2. [Troubleshooting Guide](troubleshooting.md) - Debug and optimize
3. [Advanced Features Guide](advanced-features.md) - Understand internals

### By Task

**Creating Bilingual Subtitles**:
- [CLI Reference - Merge Command](cli-reference.md#merge-command)
- [Interactive Guide - Bilingual Merging](interactive-guide.md#bilingual-subtitle-merging)
- [Examples - Anime Processing](examples.md#anime-processing)

**Handling Timing Issues**:
- [Advanced Features - Manual Synchronization](advanced-features.md#manual-synchronization-interface)
- [CLI Reference - Enhanced Alignment](cli-reference.md#enhanced-alignment-options)
- [Troubleshooting - Alignment Problems](troubleshooting.md#alignment-problems)

**Batch Processing**:
- [CLI Reference - Batch Commands](cli-reference.md#batch-commands)
- [Interactive Guide - Batch Operations](interactive-guide.md#batch-operations)
- [Examples - Batch Strategies](examples.md#batch-processing-strategies)

**PGS Conversion**:
- [PGS Conversion Guide](pgs-conversion.md) - Complete guide
- [CLI Reference - PGS Commands](cli-reference.md#pgs-commands)
- [Troubleshooting - PGS Issues](troubleshooting.md#pgs-conversion-issues)

## 🎯 Feature Overview

### Core Capabilities

**Bilingual Subtitle Creation**:
- Merge Chinese and English subtitles into unified tracks
- Intelligent track selection with multi-criteria scoring
- Enhanced alignment system with global synchronization
- Translation-assisted semantic matching

**Advanced Processing**:
- Two-phase alignment: global sync + detailed event matching
- Manual synchronization interface with anchor point selection
- Cross-platform PGS (image-based) subtitle conversion
- Comprehensive encoding detection and conversion

**User Interfaces**:
- Command-line interface with 20+ options
- Interactive menu-driven interface
- Feature parity between CLI and interactive modes
- Batch processing with confirmation workflows

### Supported Formats

**Video Containers**: MKV, MP4, AVI, M4V, MOV, WebM, TS, MPG
**Subtitle Formats**: SRT, ASS/SSA, VTT, PGS (via OCR)
**Languages**: Chinese (Simplified/Traditional), English, Japanese, Korean
**Encodings**: UTF-8, UTF-16, GB18030, GBK, Big5, Shift-JIS

## 📖 Documentation Structure

### User Documentation

**[CLI Reference](cli-reference.md)**
- Complete command-line interface documentation
- All commands, options, and parameters
- Usage examples and advanced patterns
- Environment integration and automation

**[Interactive Mode Guide](interactive-guide.md)**
- Step-by-step interactive interface walkthrough
- Menu navigation and workflow explanations
- Best practices and tips for efficient usage
- Troubleshooting interactive mode issues

**[Real-World Examples](examples.md)**
- Practical usage scenarios for different content types
- Anime, movie, and TV series processing workflows
- Batch processing strategies and automation scripts
- Quality control and optimization techniques

### Technical Documentation

**[Advanced Features Guide](advanced-features.md)**
- Enhanced alignment system deep dive
- Translation-assisted alignment configuration
- Manual synchronization interface details
- Intelligent track selection algorithms

**[PGS Conversion Guide](pgs-conversion.md)**
- Complete PGS subtitle conversion setup
- OCR technology and language support
- Cross-platform installation and configuration
- Performance optimization and troubleshooting

**[API Reference](api-reference.md)**
- Developer reference for extending functionality
- Core modules and processor classes
- Configuration system and extension points
- Integration examples and custom implementations

### Support Documentation

**[Troubleshooting Guide](troubleshooting.md)**
- Common issues and their solutions
- Installation, processing, and performance problems
- Debug techniques and log analysis
- Platform-specific considerations

## 🔧 Installation

### Quick Installation
```bash
# Clone repository
git clone <repository-url>
cd chsub

# Install dependencies
pip install -r requirements.txt

# Verify installation
python biss.py --version
```

### Optional Components
```bash
# PGS conversion support
python biss.py setup-pgsrip install

# Enhanced encoding detection
pip install charset-normalizer

# Translation services (requires API key)
export GOOGLE_TRANSLATE_API_KEY="your-api-key"
```

## 🚀 Quick Start

### Interactive Mode (Recommended for Beginners)
```bash
python biss.py
```

### Command Line (Power Users)
```bash
# Basic bilingual subtitle creation
python biss.py merge movie.mkv

# Enhanced alignment with manual control
python biss.py merge movie.mkv --auto-align --manual-align

# Batch process entire directory
python biss.py batch-merge "Season 01" --auto-confirm
```

## 📋 Common Workflows

### Anime Processing
1. **Basic Episode**: `python biss.py merge episode.mkv`
2. **Complex Timing**: `python biss.py merge episode.mkv --auto-align --manual-align`
3. **Batch Season**: `python biss.py batch-merge "Season 01" --auto-align`

### Movie Processing
1. **Standard Movie**: `python biss.py merge movie.mkv --auto-align`
2. **PGS Subtitles**: `python biss.py merge movie.mkv --force-pgs --pgs-language chi_sim`
3. **High Precision**: `python biss.py merge movie.mkv --auto-align --manual-align --use-translation`

### Batch Operations
1. **Convert Encodings**: `python biss.py batch-convert /media --encoding utf-8 --backup`
2. **Merge Videos**: `python biss.py batch-merge /media --auto-align --auto-confirm`
3. **Realign Subtitles**: `python biss.py batch-realign /media --source-ext .zh.srt --reference-ext .en.srt`

## 🆘 Getting Help

### Documentation
- Check the relevant guide for your use case
- Review examples for similar scenarios
- Consult troubleshooting guide for common issues

### Debug Information
```bash
# Enable debug mode for detailed logging
python biss.py --debug --verbose [command]

# Check system information
python biss.py --version
python biss.py setup-pgsrip check
```

### Community Support
- **GitHub Issues**: Report bugs and request features
- **Documentation**: Comprehensive guides and examples
- **Debug Logs**: Include debug output when reporting issues

## 📝 Contributing

We welcome contributions to improve the Chinese Subtitle Processor:

- **Bug Reports**: Use GitHub issues with debug information
- **Feature Requests**: Describe use cases and expected behavior
- **Documentation**: Help improve guides and examples
- **Code Contributions**: Follow existing patterns and include tests

## 📄 License

MIT License - see [LICENSE](../LICENSE) file for details.

---

**Navigation**: [Main README](../README.md) | [CLI Reference](cli-reference.md) | [Interactive Guide](interactive-guide.md) | [Examples](examples.md) | [Advanced Features](advanced-features.md) | [PGS Conversion](pgs-conversion.md) | [Troubleshooting](troubleshooting.md) | [API Reference](api-reference.md)
