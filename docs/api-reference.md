# API Reference

Developer reference for extending and integrating with the Bilingual Subtitle Suite.

## Table of Contents
- [Core Modules](#core-modules)
- [Processor Classes](#processor-classes)
- [Utility Functions](#utility-functions)
- [Configuration System](#configuration-system)
- [Extension Points](#extension-points)
- [Integration Examples](#integration-examples)

## Core Modules

### subtitle_formats.py

**Purpose**: Handle parsing and writing of different subtitle formats.

#### SubtitleParser Class

```python
from core.subtitle_formats import SubtitleParser

parser = SubtitleParser()

# Parse subtitle file
entries = parser.parse_file("subtitle.srt")

# Parse from string
entries = parser.parse_string(content, format="srt")

# Write subtitle file
parser.write_file(entries, "output.srt", format="srt")
```

**Methods**:
- `parse_file(file_path: Path, format: str = None) -> List[SubtitleEntry]`
- `parse_string(content: str, format: str) -> List[SubtitleEntry]`
- `write_file(entries: List[SubtitleEntry], file_path: Path, format: str)`
- `detect_format(file_path: Path) -> str`

#### SubtitleEntry Class

```python
from core.subtitle_formats import SubtitleEntry

entry = SubtitleEntry(
    index=1,
    start_time=1.5,
    end_time=3.2,
    text="Hello world",
    style_info={}
)

# Properties
entry.duration  # 1.7 seconds
entry.is_empty  # False
entry.text_length  # 11 characters
```

### video_containers.py

**Purpose**: Extract and analyze subtitle tracks from video containers.

#### VideoProcessor Class

```python
from core.video_containers import VideoProcessor

processor = VideoProcessor()

# Get subtitle tracks
tracks = processor.get_subtitle_tracks("movie.mkv")

# Extract specific track
success = processor.extract_subtitle_track(
    video_path="movie.mkv",
    track_index=2,
    output_path="subtitle.srt"
)

# Get track information
info = processor.get_track_info("movie.mkv", track_index=2)
```

### track_analyzer.py

**Purpose**: Intelligent analysis and selection of subtitle tracks.

#### TrackAnalyzer Class

```python
from core.track_analyzer import TrackAnalyzer

analyzer = TrackAnalyzer()

# Analyze all tracks
analysis = analyzer.analyze_tracks("movie.mkv")

# Get best tracks for languages
best_english = analyzer.get_best_track(analysis, language="eng")
best_chinese = analyzer.get_best_track(analysis, language="chi")

# Score individual track
score = analyzer.score_track(track_info)
```

### language_detection.py

**Purpose**: Detect and classify subtitle languages.

#### LanguageDetector Class

```python
from core.language_detection import LanguageDetector

detector = LanguageDetector()

# Detect language from text
language = detector.detect_language("Hello world")  # Returns "en"
language = detector.detect_language("你好世界")      # Returns "zh"

# Detect from file
language = detector.detect_file_language("subtitle.srt")

# Get language info
info = detector.get_language_info("zh")
# Returns: {"code": "zh", "name": "Chinese", "family": "sino-tibetan"}
```

## Processor Classes

### BilingualMerger

**Purpose**: Core bilingual subtitle merging functionality.

```python
from processors.merger import BilingualMerger

merger = BilingualMerger(
    enable_enhanced_alignment=True,
    alignment_threshold=0.8,
    use_translation=False
)

# Merge from video file
success = merger.merge_from_video(
    video_path="movie.mkv",
    output_path="bilingual.srt",
    chinese_track=None,  # Auto-detect
    english_track=None,  # Auto-detect
    output_format="srt"
)

# Merge subtitle files
success = merger.merge_subtitle_files(
    chinese_path="chinese.srt",
    english_path="english.srt",
    output_path="merged.srt",
    output_format="srt"
)
```

**Configuration Options**:
```python
merger = BilingualMerger(
    enable_enhanced_alignment=True,
    enable_manual_alignment=False,
    alignment_threshold=0.8,
    time_threshold=0.5,
    similarity_threshold=0.7,
    use_translation=False,
    translation_api_key=None,
    sync_strategy="auto",  # auto, first-line, scan, translation, manual
    gap_threshold=0.1,
    max_line_length=80
)
```

### EncodingConverter

**Purpose**: Convert subtitle file encodings.

```python
from processors.converter import EncodingConverter

converter = EncodingConverter()

# Convert single file
success = converter.convert_file(
    file_path="chinese.srt",
    target_encoding="utf-8",
    keep_backup=True,
    force_conversion=False
)

# Batch convert
results = converter.convert_directory(
    directory="subtitles/",
    target_encoding="utf-8",
    recursive=True,
    parallel=True,
    keep_backup=True
)
```

### SubtitleRealigner

**Purpose**: Realign subtitle timing.

```python
from processors.realigner import SubtitleRealigner

realigner = SubtitleRealigner()

# Basic realignment
success = realigner.align_subtitles(
    source_path="source.srt",
    reference_path="reference.srt",
    source_align_idx=5,
    ref_align_idx=3,
    create_backup=True
)

# Auto-alignment with similarity
success = realigner.auto_align_subtitles(
    source_path="source.srt",
    reference_path="reference.srt",
    similarity_threshold=0.8
)
```

### BatchProcessor

**Purpose**: Handle batch operations efficiently.

```python
from processors.batch_processor import BatchProcessor

processor = BatchProcessor()

# Batch merge
results = processor.batch_merge_videos(
    directory="Season 01/",
    recursive=False,
    auto_confirm=True,
    enhanced_alignment=True
)

# Batch convert
results = processor.batch_convert_encodings(
    directory="subtitles/",
    target_encoding="utf-8",
    parallel=True,
    max_workers=4
)
```

## Utility Functions

### file_operations.py

```python
from utils.file_operations import FileHandler

# Find subtitle files
subtitle_files = FileHandler.find_subtitle_files(
    directory="media/",
    recursive=True,
    extensions=[".srt", ".ass", ".vtt"]
)

# Create backup
backup_path = FileHandler.create_backup("original.srt")

# Safe file operations
success = FileHandler.safe_write("output.srt", content)
content = FileHandler.safe_read("input.srt")
```

### backup_manager.py

```python
from utils.backup_manager import BackupManager

manager = BackupManager()

# Create backup
backup_path = manager.create_backup("file.srt")

# List backups
backups = manager.list_backups("file.srt")

# Restore backup
success = manager.restore_backup(backup_path)

# Cleanup old backups
cleaned = manager.cleanup_old_backups(
    directory=".",
    older_than_days=30
)
```

### logging_config.py

```python
from utils.logging_config import setup_logging

# Setup logging
logger = setup_logging(
    level="INFO",
    use_colors=True,
    log_file="app.log"
)

# Use logger
logger.info("Processing started")
logger.warning("Potential issue detected")
logger.error("Processing failed")
```

## Configuration System

### Environment Variables

```python
import os

# API keys
api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")

# Timeouts
ffmpeg_timeout = int(os.getenv("FFMPEG_TIMEOUT", "900"))

# Debug settings
debug_level = os.getenv("SUBTITLE_DEBUG_LEVEL", "INFO")
```

### Configuration File

**Location**: `~/.subtitle-processor.json`

```python
from utils.config import ConfigManager

config = ConfigManager()

# Load configuration
settings = config.load_config()

# Get specific setting
threshold = config.get("alignment.default_threshold", 0.8)

# Update setting
config.set("alignment.default_threshold", 0.9)
config.save_config()
```

**Configuration Schema**:
```json
{
  "alignment": {
    "default_threshold": 0.8,
    "time_threshold": 0.5,
    "similarity_threshold": 0.7,
    "enable_translation": false
  },
  "translation": {
    "api_key": null,
    "cache_enabled": true,
    "max_requests_per_alignment": 10,
    "timeout": 30
  },
  "output": {
    "default_format": "srt",
    "backup_enabled": true,
    "naming_convention": "auto"
  },
  "processing": {
    "parallel_enabled": true,
    "max_workers": 4,
    "ffmpeg_timeout": 900,
    "chunk_size": 1000
  }
}
```

## Extension Points

### Custom Subtitle Formats

```python
from core.subtitle_formats import SubtitleParser

class CustomFormatParser(SubtitleParser):
    def parse_custom_format(self, content: str) -> List[SubtitleEntry]:
        # Implement custom parsing logic
        entries = []
        # ... parsing code ...
        return entries
    
    def write_custom_format(self, entries: List[SubtitleEntry]) -> str:
        # Implement custom writing logic
        content = ""
        # ... writing code ...
        return content

# Register custom format
parser = SubtitleParser()
parser.register_format("custom", CustomFormatParser())
```

### Custom Alignment Strategies

```python
from core.alignment import AlignmentStrategy

class CustomAlignmentStrategy(AlignmentStrategy):
    def find_anchor_points(self, track1, track2):
        # Implement custom anchor detection
        anchors = []
        # ... detection logic ...
        return anchors
    
    def calculate_confidence(self, anchor1, anchor2):
        # Implement custom confidence calculation
        confidence = 0.0
        # ... calculation logic ...
        return confidence

# Register strategy
from processors.merger import BilingualMerger
merger = BilingualMerger()
merger.register_strategy("custom", CustomAlignmentStrategy())
```

### Custom Translation Services

```python
from core.translation_service import TranslationService

class CustomTranslationService(TranslationService):
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        # Implement custom translation logic
        translated = ""
        # ... translation code ...
        return translated
    
    def detect_language(self, text: str) -> str:
        # Implement language detection
        language = ""
        # ... detection code ...
        return language

# Use custom service
from processors.merger import BilingualMerger
merger = BilingualMerger(translation_service=CustomTranslationService())
```

## Integration Examples

### Web API Integration

```python
from flask import Flask, request, jsonify
from processors.merger import BilingualMerger

app = Flask(__name__)
merger = BilingualMerger()

@app.route('/merge', methods=['POST'])
def merge_subtitles():
    data = request.json
    
    success = merger.merge_from_video(
        video_path=data['video_path'],
        output_path=data['output_path'],
        enhanced_alignment=data.get('enhanced_alignment', True)
    )
    
    return jsonify({'success': success})

if __name__ == '__main__':
    app.run(debug=True)
```

### Batch Processing Script

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
from processors.batch_processor import BatchProcessor

def main():
    if len(sys.argv) != 2:
        print("Usage: batch_process.py <directory>")
        sys.exit(1)
    
    directory = Path(sys.argv[1])
    processor = BatchProcessor()
    
    results = processor.batch_merge_videos(
        directory=directory,
        recursive=True,
        enhanced_alignment=True,
        auto_confirm=True
    )
    
    print(f"Processed {results['total']} files")
    print(f"Success: {results['success']}")
    print(f"Failed: {results['failed']}")

if __name__ == '__main__':
    main()
```

### Plugin System

```python
from abc import ABC, abstractmethod

class SubtitlePlugin(ABC):
    @abstractmethod
    def process(self, entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        pass

class UppercasePlugin(SubtitlePlugin):
    def process(self, entries):
        for entry in entries:
            entry.text = entry.text.upper()
        return entries

# Plugin manager
class PluginManager:
    def __init__(self):
        self.plugins = []
    
    def register_plugin(self, plugin: SubtitlePlugin):
        self.plugins.append(plugin)
    
    def apply_plugins(self, entries):
        for plugin in self.plugins:
            entries = plugin.process(entries)
        return entries

# Usage
manager = PluginManager()
manager.register_plugin(UppercasePlugin())
processed_entries = manager.apply_plugins(subtitle_entries)
```

### Custom CLI Commands

```python
from ui.cli import CLIHandler

class CustomCLIHandler(CLIHandler):
    def add_custom_parsers(self, subparsers):
        # Add custom command
        custom_parser = subparsers.add_parser('custom-command')
        custom_parser.add_argument('input', help='Input file')
        custom_parser.add_argument('--option', help='Custom option')
    
    def handle_custom_command(self, args):
        # Implement custom command logic
        print(f"Processing {args.input} with option {args.option}")
        return 0

# Extend CLI
cli = CustomCLIHandler()
cli.add_custom_parsers(cli.parser.subparsers)
```
