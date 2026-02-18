# Enhanced Realignment for Mixed Track Scenarios

## Overview

The Enhanced Realignment feature in Bilingual Subtitle Suite addresses a specific scenario where external subtitle files (like Chinese .srt files) have completely different timing compared to properly-synchronized embedded subtitle tracks from video containers.

## Problem Scenario

Consider this common situation with anime episodes:
- **Video file**: `Made in Abyss S02E01.mkv` with embedded English subtitles properly synchronized to the video
- **External file**: `Made in Abyss S02E01.zh.srt` with Chinese subtitles that have major timing differences (50+ seconds offset)

**Real-World Example**:
- Embedded English subtitle starts at 00:00:11,730: "This compass..."
- External Chinese subtitle starts at 00:01:08,497: "在這個羅盤..." (same content, 56.8 second offset!)

Without enhanced realignment, the merger would either:
1. Preserve timing exactly (resulting in completely mismatched bilingual subtitles)
2. Apply standard alignment (potentially disrupting the properly-timed embedded track)
3. Fail to find any alignment points due to the large timing difference

## Enhanced Realignment Solution

### Core Principles

1. **Embedded Track Protection**: Embedded tracks are treated as the timing reference and their timing is NEVER modified
2. **External Track Realignment**: Only external tracks with major timing misalignment are modified
3. **User Confirmation**: Major timing shifts require explicit user confirmation
4. **Semantic Anchoring**: Uses content similarity to find the correct alignment point

### Workflow

#### 1. Scenario Detection
- Detects mixed track types (embedded + external)
- Identifies major timing misalignment (>5 seconds difference, handles 50+ second offsets)
- Only activates when `--enable-mixed-realignment` flag is used or auto-detected in interactive mode

#### 2. Enhanced Alignment Point Detection
- **Cross-Language Content Matching**: Uses translation-assisted semantic matching for Chinese-English pairs
- **Expanded Search Scope**: Searches up to 40 events from each track to handle large offsets
- **Multiple Similarity Metrics**: Combines sequence matching, Jaccard similarity, cosine similarity, and edit distance
- **Lowered Confidence Thresholds**: Accepts matches as low as 0.15 confidence for large offset scenarios
- **Fallback Strategies**: Multiple detection strategies with automatic fallback

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

# Large timing offset handling (50+ second differences)
biss merge video.mkv --auto-align --use-translation --alignment-threshold 0.3

# Combined approach for maximum success rate
biss merge video.mkv --auto-align --use-translation \
  --alignment-threshold 0.3 --enable-mixed-realignment

# Real-world anime example (Made in Abyss style)
biss merge "Made in Abyss S02E01.mkv" --auto-align \
  --use-translation --alignment-threshold 0.3 --enable-mixed-realignment

# Batch processing with enhanced alignment
biss batch-merge "Season 02" --auto-align --use-translation \
  --alignment-threshold 0.3 --auto-confirm
```

### Interactive Mode

The feature is also available in interactive mode with clear prompts and confirmations.

## Example Scenario

### Input Files
- `Made in Abyss S02E01.mkv` - Video with embedded English subtitles
- `Made in Abyss S02E01.zh.srt` - External Chinese subtitles with timing offset

### Detection Output (Real Made in Abyss Example)
```
🚨 MAJOR TIMING MISALIGNMENT DETECTED (>5s difference)
🚨 Mixed embedded + external tracks with significant timing offset
🔧 Enhanced mixed track realignment is ENABLED

🔍 ENHANCED SEMANTIC ALIGNMENT: Searching for content-based anchor point
🔍 Translation-assisted anchor detection for major timing offsets
✅ TRANSLATION-ASSISTED ANCHOR FOUND:
   Embedded[4]: [11.730s] This compass...
   External[3]: [68.497s] 在這個羅盤…
   Cross-language similarity: 0.45, Time offset: -56.767s

🚨 MAJOR TIMING REALIGNMENT REQUIRED
================================================================================
Mixed track scenario detected:
  📺 Embedded en track: Properly synchronized with video (reference)
  📄 External zh track: Major timing offset detected (-56.767s)

Proposed realignment:
  🎯 Semantic anchor found: "This compass..." ↔ "在這個羅盤…"
  🔒 Embedded track timing will be preserved (reference)
  🔄 External track will be shifted by -56.767 seconds
  🗑️  3 entries before anchor will be removed (pre-anchor deletion)

⚠️  This will modify the external track timing to match the embedded track.
⚠️  The embedded track timing will remain unchanged.
⚠️  This is recommended for external files with incorrect timing.

Proceed with realignment? (y/n): y

✅ Realignment completed successfully
📊 Timing preservation: 100% of embedded track boundaries preserved
📄 Output: Made in Abyss S02E01.zh-en.srt (proper bilingual format)
```

### Result
- External Chinese track is shifted by -56.767 seconds to align with embedded English track
- 3 pre-anchor Chinese entries are removed (content before the alignment point)
- Final bilingual subtitle maintains perfect video synchronization
- Each entry contains exactly one Chinese line followed by one English line
- Zero text duplication in output file
- Embedded track timing preserved exactly for proper media player auto-detection

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
