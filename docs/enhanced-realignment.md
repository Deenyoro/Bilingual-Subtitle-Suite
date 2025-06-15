# Enhanced Realignment for Mixed Track Scenarios

## Overview

The Enhanced Realignment feature in Bilingual Subtitle Suite addresses a specific scenario where external subtitle files (like Chinese .srt files) have completely different timing compared to properly-synchronized embedded subtitle tracks from video containers.

## Problem Scenario

Consider this common situation:
- **Video file**: `Made in Abyss S02E01.mkv` with embedded English subtitles properly synchronized to the video
- **External file**: `Made in Abyss S02E01.zh.srt` with Chinese subtitles that start at completely different times (e.g., 10+ seconds offset)

Without enhanced realignment, the merger would either:
1. Preserve timing exactly (resulting in mismatched bilingual subtitles)
2. Apply standard alignment (potentially disrupting the properly-timed embedded track)

## Enhanced Realignment Solution

### Core Principles

1. **Embedded Track Protection**: Embedded tracks are treated as the timing reference and their timing is NEVER modified
2. **External Track Realignment**: Only external tracks with major timing misalignment are modified
3. **User Confirmation**: Major timing shifts require explicit user confirmation
4. **Semantic Anchoring**: Uses content similarity to find the correct alignment point

### Workflow

#### 1. Scenario Detection
- Detects mixed track types (embedded + external)
- Identifies major timing misalignment (>5 seconds difference)
- Only activates when `--enable-mixed-realignment` flag is used

#### 2. Alignment Point Detection
- Searches for semantically matching subtitle lines between tracks
- Uses content similarity scoring (with optional translation assistance)
- Identifies the first reliable anchor point for synchronization

#### 3. Realignment Process
- Calculates time offset needed to align anchor points
- Applies global time shift to ALL events in the external track
- Removes subtitle entries that occur before the alignment anchor (pre-anchor deletion)
- Preserves embedded track timing completely unchanged

#### 4. Post-Alignment Merging
- Merges the now-synchronized tracks using timing preservation methods
- Embedded track remains the timing reference throughout

## Usage

### Command Line

```bash
# Enable enhanced realignment for mixed tracks
biss merge video.mkv --enable-mixed-realignment

# With translation assistance for better anchor detection
biss merge video.mkv --enable-mixed-realignment --use-translation --translation-api-key YOUR_KEY

# Batch processing with enhanced realignment
biss batch-merge /path/to/videos --enable-mixed-realignment
```

### Interactive Mode

The feature is also available in interactive mode with clear prompts and confirmations.

## Example Scenario

### Input Files
- `Made in Abyss S02E01.mkv` - Video with embedded English subtitles
- `Made in Abyss S02E01.zh.srt` - External Chinese subtitles with timing offset

### Detection Output
```
🚨 MAJOR TIMING MISALIGNMENT DETECTED (>5s difference)
🚨 Mixed embedded + external tracks with significant timing offset
🔧 Enhanced mixed track realignment is ENABLED

🔍 SEMANTIC ANCHOR SEARCH: Finding alignment point using content similarity
🎯 Translation-assisted anchor found: embedded[0] ↔ external[2] (confidence: 0.85, offset: -10.0s)

🚨 MAJOR TIMING REALIGNMENT REQUIRED
================================================================================
Mixed track scenario detected:
  📺 Embedded en track: Properly synchronized with video
  📄 External zh track: Major timing offset detected

Proposed realignment:
  🎯 Anchor point found with 10.0 second offset
  🔒 Embedded track timing will be preserved (reference)
  🔄 External track will be shifted by -10.000 seconds
  🗑️  2 entries before anchor will be removed

⚠️  This will modify the external track timing to match the embedded track.
⚠️  The embedded track timing will remain unchanged.
⚠️  This is recommended for external files with incorrect timing.

Proceed with realignment? (y/n):
```

### Result
- External Chinese track is shifted to align with embedded English track
- Pre-anchor Chinese entries are removed
- Final bilingual subtitle maintains perfect video synchronization

## Technical Details

### Timing Preservation Validation

The system validates that:
- At least 70% of embedded track timing boundaries are preserved in mixed scenarios
- Reference track timing is never modified during realignment
- Anti-jitter logic is limited to 100ms tolerance for identical segments

### Anchor Point Detection

1. **Translation-Assisted** (if enabled):
   - Translates external track content to match embedded track language
   - Uses fuzzy matching to find semantically similar lines
   - Provides higher confidence scores

2. **Similarity-Only** (fallback):
   - Uses multiple similarity algorithms (sequence, Jaccard, cosine, edit distance)
   - Weighted scoring system for confidence calculation
   - Minimum confidence threshold of 0.5

### Safety Features

- **User Confirmation**: Required for all major timing shifts
- **Backup Creation**: Automatic backup of original files
- **Validation Logging**: Detailed logging of all timing decisions
- **Fallback Behavior**: Falls back to timing preservation if anchor detection fails

## Limitations

1. **Requires Semantic Similarity**: Anchor detection depends on finding matching content between tracks
2. **Single Anchor Point**: Uses first reliable anchor point (may not be optimal for all scenarios)
3. **Pre-Anchor Deletion**: Content before anchor point is lost from external track
4. **Manual Confirmation**: Requires user interaction (can be automated with `--auto-confirm`)

## Best Practices

1. **Enable Translation**: Use `--use-translation` for better anchor detection across languages
2. **Review Anchor Points**: Check the proposed anchor points before confirming
3. **Test with Samples**: Try on a few files before batch processing
4. **Backup Important Files**: Always keep backups of original subtitle files

## Troubleshooting

### No Anchor Point Found
- Try enabling translation assistance
- Check if subtitle content actually matches between tracks
- Verify that tracks contain substantial overlapping content

### Poor Alignment Results
- Review the detected anchor point for accuracy
- Consider manual alignment for complex cases
- Check if pre-anchor deletion removed important content

### Performance Issues
- Translation-assisted detection may be slower
- Consider processing smaller batches for large datasets
- Use `--auto-confirm` for fully automated processing

## Related Features

- [Timing Preservation](timing-preservation.md) - Core timing preservation principles
- [Translation Service](translation-service.md) - Google Cloud Translation integration
- [Batch Processing](batch-processing.md) - Automated processing workflows
- [Interactive Mode](interactive-guide.md) - Menu-driven interface
