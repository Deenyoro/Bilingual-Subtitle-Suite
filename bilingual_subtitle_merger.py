#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import codecs
import glob
import tempfile
import shutil

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
        # If block starts with index number, skip it
        if re.match(r'^\d+$', lines[0]):
            lines = lines[1:]
        if not lines:
            continue
        # Parse timing line
        time_line = lines[0]
        match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', time_line)
        if not match:
            continue
        start_str, end_str = match.groups()
        start_str = start_str.replace(',', '.')
        end_str   = end_str.replace(',', '.')
        # Convert time to total seconds
        h1, m1, s1 = start_str.split(':')
        s1, ms1 = s1.split('.')
        h2, m2, s2 = end_str.split(':')
        s2, ms2 = s2.split('.')
        start = int(h1)*3600 + int(m1)*60 + int(s1) + int(ms1)/1000.0
        end   = int(h2)*3600 + int(m2)*60 + int(s2) + int(ms2)/1000.0
        # Remaining lines are text
        text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        events.append({"start": start, "end": end, "text": text})
    return events

def parse_ass(file_path):
    """Parse an ASS file into events, and extract style and script info sections."""
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
                    # default fields
                    parts = content.split(",", 9)
                if len(parts) < 10:
                    continue
                # find indices
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
                # Convert times
                h1,m1,s1 = start_str.split(':')
                s1, cs1 = s1.split('.')
                h2,m2,s2 = end_str.split(':')
                s2, cs2 = s2.split('.')
                start = int(h1)*3600 + int(m1)*60 + int(s1) + int(cs1)/100.0
                end   = int(h2)*3600 + int(m2)*60 + int(s2) + int(cs2)/100.0

                text = parts[text_idx]
                text_clean = text.replace("\\N", "\n")
                events.append({"start": start, "end": end, "text": text_clean, "raw": text})
                continue

        # If not in styles or events, treat line as Script Info line
        if not in_styles and not in_events and line:
            script_info.append(line)

    return events, styles, script_info

def merge_events_srt(chinese_events, english_events):
    """Merge two lists of events into one (SRT style)."""
    merged = []
    times = sorted({ev["start"] for ev in (chinese_events+english_events)} |
                   {ev["end"] for ev in (chinese_events+english_events)})

    for i in range(len(times)-1):
        seg_start = times[i]
        seg_end   = times[i+1]
        if seg_end <= seg_start:
            continue
        cn_text = en_text = None
        for ev in chinese_events:
            if ev["start"] <= seg_start < ev["end"]:
                cn_text = ev["text"]
        for ev in english_events:
            if ev["start"] <= seg_start < ev["end"]:
                en_text = ev["text"]
        if cn_text is None and en_text is None:
            continue
        if cn_text is not None and en_text is not None:
            merged_text = f"{cn_text}\n{en_text}"
        else:
            merged_text = cn_text if cn_text is not None else en_text
        merged.append({"start": seg_start, "end": seg_end, "text": merged_text})

    # Combine consecutive identical text blocks
    compact = []
    for ev in merged:
        if compact and ev["text"] == compact[-1]["text"] and abs(ev["start"] - compact[-1]["end"]) < 1e-6:
            compact[-1]["end"] = ev["end"]
        else:
            compact.append(ev)
    return compact

