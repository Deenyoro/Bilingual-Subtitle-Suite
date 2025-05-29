# Enhanced Subtitle Realignment Tool

A powerful and feature-rich Python tool for **bulk subtitle synchronization** that automatically or interactively aligns subtitle files to reference timings. This enhanced version offers both **automatic alignment** (matching earliest events) and a new **interactive mode** where you can manually select specific alignment points between subtitles.

---

## Key Features

### 1. **Interactive Alignment Mode** 
- **Visual Interface**: Navigate through subtitles using arrow keys in a curses-based UI
- **Side-by-Side Preview**: View source and reference subtitles simultaneously
- **Manual Selection**: Choose exact alignment points for precise synchronization
- **Tab Navigation**: Switch between source/reference columns with TAB key
- **Auto-Removal**: Automatically removes all events before selected alignment points
- **Console Fallback**: Basic text interface when curses is unavailable

### 2. **Automatic Pair Detection & Bulk Processing**
- Intelligently matches subtitle pairs by base filename
- Processes entire directories in one command
- Supports mixed formats (e.g., `.zh.ass` with `.en.srt`)
- Detailed progress reporting for batch operations

### 3. **Enhanced File Format Support**
- **SRT Files**: Full support for SubRip format with millisecond precision
- **ASS/SSA Files**: Advanced SubStation Alpha parsing with format preservation
- **Encoding Detection**: Automatic detection of file encodings (UTF-8, GBK, Big5, etc.)
- **Malformed File Handling**: Robust parsing that gracefully handles format errors

### 4. **Professional-Grade Features**
- **Automatic Backups**: Creates timestamped backups before modifications
- **Colored Logging**: Clear, color-coded output for different message types
- **Type Safety**: Full type hints for better IDE support and code clarity
- **Object-Oriented Design**: Clean, maintainable architecture with dedicated handlers
- **Comprehensive Error Handling**: Detailed error messages with recovery strategies

### 5. **Flexible Output Options**
- **In-Place Updates**: Modify original files (with automatic backup)
- **Custom Suffixes**: Add suffixes like `.aligned` to preserve originals
- **Backup Management**: Organized backup folder with timestamps
- **Encoding Preservation**: Maintains original file encoding in output

### 6. **Millisecond Precision Timing**
- All timing calculations performed in milliseconds internally
- Accurate conversion between different timestamp formats
- Proper handling of negative time values (clamped to zero)
- Support for both centisecond and millisecond ASS formats

---

## 📋 Requirements

- **Python 3.6+** (uses f-strings and type hints)
- **No external dependencies** for basic functionality
- **Optional**: `curses` module for enhanced interactive interface (pre-installed on Unix/macOS, may need `windows-curses` on Windows)

---

## 🚀 Installation

```bash
# Clone or download the script
wget https://raw.githubusercontent.com/yourusername/subtitle-realign/main/realign_subtitles_enhanced.py

# Make it executable (Unix/macOS)
chmod +x realign_subtitles_enhanced.py

# Optional: Install windows-curses for better interactive mode on Windows
pip install windows-curses  # Windows only
```

---

## 📖 Usage Examples

### Basic Automatic Alignment
Align Chinese subtitles to English reference (original behavior):

```bash
python realign_subtitles_enhanced.py --src-ext .zh.ass --ref-ext .en.ass
```

### Interactive Mode with Visual Selection
Manually choose alignment points with visual preview:

```bash
python realign_subtitles_enhanced.py --src-ext .zh.ass --ref-ext .en.ass --interactive
```

### Process Specific Folder with Custom Output
Align subtitles in a specific directory and add suffix:

```bash
python realign_subtitles_enhanced.py \
  --folder "/path/to/TV Series/Season 1" \
  --src-ext .chs.srt \
  --ref-ext .eng.srt \
  --output-suffix .aligned
```

### Debug Mode Without Backups
Enable detailed logging and skip backup creation:

```bash
python realign_subtitles_enhanced.py \
  --src-ext .cn.ass \
  --ref-ext .en.ass \
  --debug \
  --no-backup
```

### Complex Multi-Language Setup
Handle multiple subtitle variants:

```bash
# First pass: Align simplified Chinese to English
python realign_subtitles_enhanced.py --src-ext .chs.ass --ref-ext .en.ass

# Second pass: Align traditional Chinese to English
python realign_subtitles_enhanced.py --src-ext .cht.ass --ref-ext .en.ass
```

---

## 🎮 Interactive Mode Guide

The interactive mode provides a visual interface for precise subtitle alignment:

### Curses Interface (Unix/macOS/Windows with windows-curses)

```
=== INTERACTIVE SUBTITLE ALIGNMENT ===

Use TAB to switch between source/reference
Use UP/DOWN arrows to navigate events
Press ENTER to confirm alignment
Press 'q' to quit without saving

SOURCE: movie.zh.ass                    REFERENCE: movie.en.ass
────────────────────────────────────    ────────────────────────────────────
1. 00:00:15.230 --> 00:00:18.450       1. 00:00:12.100 --> 00:00:15.200
   第一集                                  Episode One

2. 00:00:20.100 --> 00:00:23.200       2. 00:00:16.000 --> 00:00:19.100
   很久很久以前...                         A long time ago...

3. 00:00:25.000 --> 00:00:28.000       3. 00:00:20.500 --> 00:00:23.500
   在一个遥远的星系                        In a galaxy far away

Source: 1/150 | Reference: 1/145
```

