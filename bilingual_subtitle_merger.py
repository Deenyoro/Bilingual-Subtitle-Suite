#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import codecs
import glob
import tempfile
import shutil
import sys
import logging
from pathlib import Path
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("subtitle_merger")

def parse_srt(file_path):
    """Parse an SRT file into a list of subtitle events."""
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'gbk', 'big5', 'shift-jis']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                data = f.read()
            break
        except Exception:
            if encoding == encodings[-1]:
                logger.error(f"Failed to read {file_path} with any encoding")
                return []
            continue

    blocks = re.split(r'\r?\n\r?\n', data.strip())
    events = []
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        # If block starts with index number, skip that line
        if re.match(r'^\d+$', lines[0]):
            lines = lines[1:]
        if not lines:
            continue

        # Parse "HH:MM:SS,mmm --> HH:MM:SS,mmm"
        time_line = lines[0]
        match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', time_line)
        if not match:
            continue
        start_str, end_str = match.groups()
        start_str = start_str.replace(',', '.')
        end_str   = end_str.replace(',', '.')

        # Convert times to total seconds
        h1, m1, s1 = start_str.split(':')
        s1, ms1 = s1.split('.')
        h2, m2, s2 = end_str.split(':')
        s2, ms2 = s2.split('.')
        start = int(h1)*3600 + int(m1)*60 + int(s1) + float(ms1)/1000.0
        end   = int(h2)*3600 + int(m2)*60 + int(s2) + float(ms2)/1000.0

        # Remainder is the subtitle text
        text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        events.append({"start": start, "end": end, "text": text})
    return events

def parse_ass(file_path):
    """
    Parse an ASS file into events and extract style and script info sections.
    Returns: (events, styles, script_info)
    """
    events = []
    styles = []
    script_info = []
    format_fields = []
    in_styles = in_events = False

    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'gbk', 'big5', 'shift-jis']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                lines = f.readlines()
            break
        except Exception as e:
            if encoding == encodings[-1]:
                logger.error(f"Failed to read {file_path} with any encoding: {e}")
                return [], [], []
            continue

    for line in lines:
        line = line.rstrip('\r\n')

        if line.strip().lower().startswith("[script info]"):
            in_styles = in_events = False
            script_info.append(line)
            continue
        if line.strip().lower().startswith("[v4+ styles]"):
            in_styles = True
            in_events = False
            styles = []
            script_info.append(line)
            continue
        if line.strip().lower().startswith("[events]"):
            in_events = True
            in_styles = False
            events = []
            continue

        if in_styles:
            # Collect style lines
            styles.append(line)
            continue

        if in_events:
            if line.strip().lower().startswith("format:"):
                format_fields = [f.strip().lower() for f in line.split(":",1)[1].split(",")]
                continue

            if line.strip().lower().startswith("dialogue:"):
                content = line.split(":", 1)[1]
                if format_fields:
                    parts = content.split(",", len(format_fields)-1)
                else:
                    parts = content.split(",", 9)
                if len(parts) < 10:
                    continue

                # find indices for Start, End, Text
                if format_fields:
                    try:
                        start_idx = format_fields.index("start")
                        end_idx   = format_fields.index("end")
                        text_idx  = format_fields.index("text")
                    except ValueError:
                        start_idx, end_idx, text_idx = 1, 2, len(parts)-1
                else:
                    start_idx, end_idx, text_idx = 1, 2, 9

                start_str = parts[start_idx].strip()
                end_str   = parts[end_idx].strip()

                # Convert "H:MM:SS.cc" to seconds
                try:
                    h1,m1,s1 = start_str.split(':')
                    s1, cs1 = s1.split('.')
                    h2,m2,s2 = end_str.split(':')
                    s2, cs2 = s2.split('.')
                    start = int(h1)*3600 + int(m1)*60 + int(s1) + float(cs1)/100.0
                    end   = int(h2)*3600 + int(m2)*60 + int(s2) + float(cs2)/100.0
                except:
                    continue

                text = parts[text_idx]
                text_clean = text.replace("\\N", "\n")
                events.append({
                    "start": start,
                    "end": end,
                    "text": text_clean,
                    "raw": text
                })
                continue

        # If not in styles or events, treat line as Script Info
        if not in_styles and not in_events and line:
            script_info.append(line)

    return events, styles, script_info