def merge_events_ass(chinese_events, english_events, chinese_styles, english_styles, script_info_cn, script_info_en):
    """Merge events into an ASS, assigning top style to CN, bottom style to EN."""
    style_name_cn = "Chinese"
    style_name_en = "English"

    # Merge script info
    script_info_out = ["[Script Info]", "; Merged bilingual subtitle"]
    base_info = (script_info_cn or []) + (script_info_en or [])
    for line in base_info:
        if line.strip().startswith(("PlayResX", "PlayResY")):
            script_info_out.append(line.strip())
    script_info_out.append("ScriptType: v4.00+")
    script_info_out.append("Collisions: Normal")
    script_info_out.append("ScaledBorderAndShadow: yes")
    script_info_out.append("")

    # Merge styles
    style_lines = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,"
        " Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    ]
    def parse_style_line(line):
        return line.split(":",1)[1].split(",")

    base_cn_style = None
    base_en_style = None

    # Grab first style line from each if present
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

    if base_cn_style is None:
        base_cn_style = base_en_style
    if base_en_style is None:
        base_en_style = base_cn_style

    # Provide a default if everything is None
    if base_cn_style is None:
        base_cn_style = [
            style_name_cn, "Arial", "40", "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
            "0","0","0","0","100","100","0","0","1","2","2","8","10","10","10","0"
        ]
    else:
        base_cn_style = base_cn_style[:]
        if len(base_cn_style) > 18:
            base_cn_style[18] = "8"  # top-center alignment
        base_cn_style[0] = style_name_cn

    if base_en_style is None:
        base_en_style = [
            style_name_en, "Arial", "40", "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
            "0","0","0","0","100","100","0","0","1","2","2","2","10","10","10","0"
        ]
    else:
        base_en_style = base_en_style[:]
        if len(base_en_style) > 18:
            base_en_style[18] = "2"  # bottom-center alignment
        base_en_style[0] = style_name_en

    style_lines.append("Style: " + ",".join(str(x) for x in base_cn_style))
    style_lines.append("Style: " + ",".join(str(x) for x in base_en_style))

    # Prepare events
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

    def to_ass_time(t):
        total_cs = int(round(t * 100))
        cs = total_cs % 100
        total_s = total_cs // 100
        secs = total_s % 60
        mins = (total_s // 60) % 60
        hrs  = total_s // 3600
        return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"

    for start, end, style, text in combined:
        start_str = to_ass_time(start)
        end_str   = to_ass_time(end)
        ass_text = text.replace("\n", "\\N")
        event_lines.append(f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{ass_text}")

    output_lines = script_info_out + style_lines + [""] + event_lines
    return "\n".join(output_lines)

def detect_forced_track(chinese_events, english_events):
    """Simple heuristic to detect if one track might be forced (fewer lines)."""
    cn_count = len(chinese_events)
    en_count = len(english_events)
    if cn_count == 0 or en_count == 0:
        return None
    if en_count < 0.5 * cn_count:
        return "English"
    if cn_count < 0.5 * en_count:
        return "Chinese"
    return None

def extract_subtitle_track(mkv_file, track_id, out_path):
    """
    Extracts a single subtitle track from an MKV using mkvextract.
    Raises an exception if mkvextract fails.
    """
    print(f"Extracting track #{track_id} from '{mkv_file}' to '{out_path}'...")
    cmd = [
        "mkvextract", "tracks",
        mkv_file,
        f"{track_id}:{out_path}"
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Failed to extract track #{track_id} from {mkv_file}.\n{completed.stderr}")

def list_mkv_tracks(mkv_file):
    """
    Returns a list of (track_id, track_type, language, track_name) from mkvmerge --identify.
    Example output line:
      Track ID 0: subtitles (S_TEXT/ASS) [language:eng]
    """
    cmd = ["mkvmerge", "--identify", mkv_file]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Failed to identify tracks in {mkv_file}.\n{completed.stderr}")

    results = []
    for line in completed.stdout.splitlines():
        # e.g. "Track ID 1: video (V_MPEG4/ISO/AVC) [language:eng]"
        m = re.search(r"Track ID (\d+): (\w+) \(([^)]+)\).*?language:\s?(\w+)", line)
        if m:
            track_id = m.group(1)
            track_type = m.group(2)
            track_codec = m.group(3)
            language = m.group(4)
            # see if there's a track name too
            # mkvmerge can have lines like: 
            #   "Track ID 4: subtitles (S_TEXT/ASS) [language:eng, track_name:Signs [Coalgirls]]"
            name_match = re.search(r"track_name:\s?([^,]+)", line)
            track_name = name_match.group(1) if name_match else ""
            results.append((track_id, track_type, language, track_name))
    return results

def guess_track_id_for_language(mkv_file, desired_language="eng"):
    """
    Attempt to find a subtitle track with the specified language code using mkvmerge --identify.
    Return the track_id (str) if found, otherwise None.
    If multiple matches, returns the first.
    """
    tracks = list_mkv_tracks(mkv_file)
    # Filter subtitles only
    sub_tracks = [(tid, ttype, lang, tname) for (tid, ttype, lang, tname) in tracks if ttype.lower().startswith("sub")]
    # Try exact match on language
    for tid, ttype, lang, tname in sub_tracks:
        if lang.lower() == desired_language.lower():
            return tid
    return None

def guess_embedded_subtitle(mkv_file, is_chinese=False):
    """
    Helper that tries to guess the track ID for the desired language.
    For Chinese, we look for 'chi', 'zho', or 'chinese' in track name or language code.
    For English, we look for 'eng' or 'english'.
    If not found, or if multiple matches, prompt the user.
    """
    tracks = list_mkv_tracks(mkv_file)
    subtitle_tracks = [(tid, ttype, lang, name) for (tid, ttype, lang, name) in tracks if ttype.lower().startswith("sub")]
    if not subtitle_tracks:
        return None  # no subtitle tracks

    # Potential language codes for Chinese
    if is_chinese:
        possible_codes = ["chi", "zho", "chinese", "cht", "chs"]
    else:
        possible_codes = ["eng", "english"]

    # Filter by language or name
    matches = []
    for tid, ttype, lang, name in subtitle_tracks:
        text = f"{lang.lower()} {name.lower()}"
        if any(code in text for code in possible_codes):
            matches.append((tid, lang, name))

    if len(matches) == 1:
        return matches[0][0]  # track ID
    elif len(matches) > 1:
        # Ask user which track
        print(f"Multiple candidate {'Chinese' if is_chinese else 'English'} subtitle tracks found in '{mkv_file}':")
        for i, (tid, lang, name) in enumerate(matches, start=1):
            print(f"  {i}) Track ID {tid} [language: {lang}, name: {name}]")
        choice = input("Choose a track number (or press Enter to skip): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            chosen = matches[int(choice)-1]
            return chosen[0]
        else:
            return None
    else:
        # No direct matches, prompt user for any track
        print(f"No direct match found for {'Chinese' if is_chinese else 'English'} track in '{mkv_file}'.")
        if subtitle_tracks:
            print(f"Available subtitle tracks:")
            for i, (tid, ttype, lang, name) in enumerate(subtitle_tracks, start=1):
                print(f"  {i}) Track ID {tid} [language: {lang}, name: {name}]")
            choice = input("Choose a track number (or press Enter to skip): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(subtitle_tracks):
                chosen = subtitle_tracks[int(choice)-1]
                return chosen[0]
        return None

def find_external_sub(video_path, is_chinese=False):
    """
    Look for external sub in same folder with the same base name + typical suffixes.
    Returns path if found, else None.
    E.g. for 'MyMovie.mkv', tries 'MyMovie.zh.srt', 'MyMovie.zh-TW.srt', etc.
    If is_chinese=False, tries typical English suffixes.
    """
    folder = os.path.dirname(video_path)
    base = os.path.splitext(video_path)[0]  # remove .mkv
    # Common variants
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

    # We just see if we can find anything that matches
    for pat in patterns:
        for candidate in glob.glob(pat):
            # pick the first matching file
            if os.path.isfile(candidate):
                return candidate
    return None

def process_one_video(video_path, eng_sub=None, chi_sub=None, out_format="srt", out_file=None):
    """
    Process a single video file, merging English/Chinese subtitles into out_format (srt/ass).
    If eng_sub or chi_sub is None, attempt to find or extract from the MKV or external subs.
    """
    # If no ENG sub provided, try external
    if not eng_sub:
        maybe_ext = find_external_sub(video_path, is_chinese=False)
        if maybe_ext:
            eng_sub = maybe_ext
        else:
            # attempt embedded
            track_id = guess_embedded_subtitle(video_path, is_chinese=False)
            if track_id:
                # extract to tmp
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".eng_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extract_subtitle_track(video_path, track_id, tmp_path)
                eng_sub = tmp_path

    # If no CHI sub provided, try external
    if not chi_sub:
        maybe_ext = find_external_sub(video_path, is_chinese=True)
        if maybe_ext:
            chi_sub = maybe_ext
        else:
            # attempt embedded
            track_id = guess_embedded_subtitle(video_path, is_chinese=True)
            if track_id:
                tmp_file = os.path.splitext(os.path.basename(video_path))[0] + f".chi_track_{track_id}.ass"
                tmp_path = os.path.join(tempfile.gettempdir(), tmp_file)
                extract_subtitle_track(video_path, track_id, tmp_path)
                chi_sub = tmp_path

    # If still no eng_sub or chi_sub => skip
    if not eng_sub and not chi_sub:
        print(f"WARNING: No Chinese or English subtitles found for '{video_path}'. Skipping.")
        return
    elif not eng_sub:
        print(f"WARNING: No English subtitles found for '{video_path}'. Will only use Chinese.")
    elif not chi_sub:
        print(f"WARNING: No Chinese subtitles found for '{video_path}'. Will only use English.")

    # parse the subs we have
    eng_events, eng_styles, script_info_eng = [], [], []
    chi_events, chi_styles, script_info_chi = [], [], []

    def is_srt(file):
        return file and file.lower().endswith(".srt")
    def is_ass(file):
        return file and file.lower().endswith(".ass")

    # English
    if eng_sub and os.path.exists(eng_sub):
        if is_srt(eng_sub):
            eng_events = parse_srt(eng_sub)
        elif is_ass(eng_sub):
            eev, esty, si = parse_ass(eng_sub)
            eng_events, eng_styles, script_info_eng = eev, esty, si

    # Chinese
    if chi_sub and os.path.exists(chi_sub):
        if is_srt(chi_sub):
            chi_events = parse_srt(chi_sub)
        elif is_ass(chi_sub):
            cev, csty, si = parse_ass(chi_sub)
            chi_events, chi_styles, script_info_chi = cev, csty, si

    # detect forced track
    forced_track = detect_forced_track(chi_events, eng_events)
    if forced_track:
        print(f"Warning: The {forced_track} track appears much shorter. Could be forced or partial subs.")

    # If no out_file provided, pick a name
    if not out_file:
        base = os.path.splitext(video_path)[0]
        out_file = f"{base}.bilingual.{out_format}"

    # merge
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
                f.write(f"{i}\n{start_str} --> {end_str}\n{ev['text']}\n\n")
        print(f"Created bilingual SRT: {out_file}")

    else:  # "ass"
        merged_ass = merge_events_ass(chi_events, eng_events, chi_styles, eng_styles, script_info_chi, script_info_eng)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(codecs.BOM_UTF8.decode('utf-8'))
            f.write(merged_ass)
        print(f"Created bilingual ASS: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Merge English & Chinese subtitles into a single bilingual file.")
    parser.add_argument("-e", "--english", help="English subtitle file path (.srt or .ass)")
    parser.add_argument("-c", "--chinese", help="Chinese subtitle file path (.srt or .ass)")
    parser.add_argument("-o", "--output", help="Output file path (defaults to <video>.bilingual.srt or .ass)")
    parser.add_argument("-f", "--format", choices=["srt","ass"], help="Output format. Defaults to 'srt'.")
    parser.add_argument("-v", "--video", help="Video file (e.g. .mkv). If not set but -e/-c are provided, merges those two subs directly.")
    parser.add_argument("--bulk", action="store_true", help="Process all MKV files in current folder (or specify with -v) in bulk.")
    args = parser.parse_args()

    out_format = args.format or "srt"

    # If bulk mode is set, we process all MKV files in a folder
    if args.bulk:
        # If user provided a single folder or file in -v, we handle that; otherwise, current dir
        path = args.video or "."
        if os.path.isdir(path):
            mkvs = glob.glob(os.path.join(path, "*.mkv"))
        elif os.path.isfile(path) and path.lower().endswith(".mkv"):
            mkvs = [path]
        else:
            mkvs = []

        if not mkvs:
            print("No MKV files found for bulk operation.")
            return

        for mkv_file in mkvs:
            print(f"\n=== Processing: {mkv_file} ===")
            process_one_video(mkv_file,
                              eng_sub=args.english,
                              chi_sub=args.chinese,
                              out_format=out_format,
                              out_file=None)
        return

    # Non-bulk mode
    # If user has provided a specific video, do the "auto-detect" logic if needed
    if args.video:
        process_one_video(args.video,
                          eng_sub=args.english,
                          chi_sub=args.chinese,
                          out_format=out_format,
                          out_file=args.output)
    else:
        # If user only gave -e and -c with no video, we just do a direct merge
        if not args.english or not args.chinese:
            print("ERROR: Either specify both --english and --chinese subtitles directly, "
                  "or provide a --video for auto-detection, or use --bulk mode.")
            return

        # Merge two external files directly
        # We'll parse them, merge, and write out
        eng_file = args.english
        chi_file = args.chinese
        # parse
        eng_events, eng_styles, script_info_eng = ([],[],[])
        chi_events, chi_styles, script_info_chi = ([],[],[])

        def is_srt(file):
            return file.lower().endswith(".srt")
        def is_ass(file):
            return file.lower().endswith(".ass")

        if is_srt(eng_file):
            eng_events = parse_srt(eng_file)
        elif is_ass(eng_file):
            eev, esty, si = parse_ass(eng_file)
            eng_events, eng_styles, script_info_eng = eev, esty, si
        else:
            print(f"Unsupported file format for English: {eng_file}")
            return

        if is_srt(chi_file):
            chi_events = parse_srt(chi_file)
        elif is_ass(chi_file):
            cev, csty, si = parse_ass(chi_file)
            chi_events, chi_styles, script_info_chi = cev, csty, si
        else:
            print(f"Unsupported file format for Chinese: {chi_file}")
            return

        forced_track = detect_forced_track(chi_events, eng_events)
        if forced_track:
            print(f"Warning: The {forced_track} track appears much shorter. Possibly forced or partial.")

        out_file = args.output
        if not out_file:
            out_file = "merged." + out_format

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
                    f.write(f"{i}\n{start_str} --> {end_str}\n{ev['text']}\n\n")
            print(f"Created merged SRT: {out_file}")
        else:
            merged_ass = merge_events_ass(chi_events, eng_events, chi_styles, eng_styles, script_info_chi, script_info_eng)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(codecs.BOM_UTF8.decode('utf-8'))
                f.write(merged_ass)
            print(f"Created merged ASS: {out_file}")

if __name__ == "__main__":
    main()
