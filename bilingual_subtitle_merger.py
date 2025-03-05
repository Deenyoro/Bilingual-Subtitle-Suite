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

def parse_srt(file_path):
    """Parse an SRT file into a list of subtitle events."""
    import re
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        data = f.read()
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

    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        lines = f.readlines()

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
    Merge two lists of events (Chinese, English) into SRT:
      1) Build a sorted timeline of all start/end points
      2) For each segment, combine CN/EN lines if they overlap
      3) Output blocks with text "Chinese\nEnglish"
    """
    merged = []
    times = sorted({ev["start"] for ev in (chinese_events + english_events)} |
                   {ev["end"]   for ev in (chinese_events + english_events)})

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

        merged.append({
            "start": seg_start,
            "end": seg_end,
            "text": merged_text
        })

    # Combine consecutive identical text blocks to reduce flicker
    compact = []
    for ev in merged:
        if compact and (ev["text"] == compact[-1]["text"]
                        and abs(ev["start"] - compact[-1]["end"]) < 1e-6):
            compact[-1]["end"] = ev["end"]
        else:
            compact.append(ev)
    return compact

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

def is_mp4(file):
    # For simplicity, treat .mp4/.m4v/.mov similarly
    ext = os.path.splitext(file)[1].lower()
    return ext in [".mp4", ".m4v", ".mov", ".avi", ".flv", ".ts"]

def list_tracks_mkv(mkv_file):
    """
    Parse mkvmerge --identify to list tracks.
    Returns list of dict: [{ 'track_id': '0', 'type': 'subtitles', 'lang': 'eng', 'title': '...' }, ...]
    """
    cmd = ["mkvmerge", "--identify", mkv_file]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Failed to identify tracks in {mkv_file}.\n{completed.stderr}")

    tracks = []
    for line in completed.stdout.splitlines():
        # Example: "Track ID 1: subtitles (S_TEXT/ASS) [language:eng, track_name:Signs]"
        m = re.search(r"Track ID (\d+): (\w+) \(([^)]+)\).*?\[language:(\w+)(?:,\s*track_name:(.*?)\])?", line)
        if m:
            tid = m.group(1)
            ttype = m.group(2)  # "subtitles" or "video"...
            lang = m.group(4) or ""
            tname = m.group(5) or ""
            tracks.append({
                'track_id': tid,
                'type': ttype,
                'lang': lang.lower(),
                'title': tname.strip()
            })
    return tracks

def list_tracks_ffmpeg(media_file):
    """
    Use ffmpeg -i <media_file> to list subtitle streams.
    Returns a list of dict: [{ 'track_id': '0:2', 'type': 'subtitle', 'lang': 'eng', 'title': '' }, ...]
    We'll store track_id as e.g. "0:2" to indicate the stream index for ffmpeg extraction.
    """
    cmd = ["ffmpeg", "-hide_banner", "-i", media_file]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0 and completed.returncode != 1:
        # ffmpeg often returns 1 if it can't transcode. We only need stream info
        raise RuntimeError(f"Failed to analyze {media_file} with ffmpeg.\n{completed.stderr}")

    lines = completed.stderr.splitlines()
    # Looking for lines like: "Stream #0:2(eng): Subtitle: subrip (default)"
    # or "Stream #0:3(chi): Subtitle: ass..."
    tracks = []
    # We'll parse "Stream #0:X(...)"
    stream_regex = re.compile(r"^(\s*)Stream #(\d+:\d+)(?:\((\w+)\))?: Subtitle: ([^,]+)(.*)$", re.IGNORECASE)
    for line in lines:
        match = stream_regex.match(line.strip())
        if match:
            track_id_ff = match.group(2)  # "0:2"
            track_lang  = match.group(3) or ""
            track_type  = "subtitles"  # We only parse subtitle lines
            # The "rest" might show 'default' or 'forced'
            tracks.append({
                'track_id': track_id_ff,
                'type': track_type,
                'lang': track_lang.lower(),
                'title': ""  # ffmpeg doesn't easily expose track_name
            })
    return tracks

def extract_subtitle_mkv(mkv_file, track_id, out_path):
    """
    Extract a single subtitle track from MKV using mkvextract.
    track_id is a string index, e.g. '0'.
    """
    print(f"Extracting MKV track #{track_id} from '{mkv_file}' to '{out_path}'...")
    cmd = ["mkvextract", "tracks", mkv_file, f"{track_id}:{out_path}"]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"mkvextract failed.\n{completed.stderr}")

def extract_subtitle_ffmpeg(media_file, track_id, out_path):
    """
    Extract a single subtitle track from non-MKV using ffmpeg.
    track_id is like "0:2".
    We'll extract as .ass so we preserve formatting if possible.
    (Then we'll parse it in Python.)
    """
    print(f"Extracting FFmpeg track {track_id} from '{media_file}' to '{out_path}'...")
    # We'll try to force an ASS output to parse consistently
    # If you prefer SRT for intermediate, just switch -c:s ass -> -c:s srt
    cmd = [
        "ffmpeg", "-y", "-i", media_file,
        "-map", f"{track_id}",  # e.g. "0:2"
        "-c:s", "ass",
        out_path
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg extraction failed.\n{completed.stderr}")

def guess_embedded_subtitle(video_file, is_chinese=False):
    """
    Identify a likely embedded subtitle track for either CN or EN.
    Return track_id in a container-appropriate format:
      - for MKV: "0", "1", ...
      - for FFmpeg: "0:2", etc.
    or None if none found.
    This will prompt if multiple matches are found.
    """
    if is_mkv(video_file):
        tracks = list_tracks_mkv(video_file)
        sub_tracks = [t for t in tracks if t['type'].lower().startswith("sub")]
        if not sub_tracks:
            return None
        # For Chinese, we look for chi/zho/chs/cht/...
        # For English, we look for eng
        possible_codes = ["chi","zho","chs","cht","chinese"] if is_chinese else ["eng","english"]
        matched = []
        for t in sub_tracks:
            text = f"{t['lang']} {t['title']}".lower()
            if any(code in text for code in possible_codes):
                matched.append(t)

        if len(matched) == 1:
            return matched[0]['track_id']
        elif len(matched) > 1:
            # prompt
            print(f"Multiple candidate {'Chinese' if is_chinese else 'English'} tracks in {video_file}:")
            for i, track in enumerate(matched, start=1):
                print(f"{i}) track_id={track['track_id']}, lang={track['lang']}, title={track['title']}")
            choice = input("Pick track number (or Enter to skip): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(matched):
                return matched[int(choice)-1]['track_id']
            return None
        else:
            # no direct matches, prompt for any sub track
            if sub_tracks:
                print(f"No direct match found for {'Chinese' if is_chinese else 'English'} in {video_file}.")
                for i, track in enumerate(sub_tracks, start=1):
                    print(f"{i}) track_id={track['track_id']}, lang={track['lang']}, title={track['title']}")
                choice = input("Pick track number (or Enter to skip): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(sub_tracks):
                    return sub_tracks[int(choice)-1]['track_id']
            return None

    else:
        # Non-MKV => use ffmpeg
        tracks = list_tracks_ffmpeg(video_file)
        sub_tracks = [t for t in tracks if t['type'].lower().startswith("sub")]
        if not sub_tracks:
            return None

        possible_codes = ["chi","zho","chs","cht","chinese"] if is_chinese else ["eng","english"]
        matched = []
        for t in sub_tracks:
            text = f"{t['lang']} {t['title']}".lower()
            if any(code in text for code in possible_codes):
                matched.append(t)

        if len(matched) == 1:
            return matched[0]['track_id']
        elif len(matched) > 1:
            print(f"Multiple candidate {'Chinese' if is_chinese else 'English'} tracks in {video_file}:")
            for i, track in enumerate(matched, start=1):
                print(f"{i}) track_id={track['track_id']}, lang={track['lang']}")
            choice = input("Pick track number (or Enter to skip): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(matched):
                return matched[int(choice)-1]['track_id']
            return None
        else:
            # no direct matches => prompt
            print(f"No direct match found for {'Chinese' if is_chinese else 'English'} in {video_file}.")
            for i, track in enumerate(sub_tracks, start=1):
                print(f"{i}) track_id={track['track_id']}, lang={track['lang']}")
            choice = input("Pick track number (or Enter to skip): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(sub_tracks):
                return sub_tracks[int(choice)-1]['track_id']
            return None

def extract_subtitle_track(video_file, track_id, out_path):
    """
    Extract the given track from video_file to out_path, depending on container.
    For MKV => mkvextract
    For others => ffmpeg
    """
    if is_mkv(video_file):
        extract_subtitle_mkv(video_file, track_id, out_path)
    else:
        extract_subtitle_ffmpeg(video_file, track_id, out_path)

# --------------------------------------------------------------------------
# Searching for external subtitles
# --------------------------------------------------------------------------

def find_external_sub(video_path, is_chinese=False):
    """
    Look for an external .en.srt/.zh.srt or .ass with the same base name, or variants.
    If is_chinese=True => checks for .zh.* etc
    If is_chinese=False => checks for .en.* etc
    Return the first match or None.
    """
    folder = os.path.dirname(video_path)
    base, _ = os.path.splitext(video_path)
    if is_chinese:
        patterns = [
            f"{base}.zh.srt", f"{base}.zh.ass",
            f"{base}.ch.srt", f"{base}.ch.ass",
            f"{base}.zh-*.*", f"{base}.cn.*", f"{base}.*zh.*"
        ]
    else:
        patterns = [
            f"{base}.en.srt", f"{base}.en.ass",
            f"{base}.eng.srt", f"{base}.eng.ass",
            f"{base}.*en.*"
        ]

    for pat in patterns:
        for candidate in glob.glob(pat):
            if os.path.isfile(candidate):
                return candidate
    return None

# --------------------------------------------------------------------------
# Processing a single video
# --------------------------------------------------------------------------

def process_one_video(video_path, eng_sub=None, chi_sub=None,
                      out_format="srt", out_file=None):
    """
    Merge English/Chinese subs into one track. If eng_sub or chi_sub is None,
    the script attempts to find or extract them from video_path or external files.
    """
    # 1. If no ENG sub specified, search external or embedded
    if not eng_sub:
        maybe = find_external_sub(video_path, is_chinese=False)
        if maybe:
            eng_sub = maybe
        else:
            # try embedded
            track_id = guess_embedded_subtitle(video_path, is_chinese=False)
            if track_id:
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".eng_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extract_subtitle_track(video_path, track_id, tmp_path)
                eng_sub = tmp_path

    # 2. If no CHI sub specified, search external or embedded
    if not chi_sub:
        maybe = find_external_sub(video_path, is_chinese=True)
        if maybe:
            chi_sub = maybe
        else:
            # try embedded
            track_id = guess_embedded_subtitle(video_path, is_chinese=True)
            if track_id:
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".chi_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extract_subtitle_track(video_path, track_id, tmp_path)
                chi_sub = tmp_path

    # 3. If we still have no ENG or CHI => skip
    if not eng_sub and not chi_sub:
        print(f"WARNING: No Chinese or English subtitles found for '{video_path}'. Skipping.")
        return
    elif not eng_sub:
        print(f"WARNING: No English subtitles found for '{video_path}'. Will only use Chinese.")
    elif not chi_sub:
        print(f"WARNING: No Chinese subtitles found for '{video_path}'. Will only use English.")

    # 4. Parse what we have
    eng_events, eng_styles, script_info_eng = [], [], []
    chi_events, chi_styles, script_info_chi = [], [], []

    def is_srt(path):
        return path.lower().endswith(".srt")
    def is_ass(path):
        return path.lower().endswith(".ass")

    if eng_sub and os.path.isfile(eng_sub):
        if is_srt(eng_sub):
            eng_events = parse_srt(eng_sub)
        elif is_ass(eng_sub):
            eev, esty, sinfo = parse_ass(eng_sub)
            eng_events, eng_styles, script_info_eng = eev, esty, sinfo

    if chi_sub and os.path.isfile(chi_sub):
        if is_srt(chi_sub):
            chi_events = parse_srt(chi_sub)
        elif is_ass(chi_sub):
            cev, csty, sinfo = parse_ass(chi_sub)
            chi_events, chi_styles, script_info_chi = cev, csty, sinfo

    # 5. Warn if forced track detected
    forced = detect_forced_track(chi_events, eng_events)
    if forced:
        print(f"Warning: The {forced} track is significantly shorter. Possibly forced or partial subs.")

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
        print(f"Created bilingual SRT: {out_file}")
    else:
        merged_ass = merge_events_ass(chi_events, eng_events,
                                      chi_styles, eng_styles,
                                      script_info_chi, script_info_eng)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(codecs.BOM_UTF8.decode('utf-8'))
            f.write(merged_ass)
        print(f"Created bilingual ASS: {out_file}")

# --------------------------------------------------------------------------
# Main CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Merge English & Chinese subtitles into a single track. "
                    "Supports MKV via mkvextract and MP4/etc via ffmpeg for embedded tracks."
    )
    parser.add_argument("-e","--english", help="Path to external English subtitle (.srt/.ass)")
    parser.add_argument("-c","--chinese", help="Path to external Chinese subtitle (.srt/.ass)")
    parser.add_argument("-o","--output",  help="Output file path. Default: <video>.zh-en.srt/.ass")
    parser.add_argument("-f","--format",  choices=["srt","ass"], default="srt",
                        help="Output format (srt or ass). Default = srt.")
    parser.add_argument("-v","--video",   help="Video file to search for embedded subs or match external subs.")
    parser.add_argument("--bulk", action="store_true",
                        help="Process all media files in the given folder (or current dir) in bulk.")
    args = parser.parse_args()

    out_format = args.format

    # If bulk mode, handle all media in folder
    if args.bulk:
        path = args.video or "."
        if os.path.isdir(path):
            # Find .mkv, .mp4, etc.
            # We'll just search for common containers
            exts = ["*.mkv","*.mp4","*.m4v","*.mov","*.avi","*.flv","*.ts"]
            files = []
            for x in exts:
                files.extend(glob.glob(os.path.join(path, x)))
        elif os.path.isfile(path):
            files = [path]
        else:
            files = []

        if not files:
            print("No media files found for bulk operation.")
            sys.exit(0)

        for media_file in sorted(files):
            print(f"\n=== Processing: {media_file} ===")
            process_one_video(media_file,
                              eng_sub=args.english,
                              chi_sub=args.chinese,
                              out_format=out_format,
                              out_file=args.output)
        return

    # Non-bulk mode
    if args.video:
        # Merge with possible embedded detection
        process_one_video(args.video,
                          eng_sub=args.english,
                          chi_sub=args.chinese,
                          out_format=out_format,
                          out_file=args.output)
    else:
        # If only external subs given
        if not args.english or not args.chinese:
            print("ERROR: Provide both --english and --chinese, or use --video, or use --bulk.")
            sys.exit(1)

        # Merge external files directly
        eng_file = args.english
        chi_file = args.chinese

        # Parse them
        def is_srt(file):
            return file.lower().endswith(".srt")
        def is_ass(file):
            return file.lower().endswith(".ass")

        eng_events = chi_events = []
        eng_styles = chi_styles = []
        script_info_eng = script_info_chi = []

        if is_srt(eng_file):
            eng_events = parse_srt(eng_file)
        elif is_ass(eng_file):
            eev, esty, sinfo = parse_ass(eng_file)
            eng_events, eng_styles, script_info_eng = eev, esty, sinfo
        else:
            print(f"Unsupported English subtitle format: {eng_file}")
            sys.exit(1)

        if is_srt(chi_file):
            chi_events = parse_srt(chi_file)
        elif is_ass(chi_file):
            cev, csty, sinfo = parse_ass(chi_file)
            chi_events, chi_styles, script_info_chi = cev, csty, sinfo
        else:
            print(f"Unsupported Chinese subtitle format: {chi_file}")
            sys.exit(1)

        forced = detect_forced_track(chi_events, eng_events)
        if forced:
            print(f"Warning: {forced} track is shorter. Possibly forced or partial.")

        out_file = args.output
        if not out_file:
            out_file = f"merged.{out_format}"
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
            print(f"Created merged SRT: {out_file}")
        else:
            merged_ass = merge_events_ass(chi_events, eng_events,
                                          chi_styles, eng_styles,
                                          script_info_chi, script_info_eng)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(codecs.BOM_UTF8.decode('utf-8'))
                f.write(merged_ass)
            print(f"Created merged ASS: {out_file}")

if __name__ == "__main__":
    main()