def merge_events_srt(chinese_events, english_events):
    """
    Merge two lists of events (Chinese, English) into SRT with improved timing:
    - Combines overlapping CN/EN segments
    - Extends display time when possible to minimize flickering
    - Keeps both languages visible for the same duration when close
    """
    # First, create all possible segment boundaries
    times = sorted({ev["start"] for ev in (chinese_events + english_events)} |
                   {ev["end"]   for ev in (chinese_events + english_events)})
    
    # Generate initial segments
    segments = []
    for i in range(len(times)-1):
        seg_start = times[i]
        seg_end = times[i+1]
        if seg_end <= seg_start:
            continue

        cn_text = en_text = None
        # Find any CN event that covers seg_start
        for ev in chinese_events:
            if ev["start"] <= seg_start < ev["end"]:
                cn_text = ev["text"]
                break
        # Find any EN event that covers seg_start
        for ev in english_events:
            if ev["start"] <= seg_start < ev["end"]:
                en_text = ev["text"]
                break

        if not cn_text and not en_text:
            continue

        if cn_text and en_text:
            merged_text = f"{cn_text}\n{en_text}"
        else:
            merged_text = cn_text if cn_text else en_text

        segments.append({
            "start": seg_start,
            "end": seg_end,
            "text": merged_text,
            "cn_text": cn_text,
            "en_text": en_text
        })
    
    # Now refine timing to reduce flickering:
    # 1. Combine identical segments
    # 2. Extend display time when possible
    
    # First pass: combine segments with identical text
    combined = []
    for seg in segments:
        if (combined and 
            seg["text"] == combined[-1]["text"] and 
            abs(seg["start"] - combined[-1]["end"]) < 0.1):  # 100ms tolerance
            combined[-1]["end"] = seg["end"]
        else:
            combined.append(seg.copy())
    
    # Second pass: look for opportunities to extend subtitle display
    # when the same language continues but the other changes
    output = []
    i = 0
    while i < len(combined):
        curr = combined[i].copy()
        
        # Look ahead for overlapping language content
        j = i + 1
        while j < len(combined):
            next_seg = combined[j]
            
            # Check if one language remains the same
            cn_same = ((curr["cn_text"] is not None and next_seg["cn_text"] is not None and 
                        curr["cn_text"] == next_seg["cn_text"]) or
                       (curr["cn_text"] is None and next_seg["cn_text"] is None))
            
            en_same = ((curr["en_text"] is not None and next_seg["en_text"] is not None and 
                        curr["en_text"] == next_seg["en_text"]) or
                       (curr["en_text"] is None and next_seg["en_text"] is None))
            
            # If both changed or both stayed the same, we can't optimize further
            if (cn_same and en_same) or (not cn_same and not en_same):
                break
                
            # If Chinese stayed the same but English changed, make a new segment with
            # the same Chinese but updated English
            if cn_same and not en_same:
                # Split the segment
                curr["end"] = next_seg["start"]
                output.append(curr)
                
                # Create a new current segment with updated text
                curr = next_seg.copy()
                i = j
                j += 1
                continue
                
            # If English stayed the same but Chinese changed, same approach
            if en_same and not cn_same:
                curr["end"] = next_seg["start"] 
                output.append(curr)
                
                curr = next_seg.copy()
                i = j
                j += 1
                continue
                
            j += 1
            
        # Add the final segment from this group
        output.append(curr)
        i += 1
    
    # Clean up the output: remove cn_text and en_text fields, keep only text for display
    for seg in output:
        seg.pop("cn_text", None)
        seg.pop("en_text", None)
        
    return output