### Navigation Controls

- **TAB**: Switch focus between source and reference columns
- **↑/↓**: Navigate through subtitle events
- **ENTER**: Confirm current selection as alignment points
- **Q**: Quit without saving changes

### Console Fallback Interface

If curses is unavailable, a simple text interface is provided:

```
=== INTERACTIVE SUBTITLE ALIGNMENT ===
Select alignment points for source and reference subtitles

SOURCE: movie.zh.ass
────────────────────────────────────────────────────────────
1. [00:00:15.230 --> 00:00:18.450]
   第一集
2. [00:00:20.100 --> 00:00:23.200]
   很久很久以前...

REFERENCE: movie.en.ass
────────────────────────────────────────────────────────────
1. [00:00:12.100 --> 00:00:15.200]
   Episode One
2. [00:00:16.000 --> 00:00:19.100]
   A long time ago...

Enter source event number to align (or 'q' to quit): 2
Enter reference event number to align to: 2
```

---

## 🔧 Command Line Options

### Required Arguments

| Option | Description | Example |
|--------|-------------|---------|
| `--src-ext` | Source subtitle extension to realign | `.zh.ass`, `.chs.srt` |
| `--ref-ext` | Reference subtitle extension | `.en.ass`, `.eng.srt` |

### Optional Arguments

| Option | Description | Default |
|--------|-------------|---------|
| `--folder` | Directory to scan for subtitle pairs | Current directory |
| `--interactive`, `-i` | Enable interactive alignment mode | False |
| `--output-suffix` | Suffix to add to output files | None (overwrites) |
| `--no-backup` | Skip creating backups | False (creates backups) |
| `--debug` | Enable debug logging | False |

---

## 🔄 Processing Workflow

### 1. **Discovery Phase**
- Scans specified folder for files matching `--src-ext`
- Finds corresponding reference files with `--ref-ext`
- Reports number of pairs found

### 2. **Loading Phase**
- Detects and uses appropriate file encoding
- Parses subtitle events with timing and text
- Validates file structure and content

### 3. **Alignment Phase**

#### Automatic Mode (Default)
- Finds earliest event in both files
- Calculates time shift: `shift_ms = ref_earliest - src_earliest`
- Applies shift to all source events

#### Interactive Mode
- Presents visual interface for browsing events
- User selects specific alignment points
- Removes events before alignment points
- Calculates and applies time shift

### 4. **Output Phase**
- Creates backup if enabled (default)
- Writes aligned subtitles with preserved formatting
- Reports success/failure for each pair

---

## 📁 File Structure

### Backup Organization
```
your-video-folder/
├── subtitle_backups/              # Auto-created backup directory
│   ├── movie.zh_20231215_143022.ass
│   ├── movie.zh_20231215_152455.ass
│   └── episode01.chs_20231215_160133.srt
├── movie.zh.ass                   # Original/updated subtitle
├── movie.en.ass                   # Reference subtitle
└── realign_subtitles_enhanced.py  # The script
```

### Output with Suffix
```
your-video-folder/
├── movie.zh.ass                   # Original (unchanged)
├── movie.zh.aligned.ass           # Aligned version
└── movie.en.ass                   # Reference
```

---

## 🛠️ Advanced Usage

### Custom Time Adjustments

To add additional offset after alignment, modify the script:

```python
# In align_subtitles method, after calculating shift_ms:
shift_ms += 1000  # Add 1 second forward
# or
shift_ms -= 500   # Subtract 0.5 seconds
```

### Filtering Events

To ignore certain subtitle events during alignment:

```python
# In parse methods, add filtering logic:
if "♪" in event.text:  # Skip music symbols
    continue
```

### Different Alignment Strategies

The script uses "earliest-to-earliest" alignment by default. For other strategies:

```python
# Align by first dialogue (skip signs/credits)
def get_first_dialogue_event(events):
    for event in events:
        if not event.text.startswith("[") and len(event.text) > 10:
            return event
    return events[0]  # Fallback
```

---

## 🐛 Troubleshooting

### Common Issues

1. **"No matching subtitle pairs found"**
   - Check file extensions match exactly (case-sensitive on Unix)
   - Ensure base filenames are identical
   - Verify files exist in the specified folder

2. **Encoding Errors**
   - Script auto-detects common encodings
   - For unusual encodings, convert files to UTF-8 first
   - Check debug output for specific encoding issues

3. **Interactive Mode Not Working**
   - Install `windows-curses` on Windows: `pip install windows-curses`
   - Falls back to console mode automatically
   - Use `--debug` to see why curses failed

4. **ASS Timing Format Issues**
   - Script handles both `H:MM:SS.cc` (centiseconds) and `H:MM:SS.mmm` (milliseconds)
   - Malformed timestamps are logged with line numbers
   - Original file structure is preserved

### Debug Mode

Enable comprehensive logging to diagnose issues:

```bash
python realign_subtitles_enhanced.py --src-ext .srt --ref-ext .ass --debug
```

Debug output includes:
- File encoding detection results
- Detailed parsing information
- Event-by-event processing logs
- Full error stack traces