def merge_events_ass(chinese_events, english_events,
                     chinese_styles, english_styles,
                     script_info_cn, script_info_en):
    """
    Merge events into an ASS, with two styles: top for Chinese, bottom for English.
    """
    style_name_cn = "Chinese"
    style_name_en = "English"

    # Merge [Script Info]
    script_info_out = ["[Script Info]", "; Merged bilingual subtitle"]
    base_info = (script_info_cn or []) + (script_info_en or [])
    for line in base_info:
        if line.strip().startswith(("PlayResX", "PlayResY")):
            script_info_out.append(line.strip())

    script_info_out.append("ScriptType: v4.00+")
    script_info_out.append("Collisions: Normal")
    script_info_out.append("ScaledBorderAndShadow: yes")
    script_info_out.append("")

    # Merge [V4+ Styles]
    style_lines = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,"
        " Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,"
        " Alignment, MarginL, MarginR, MarginV, Encoding"
    ]

    def parse_style_line(line):
        # e.g. "Style: Name,Arial,40,..." -> [Name, Arial, ...]
        return line.split(":",1)[1].split(",")

    # Attempt to get a base style from each track
    base_cn_style = None
    base_en_style = None

    if chinese_styles:
        for line in chinese_styles:
            if line.strip().startswith("Style:"):
                base_cn_style = parse_style_line(line)
                break
    if english_styles:
        for line in english_styles:
            if line.strip().startswith("Style:"):
                base_en_style = parse_style_line(line)
                break

    # If either is missing, use the other as fallback
    if base_cn_style is None:
        base_cn_style = base_en_style
    if base_en_style is None:
        base_en_style = base_cn_style

    # Provide a default style if everything is missing
    if base_cn_style is None:
        base_cn_style = [
            style_name_cn, "Arial", "40", "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
            "0", "0", "0", "0", "100", "100", "0", "0", "1", "2", "2", "8", "10", "10", "10", "0"
        ]
    else:
        # Adjust alignment to top-center
        base_cn_style = base_cn_style[:]
        base_cn_style[0] = style_name_cn
        if len(base_cn_style) > 18:
            base_cn_style[18] = "8"

    if base_en_style is None:
        base_en_style = [
            style_name_en, "Arial", "40", "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
            "0", "0", "0", "0", "100", "100", "0", "0", "1", "2", "2", "2", "10", "10", "10", "0"
        ]
    else:
        # Adjust alignment to bottom-center
        base_en_style = base_en_style[:]
        base_en_style[0] = style_name_en
        if len(base_en_style) > 18:
            base_en_style[18] = "2"

    style_lines.append("Style: " + ",".join(str(x) for x in base_cn_style))
    style_lines.append("Style: " + ",".join(str(x) for x in base_en_style))

    # [Events]
    event_lines = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    combined = []
    for ev in chinese_events:
        combined.append((ev["start"], ev["end"], style_name_cn, ev.get("raw", ev["text"])))
    for ev in english_events:
        combined.append((ev["start"], ev["end"], style_name_en, ev.get("raw", ev["text"])))

    combined.sort(key=lambda x: x[0])

    def to_ass_time(sec):
        total_cs = int(round(sec * 100))
        cs = total_cs % 100
        total_s = total_cs // 100
        s = total_s % 60
        m = (total_s // 60) % 60
        h = total_s // 3600
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    for (start, end, style, text) in combined:
        start_str = to_ass_time(start)
        end_str   = to_ass_time(end)
        ass_text  = text.replace("\n", "\\N")
        event_lines.append(f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{ass_text}")

    output_lines = script_info_out + style_lines + [""] + event_lines
    return "\n".join(output_lines)

def detect_forced_track(chinese_events, english_events):
    """Heuristic: if one track has <50% lines compared to the other, label it forced."""
    cn_count = len(chinese_events)
    en_count = len(english_events)
    if cn_count == 0 or en_count == 0:
        return None
    if en_count < 0.5 * cn_count:
        return "English"
    if cn_count < 0.5 * en_count:
        return "Chinese"
    return None

# --------------------------------------------------------------------------
# MULTI-CONTAINER SUBTITLE TRACK DETECTION & EXTRACTION
# --------------------------------------------------------------------------

def is_mkv(file):
    return file.lower().endswith(".mkv")

def is_avi(file):
    return file.lower().endswith(".avi")

def is_video_container(file):
    # For simplicity, treat various containers similarly
    ext = os.path.splitext(file)[1].lower()
    return ext in [".mkv", ".mp4", ".m4v", ".mov", ".avi", ".flv", ".ts", ".webm"]

def run_command(cmd, capture_output=True):
    """Run a command and return results with proper error handling"""
    try:
        if capture_output:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, 
                encoding='utf-8', 
                errors='replace'
            )
        else:
            result = subprocess.run(cmd)
        return result
    except subprocess.SubprocessError as e:
        logger.debug(f"Command failed: {' '.join(cmd)}")
        logger.debug(f"Error: {e}")
        # Create a dummy result object with error info
        class DummyResult:
            def __init__(self, error):
                self.returncode = 1
                self.stdout = ""
                self.stderr = f"Command execution failed: {error}"
        return DummyResult(str(e))

def list_tracks_mkv(mkv_file):
    """
    Parse mkvmerge --identify to list tracks.
    Returns list of dict: [{ 'track_id': '0', 'type': 'subtitles', 'lang': 'eng', 'title': '...' }, ...]
    """
    logger.info(f"Analyzing MKV tracks in: {os.path.basename(mkv_file)}")
    try:
        cmd = ["mkvmerge", "--identify-verbose", mkv_file]
        completed = run_command(cmd)
        
        if completed.returncode != 0:
            logger.warning(f"mkvmerge failed with error: {completed.stderr}")
            logger.warning("Trying FFmpeg for track detection...")
            return list_tracks_ffmpeg(mkv_file)

        tracks = []
        track_data = {}
        current_id = None
        
        for line in completed.stdout.splitlines():
            # Track ID line example: "Track ID 2: subtitles (S_TEXT/ASS)"
            track_id_match = re.search(r"Track ID (\d+): (\w+) \(([^)]+)\)", line)
            if track_id_match:
                # Save previous track if exists
                if current_id is not None and track_data:
                    tracks.append(track_data)
                
                # Start new track
                current_id = track_id_match.group(1)
                track_data = {
                    'track_id': current_id,
                    'type': track_id_match.group(2),  # "subtitles" or "video"...
                    'codec': track_id_match.group(3),  # S_TEXT/ASS, etc.
                    'lang': '',
                    'title': ''
                }
                continue
                
            # Property lines like: "|+ Language: eng"
            prop_match = re.search(r"\|\+ (\w+): (.*)", line)
            if prop_match and current_id is not None:
                prop_name = prop_match.group(1).lower()
                prop_value = prop_match.group(2)
                if prop_name == "language":
                    track_data['lang'] = prop_value.lower()
                elif prop_name == "track_name":
                    track_data['title'] = prop_value
        
        # Don't forget to add the last track
        if current_id is not None and track_data:
            tracks.append(track_data)
            
        # If no tracks found, try FFmpeg as fallback
        if not tracks:
            logger.warning("No tracks found with mkvmerge. Trying FFmpeg...")
            return list_tracks_ffmpeg(mkv_file)
            
        return tracks
    
    except Exception as e:
        logger.error(f"Error analyzing MKV tracks: {e}")
        logger.warning("Falling back to FFmpeg for track detection...")
        return list_tracks_ffmpeg(mkv_file)

def list_tracks_ffmpeg(media_file):
    """
    Use ffprobe to list subtitle streams.
    Returns a list of dict: [{ 'track_id': '0:2', 'type': 'subtitle', 'lang': 'eng', 'title': '' }, ...]
    """
    logger.info(f"Analyzing streams with FFmpeg in: {os.path.basename(media_file)}")
    
    # First try with ffprobe (more detailed JSON output)
    try:
        # Try to get JSON output from ffprobe
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", 
            "-show_streams", "-show_format", media_file
        ]
        result = run_command(cmd)
        
        if result.returncode == 0 and result.stdout:
            try:
                data = json.loads(result.stdout)
                tracks = []
                
                for i, stream in enumerate(data.get('streams', [])):
                    if stream.get('codec_type') == 'subtitle':
                        idx = f"{stream.get('index')}"
                        lang = stream.get('tags', {}).get('language', '').lower()
                        title = stream.get('tags', {}).get('title', '')
                        codec = stream.get('codec_name', '')
                        
                        tracks.append({
                            'track_id': idx,
                            'type': 'subtitles',
                            'codec': codec,
                            'lang': lang,
                            'title': title,
                            'ffmpeg_idx': f"0:{idx}"  # Store FFmpeg stream specifier
                        })
                
                if tracks:
                    return tracks
            except json.JSONDecodeError:
                logger.debug("Failed to parse ffprobe JSON output")
    except Exception as e:
        logger.debug(f"ffprobe JSON parsing failed: {e}")
    
    # Fallback to regular ffmpeg output parsing
    cmd = ["ffmpeg", "-hide_banner", "-i", media_file]
    completed = run_command(cmd)
    
    # ffmpeg often exits with code 1 when just listing streams - that's normal
    stderr_output = completed.stderr or ""

    tracks = []
    # Looking for lines like: "Stream #0:2(eng): Subtitle: subrip (default)"
    stream_regex = re.compile(r"Stream #(\d+):(\d+)(?:\((\w+)\))?: Subtitle: ([^,]+)(.*)$", re.IGNORECASE)
    
    for line in stderr_output.splitlines():
        match = stream_regex.search(line.strip())
        if match:
            file_idx = match.group(1)
            stream_idx = match.group(2)
            track_id = stream_idx  # Simplified for mkvextract compatibility
            track_lang = match.group(3) or ""
            codec_info = match.group(4) or ""
            extra_info = match.group(5) or ""
            
            # Try to extract title if present
            title = ""
            title_match = re.search(r"title\s*:\s*([^,\(]+)", extra_info, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            
            tracks.append({
                'track_id': track_id,
                'type': 'subtitles',
                'codec': codec_info,
                'lang': track_lang.lower(),
                'title': title,
                'ffmpeg_idx': f"{file_idx}:{stream_idx}"  # Store the FFmpeg stream specifier
            })
    
    return tracks

def extract_subtitle_mkv(mkv_file, track_id, out_path):
    """
    Extract a single subtitle track from MKV using mkvextract.
    The track_id should be a simple numeric index.
    """
    # Make sure the track_id is just a number (mkvextract format)
    # If it contains ":" (FFmpeg format), extract just the stream index
    track_id_numeric = track_id
    if ":" in track_id:
        track_id_numeric = track_id.split(":")[-1]
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    
    logger.info(f"Extracting MKV track #{track_id} from '{os.path.basename(mkv_file)}' to '{os.path.basename(out_path)}'...")
    
    # First, validate the track exists
    tracks = list_tracks_mkv(mkv_file)
    valid_track_ids = [t['track_id'] for t in tracks if t.get('type', '').lower() in ('subtitles', 'subtitle')]
    
    if track_id_numeric not in valid_track_ids:
        logger.warning(f"Track ID {track_id} not found in MKV file. Available subtitle tracks: {valid_track_ids}")
        # Try to find the track using FFmpeg indexing if mkvmerge failed
        for t in tracks:
            if 'ffmpeg_idx' in t and t['ffmpeg_idx'] == track_id:
                track_id_numeric = t['track_id']
                logger.info(f"Found matching track using FFmpeg index: {track_id_numeric}")
                break
        else:
            logger.warning("Track not found, will try FFmpeg extraction directly")
            return extract_subtitle_ffmpeg(mkv_file, track_id, out_path)
    
    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Use a temporary filename to handle potential encoding issues
        ext = os.path.splitext(out_path)[1].lower()
        tmp_path = os.path.join(tmp_dir, f"track_{track_id_numeric}{ext}")
        
        # Run mkvextract to extract the track
        cmd = ["mkvextract", "tracks", mkv_file, f"{track_id_numeric}:{tmp_path}"]
        result = run_command(cmd)
        
        if result.returncode != 0:
            logger.warning(f"mkvextract failed with code {result.returncode}")
            logger.debug(f"mkvextract error: {result.stderr}")
            logger.info("Trying FFmpeg extraction as fallback...")
            # Try FFmpeg extraction as fallback
            return extract_subtitle_ffmpeg(mkv_file, track_id, out_path)
        
        # Check if extraction was successful
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            # Copy from temporary path to final destination
            try:
                shutil.copy2(tmp_path, out_path)
                logger.info(f"Successfully extracted subtitle to {os.path.basename(out_path)}")
                return out_path
            except Exception as e:
                logger.error(f"Failed to copy extracted subtitle: {e}")
        else:
            logger.warning("mkvextract produced no output or empty file")
    
    # If we got here, mkvextract failed - try FFmpeg
    logger.info("Trying FFmpeg extraction as fallback...")
    return extract_subtitle_ffmpeg(mkv_file, track_id, out_path)

def extract_subtitle_ffmpeg(media_file, track_id, out_path):
    """
    Extract subtitle using FFmpeg.
    track_id can be a simple index like "2" or FFmpeg format like "0:2".
    """
    # Normalize track ID for FFmpeg mapping
    ffmpeg_track = track_id
    if ":" not in track_id:
        # Simple numeric track ID needs to be converted to FFmpeg format
        ffmpeg_track = f"0:{track_id}"
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    
    # Get the desired output format from the file extension
    base, ext = os.path.splitext(out_path)
    if not ext:
        ext = ".ass"  # Default to ASS if no extension
        out_path = base + ext
    
    logger.info(f"Extracting FFmpeg track {ffmpeg_track} from '{os.path.basename(media_file)}' to '{os.path.basename(out_path)}'...")
    
    # First verify the track exists using FFmpeg probe
    tracks = list_tracks_ffmpeg(media_file)
    valid_tracks = [t for t in tracks if t.get('type', '').lower() in ('subtitles', 'subtitle')]
    
    # Check if our track exists in any form (direct ID or ffmpeg_idx)
    track_to_use = None
    for t in valid_tracks:
        if t['track_id'] == track_id or t.get('ffmpeg_idx') == ffmpeg_track:
            track_to_use = t.get('ffmpeg_idx', ffmpeg_track)
            break
    
    if not track_to_use:
        logger.warning(f"Track {track_id} not found in {os.path.basename(media_file)}")
        logger.info("Available subtitle tracks:")
        for t in valid_tracks:
            logger.info(f"  - Track ID: {t['track_id']}, Lang: {t.get('lang', '')}, Title: {t.get('title', '')}")
        return None
    
    ffmpeg_track = track_to_use  # Use the verified FFmpeg track specifier
    
    # Try different subtitle formats based on the extension
    formats_to_try = []
    if ext.lower() == '.ass':
        formats_to_try = [('ass', '.ass'), ('ssa', '.ssa'), ('srt', '.srt')]
    elif ext.lower() == '.srt':
        formats_to_try = [('srt', '.srt'), ('ass', '.ass'), ('ssa', '.ssa')]
    else:
        formats_to_try = [(ext[1:], ext)]  # Use the specified extension
    
    # Create a temporary directory for extraction
    with tempfile.TemporaryDirectory() as tmp_dir:
        for subtitle_format, format_ext in formats_to_try:
            tmp_path = os.path.join(tmp_dir, f"subtitle{format_ext}")
            
            # Build FFmpeg command
            cmd = [
                "ffmpeg", "-y",
                "-i", media_file,
                "-map", ffmpeg_track,
                "-c:s", subtitle_format,
                tmp_path
            ]
            
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            
            # Run FFmpeg
            result = run_command(cmd)
            
            # Check if extraction succeeded
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                # Copy from temporary path to final destination
                try:
                    # If the format extension doesn't match the requested one, change the output path
                    final_out = out_path
                    if format_ext.lower() != ext.lower():
                        final_out = base + format_ext
                    
                    shutil.copy2(tmp_path, final_out)
                    logger.info(f"Successfully extracted to {os.path.basename(final_out)} using format {subtitle_format}")
                    return final_out
                except Exception as e:
                    logger.error(f"Failed to copy extracted subtitle: {e}")
                    continue
            else:
                logger.debug(f"FFmpeg format {subtitle_format} extraction failed: {result.stderr}")
        
        # If all formats failed, try a direct stream copy as a last resort
        tmp_path = os.path.join(tmp_dir, f"subtitle_copy{ext}")
        cmd = [
            "ffmpeg", "-y",
            "-i", media_file,
            "-map", ffmpeg_track,
            "-c:s", "copy",
            tmp_path
        ]
        
        logger.debug(f"Trying direct stream copy: {' '.join(cmd)}")
        result = run_command(cmd)
        
        if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            try:
                shutil.copy2(tmp_path, out_path)
                logger.info(f"Successfully extracted to {os.path.basename(out_path)} using direct stream copy")
                return out_path
            except Exception as e:
                logger.error(f"Failed to copy extracted subtitle: {e}")
        else:
            logger.debug(f"FFmpeg direct copy failed: {result.stderr}")
    
    # If all extraction attempts failed
    logger.error(f"Subtitle extraction failed for track {track_id}")
    return None

def guess_embedded_subtitle(video_file, is_chinese=False, remap_lang=None, prefer_track=None):
    """
    Identify a likely embedded subtitle track for either CN or EN.
    
    Args:
        video_file: Path to the video file
        is_chinese: True to look for Chinese tracks, False for English
        remap_lang: Language code to remap (treat this language as target language)
        prefer_track: Specific track number to use (overrides other selection logic)
    
    Returns:
        track_id in a container-appropriate format or None if none found.
    """
    if not os.path.exists(video_file):
        logger.error(f"Video file does not exist: {video_file}")
        return None
    
    # If user specified a track, use it directly
    if prefer_track is not None:
        logger.info(f"Using user-specified track: {prefer_track}")
        return prefer_track
    
    # Get all tracks from the video file
    if is_mkv(video_file):
        tracks = list_tracks_mkv(video_file)
    else:
        tracks = list_tracks_ffmpeg(video_file)
    
    # Filter for subtitle tracks only
    sub_tracks = [t for t in tracks if t.get('type', '').lower() in ('subtitles', 'subtitle')]
    
    if not sub_tracks:
        logger.warning(f"No subtitle tracks found in {os.path.basename(video_file)}")
        return None
        
    # Define language codes to look for
    if is_chinese:
        possible_codes = ["chi", "zho", "chs", "cht", "zh", "chinese"] 
        if remap_lang:
            possible_codes.append(remap_lang.lower())
    else:
        possible_codes = ["eng", "en", "english"]
        if remap_lang:
            possible_codes.append(remap_lang.lower())
    
    # Find tracks that match by language or title
    matched = []
    
    for t in sub_tracks:
        text = f"{t.get('lang', '')} {t.get('title', '')}".lower()
        if any(code in text for code in possible_codes):
            matched.append(t)

    if len(matched) == 1:
        logger.info(f"Found {'Chinese' if is_chinese else 'English'} subtitle track: {matched[0].get('title', '')} (lang: {matched[0].get('lang', '')})")
        return matched[0]['track_id']
    elif len(matched) > 1:
        # List all matches with detailed info
        logger.info(f"Multiple candidate {'Chinese' if is_chinese else 'English'} tracks in {os.path.basename(video_file)}:")
        for i, track in enumerate(matched, start=1):
            logger.info(f"{i}) track_id={track['track_id']}, lang={track.get('lang', '')}, title={track.get('title', '')}")
        
        # Default to the first track rather than requiring interactive input
        logger.info(f"Automatically selecting track #{matched[0]['track_id']}")
        return matched[0]['track_id']
    else:
        # No direct matches - list all available subtitle tracks
        logger.info(f"No direct match found for {'Chinese' if is_chinese else 'English'} in {os.path.basename(video_file)}.")
        logger.info("Available subtitle tracks:")
        for i, track in enumerate(sub_tracks, start=1):
            logger.info(f"{i}) track_id={track['track_id']}, lang={track.get('lang', '')}, title={track.get('title', '')}")
        
        # Return None to indicate no suitable track was found
        return None

def extract_subtitle_track(video_file, track_id, out_path):
    """
    Extract the given track from video_file to out_path.
    For MKV files, first tries mkvextract then falls back to FFmpeg.
    For other formats, uses FFmpeg directly.
    """
    if not track_id:
        logger.error("No track ID provided for extraction")
        return None
        
    if is_mkv(video_file):
        result = extract_subtitle_mkv(video_file, track_id, out_path)
        return result
    else:
        return extract_subtitle_ffmpeg(video_file, track_id, out_path)

# --------------------------------------------------------------------------
# Searching for external subtitles
# --------------------------------------------------------------------------

def find_external_sub(video_path, is_chinese=False):
    """
    Look for an external subtitle file with the same base name, or variants.
    If is_chinese=True => checks for .zh.* etc
    If is_chinese=False => checks for .en.* etc
    """
    video_dir = os.path.dirname(video_path) or '.'
    video_name = os.path.basename(video_path)
    base_name = os.path.splitext(video_name)[0]
    
    logger.info(f"Looking for external {'Chinese' if is_chinese else 'English'} subtitle for: {video_name}")
    
    # Define patterns to search for
    if is_chinese:
        patterns = [
            f"{base_name}.zh.*", f"{base_name}.chi.*", f"{base_name}.chs.*", 
            f"{base_name}.cht.*", f"{base_name}.cn.*", f"{base_name}.*chinese.*",
            f"{base_name}.*zh.*", f"{base_name}.*chi.*"
        ]
    else:
        patterns = [
            f"{base_name}.en.*", f"{base_name}.eng.*", f"{base_name}.*english.*",
            f"{base_name}.*en.*"
        ]
    
    # Add exact extension patterns
    if is_chinese:
        exact_patterns = [f"{base_name}.zh.srt", f"{base_name}.zh.ass", f"{base_name}.chi.srt", f"{base_name}.chi.ass"]
    else:
        exact_patterns = [f"{base_name}.en.srt", f"{base_name}.en.ass", f"{base_name}.eng.srt", f"{base_name}.eng.ass"]
    
    # Search in the video directory
    all_files = os.listdir(video_dir)
    
    # First check for exact patterns
    for pattern in exact_patterns:
        pattern_file = os.path.basename(pattern)
        if pattern_file in all_files:
            sub_path = os.path.join(video_dir, pattern_file)
            logger.info(f"Found exact match: {pattern_file}")
            return sub_path
    
    # If exact patterns not found, try glob patterns
    for pattern in patterns:
        full_pattern = os.path.join(video_dir, pattern)
        matches = glob.glob(full_pattern)
        if matches:
            # Sort by path length to get closest name match
            matches.sort(key=len)
            logger.info(f"Found pattern match: {os.path.basename(matches[0])}")
            return matches[0]
    
    # Try fallback to same name but .srt or .ass extension
    sub_extensions = ['.srt', '.ass', '.ssa', '.vtt']
    for ext in sub_extensions:
        potential_sub = os.path.join(video_dir, base_name + ext)
        if os.path.exists(potential_sub):
            # If we found same-named subtitle, check content for language clues
            with open(potential_sub, 'rb') as f:
                try:
                    sample = f.read(4096).decode('utf-8', errors='replace')
                    # Extremely basic language detection
                    has_chinese = any(ord(c) > 0x4E00 and ord(c) < 0x9FFF for c in sample)
                    if is_chinese and has_chinese:
                        logger.info(f"Found same-named Chinese subtitle: {base_name}{ext}")
                        return potential_sub
                    elif not is_chinese and not has_chinese:
                        logger.info(f"Found same-named English subtitle: {base_name}{ext}")
                        return potential_sub
                except:
                    pass
    
    logger.info(f"No external {'Chinese' if is_chinese else 'English'} subtitle found for {video_name}")
    return None

# --------------------------------------------------------------------------
# Processing a single video
# --------------------------------------------------------------------------

def process_one_video(video_path, eng_sub=None, chi_sub=None,
                     out_format="srt", out_file=None,
                     remap_eng=None, remap_chi=None,
                     eng_track=None, chi_track=None,
                     prefer_external=False, prefer_embedded=False):
    """
    Merge English/Chinese subs into one track. If eng_sub or chi_sub is None,
    the script attempts to find or extract them from video_path or external files.
    """
    logger.info(f"Processing video: {os.path.basename(video_path)}")
    
    # Sanity check - both preferences can't be true
    if prefer_external and prefer_embedded:
        logger.warning("Both prefer_external and prefer_embedded can't be true. Using default behavior.")
        prefer_external = prefer_embedded = False
    
    # 1. Process English subtitles based on preferences
    if not eng_sub:
        external_eng = find_external_sub(video_path, is_chinese=False) if not prefer_embedded else None
        
        if external_eng and not prefer_embedded:
            eng_sub = external_eng
        elif not external_eng or prefer_embedded:
            # Try embedded if no external or if embedded is preferred
            track_id = guess_embedded_subtitle(video_path, is_chinese=False, 
                                              remap_lang=remap_eng, prefer_track=eng_track)
            if track_id:
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".eng_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extracted = extract_subtitle_track(video_path, track_id, tmp_path)
                eng_sub = extracted
                
        # If prefer_external and we found both, override with external
        if prefer_external and external_eng and eng_sub and eng_sub != external_eng:
            logger.info("Preferring external English subtitle over embedded.")
            eng_sub = external_eng

    # 2. Process Chinese subtitles based on preferences
    if not chi_sub:
        external_chi = find_external_sub(video_path, is_chinese=True) if not prefer_embedded else None
        
        if external_chi and not prefer_embedded:
            chi_sub = external_chi
        elif not external_chi or prefer_embedded:
            # Try embedded if no external or if embedded is preferred
            track_id = guess_embedded_subtitle(video_path, is_chinese=True, 
                                              remap_lang=remap_chi, prefer_track=chi_track)
            if track_id:
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".chi_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extracted = extract_subtitle_track(video_path, track_id, tmp_path)
                chi_sub = extracted
                
        # If prefer_external and we found both, override with external
        if prefer_external and external_chi and chi_sub and chi_sub != external_chi:
            logger.info("Preferring external Chinese subtitle over embedded.")
            chi_sub = external_chi

    # 3. If we still have no ENG or CHI => skip
    if not eng_sub and not chi_sub:
        logger.warning(f"No Chinese or English subtitles found for '{os.path.basename(video_path)}'. Skipping.")
        return
    elif not eng_sub:
        logger.warning(f"No English subtitles found for '{os.path.basename(video_path)}'. Will only use Chinese.")
    elif not chi_sub:
        logger.warning(f"No Chinese subtitles found for '{os.path.basename(video_path)}'. Will only use English.")

    # 4. Parse what we have
    eng_events, eng_styles, script_info_eng = [], [], []
    chi_events, chi_styles, script_info_chi = [], [], []

    def is_srt(path):
        return path and path.lower().endswith(".srt")
    def is_ass(path):
        return path and (path.lower().endswith(".ass") or path.lower().endswith(".ssa"))

    if eng_sub and os.path.isfile(eng_sub):
        logger.info(f"Parsing English subtitle: {os.path.basename(eng_sub)}")
        if is_srt(eng_sub):
            eng_events = parse_srt(eng_sub)
        elif is_ass(eng_sub):
            eev, esty, sinfo = parse_ass(eng_sub)
            eng_events, eng_styles, script_info_eng = eev, esty, sinfo
        logger.info(f"Found {len(eng_events)} English subtitle events")

    if chi_sub and os.path.isfile(chi_sub):
        logger.info(f"Parsing Chinese subtitle: {os.path.basename(chi_sub)}")
        if is_srt(chi_sub):
            chi_events = parse_srt(chi_sub)
        elif is_ass(chi_sub):
            cev, csty, sinfo = parse_ass(chi_sub)
            chi_events, chi_styles, script_info_chi = cev, csty, sinfo
        logger.info(f"Found {len(chi_events)} Chinese subtitle events")

    # 5. Warn if forced track detected
    forced = detect_forced_track(chi_events, eng_events)
    if forced:
        logger.warning(f"Warning: The {forced} track is significantly shorter. Possibly forced or partial subs.")

    # 6. Determine output name if not provided
    if not out_file:
        base, _ = os.path.splitext(video_path)
        out_file = f"{base}.zh-en.{out_format}"  # <--- changed to .zh-en.

    # 7. Merge
    if out_format == "srt":
        merged = merge_events_srt(chi_events, eng_events)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(codecs.BOM_UTF8.decode('utf-8'))  # BOM for compatibility
            for i, ev in enumerate(merged, start=1):
                start_h = int(ev['start'] // 3600)
                start_m = int((ev['start'] % 3600) // 60)
                start_s = int(ev['start'] % 60)
                start_ms = int((ev['start'] * 1000) % 1000)
                end_h = int(ev['end'] // 3600)
                end_m = int((ev['end'] % 3600) // 60)
                end_s = int(ev['end'] % 60)
                end_ms = int((ev['end'] * 1000) % 1000)
                start_str = f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d}"
                end_str   = f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}"
                text_block = ev['text']
                f.write(f"{i}\n{start_str} --> {end_str}\n{text_block}\n\n")
        logger.info(f"Created bilingual SRT: {out_file}")
    else:
        merged_ass = merge_events_ass(chi_events, eng_events,
                                      chi_styles, eng_styles,
                                      script_info_chi, script_info_eng)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(codecs.BOM_UTF8.decode('utf-8'))
            f.write(merged_ass)
        logger.info(f"Created bilingual ASS: {out_file}")

# --------------------------------------------------------------------------
# Main CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Merge English & Chinese subtitles into a single track. "
                    "Supports MKV via mkvextract and MP4/AVI/etc via ffmpeg for embedded tracks."
    )
    parser.add_argument("-e","--english", help="Path to external English subtitle (.srt/.ass)")
    parser.add_argument("-c","--chinese", help="Path to external Chinese subtitle (.srt/.ass)")
    parser.add_argument("-o","--output",  help="Output file path. Default: <video>.zh-en.srt/.ass")
    parser.add_argument("-f","--format",  choices=["srt","ass"], default="srt",
                        help="Output format (srt or ass). Default = srt.")
    parser.add_argument("-v","--video",   help="Video file to search for embedded subs or match external subs.")
    parser.add_argument("--bulk", action="store_true",
                        help="Process all media files in the given folder (or current dir) in bulk.")
    
    # New features
    parser.add_argument("--remap-eng", help="Treat tracks with this language code as English (e.g., 'jpn')")
    parser.add_argument("--remap-chi", help="Treat tracks with this language code as Chinese (e.g., 'jpn')")
    parser.add_argument("--eng-track", help="Use a specific track number for English subtitles")
    parser.add_argument("--chi-track", help="Use a specific track number for Chinese subtitles")
    parser.add_argument("--prefer-external", action="store_true", 
                        help="Prefer external subtitles over embedded ones")
    parser.add_argument("--prefer-embedded", action="store_true",
                        help="Prefer embedded subtitles over external ones")
    
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    
    # Parse arguments
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    out_format = args.format

    # If bulk mode, handle all media in folder
    if args.bulk:
        path = args.video or "."
        if os.path.isdir(path):
            # Find video files
            exts = ["*.mkv","*.mp4","*.m4v","*.mov","*.avi","*.flv","*.ts", "*.webm"]
            files = []
            for ext in exts:
                files.extend(glob.glob(os.path.join(path, ext)))
        elif os.path.isfile(path) and is_video_container(path):
            files = [path]
        else:
            logger.error(f"Path not found or not a video file: {path}")
            sys.exit(1)

        if not files:
            logger.warning("No media files found for bulk operation.")
            sys.exit(0)

        for media_file in sorted(files):
            print(f"\n=== Processing: {os.path.basename(media_file)} ===")
            try:
                process_one_video(
                    media_file,
                    eng_sub=args.english,
                    chi_sub=args.chinese,
                    out_format=out_format,
                    out_file=args.output,
                    remap_eng=args.remap_eng,
                    remap_chi=args.remap_chi,
                    eng_track=args.eng_track,
                    chi_track=args.chi_track,
                    prefer_external=args.prefer_external,
                    prefer_embedded=args.prefer_embedded
                )
            except Exception as e:
                logger.error(f"Error processing '{media_file}': {e}")
                continue
        return

    # Non-bulk mode
    if args.video:
        # Validate video file exists
        if not os.path.isfile(args.video):
            logger.error(f"Video file not found: {args.video}")
            sys.exit(1)
            
        # Merge with possible embedded detection
        try:
            process_one_video(
                args.video,
                eng_sub=args.english,
                chi_sub=args.chinese,
                out_format=out_format,
                out_file=args.output,
                remap_eng=args.remap_eng,
                remap_chi=args.remap_chi,
                eng_track=args.eng_track,
                chi_track=args.chi_track,
                prefer_external=args.prefer_external,
                prefer_embedded=args.prefer_embedded
            )
        except Exception as e:
            logger.error(f"Error processing '{args.video}': {e}")
            sys.exit(1)
    else:
        # If only external subs given
        if not args.english and not args.chinese:
            logger.error("ERROR: Provide at least one of --english or --chinese, or use --video, or use --bulk.")
            sys.exit(1)

        # Merge external files directly
        eng_file = args.english
        chi_file = args.chinese

        # Parse them
        def is_srt(file):
            return file and file.lower().endswith(".srt")
        def is_ass(file):
            return file and (file.lower().endswith(".ass") or file.lower().endswith(".ssa"))

        eng_events = []
        chi_events = []
        eng_styles = []
        chi_styles = []
        script_info_eng = []
        script_info_chi = []

        try:
            if eng_file:
                if not os.path.isfile(eng_file):
                    logger.error(f"English subtitle file not found: {eng_file}")
                    sys.exit(1)
                    
                if is_srt(eng_file):
                    eng_events = parse_srt(eng_file)
                elif is_ass(eng_file):
                    eev, esty, sinfo = parse_ass(eng_file)
                    eng_events, eng_styles, script_info_eng = eev, esty, sinfo
                else:
                    logger.error(f"Unsupported English subtitle format: {eng_file}")
                    sys.exit(1)

            if chi_file:
                if not os.path.isfile(chi_file):
                    logger.error(f"Chinese subtitle file not found: {chi_file}")
                    sys.exit(1)
                    
                if is_srt(chi_file):
                    chi_events = parse_srt(chi_file)
                elif is_ass(chi_file):
                    cev, csty, sinfo = parse_ass(chi_file)
                    chi_events, chi_styles, script_info_chi = cev, csty, sinfo
                else:
                    logger.error(f"Unsupported Chinese subtitle format: {chi_file}")
                    sys.exit(1)
        except Exception as e:
            logger.error(f"Error parsing subtitle files: {e}")
            sys.exit(1)

        forced = detect_forced_track(chi_events, eng_events)
        if forced:
            logger.warning(f"Warning: {forced} track is shorter. Possibly forced or partial.")

        out_file = args.output
        if not out_file:
            out_file = f"merged.{out_format}"
            
        try:
            if out_format == "srt":
                merged = merge_events_srt(chi_events, eng_events)
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(codecs.BOM_UTF8.decode('utf-8'))
                    for i, ev in enumerate(merged, start=1):
                        start_h = int(ev['start'] // 3600)
                        start_m = int((ev['start'] % 3600) // 60)
                        start_s = int(ev['start'] % 60)
                        start_ms = int((ev['start'] * 1000) % 1000)
                        end_h = int(ev['end'] // 3600)
                        end_m = int((ev['end'] % 3600) // 60)
                        end_s = int(ev['end'] % 60)
                        end_ms = int((ev['end'] * 1000) % 1000)
                        start_str = f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d}"
                        end_str   = f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}"
                        text_block = ev['text']
                        f.write(f"{i}\n{start_str} --> {end_str}\n{text_block}\n\n")
                logger.info(f"Created merged SRT: {out_file}")
            else:
                merged_ass = merge_events_ass(chi_events, eng_events,
                                            chi_styles, eng_styles,
                                            script_info_chi, script_info_eng)
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(codecs.BOM_UTF8.decode('utf-8'))
                    f.write(merged_ass)
                logger.info(f"Created merged ASS: {out_file}")
        except Exception as e:
            logger.error(f"Error creating output file: {e}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
