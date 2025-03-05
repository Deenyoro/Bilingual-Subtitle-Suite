#!/usr/bin/env python3
import argparse
import os
import re
import glob
import logging
import sys

# --------------------------
# CONFIGURE LOGGING
# --------------------------
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("subtitle_realign")


# --------------------------
# PARSING SRT
# --------------------------
def parse_srt(file_path):
    """
    Returns a list of events: [{'start':float_seconds, 'end':float_seconds, 'text':str}, ...]
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        data = f.read()

    # SRT blocks typically separated by blank lines
    blocks = re.split(r'\r?\n\r?\n', data.strip())
    events = []
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        # If block starts with an index number, skip that line
        if re.match(r'^\d+$', lines[0]):
            lines = lines[1:]
        if not lines:
            continue

        # e.g. "00:00:01,000 --> 00:00:04,000"
        match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', lines[0])
        if not match:
            continue
        start_str, end_str = match.groups()
        start_str = start_str.replace(',', '.')
        end_str   = end_str.replace(',', '.')

        # Convert time to float seconds
        start = srt_time_to_seconds(start_str)
        end   = srt_time_to_seconds(end_str)

        text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        events.append({'start': start, 'end': end, 'text': text})
    return events

def srt_time_to_seconds(timestr):
    # "HH:MM:SS.mmm"
    h, m, s = timestr.split(':')
    if '.' in s:
        s, ms = s.split('.')
    else:
        ms = '0'
    return int(h)*3600 + int(m)*60 + int(s) + float(ms)/1000.0

def write_srt(events, out_path):
    """
    Write the list of events back to an SRT file.
    """
    with open(out_path, 'w', encoding='utf-8') as f:
        # Optionally add a UTF-8 BOM if desired:
        # f.write('\ufeff')
        for i, ev in enumerate(events, start=1):
            start_str = seconds_to_srt_time(ev['start'])
            end_str   = seconds_to_srt_time(ev['end'])
            f.write(f"{i}\n{start_str} --> {end_str}\n{ev['text']}\n\n")

def seconds_to_srt_time(sec):
    # produce "HH:MM:SS,mmm"
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------
# PARSING ASS
# --------------------------
def parse_ass(file_path):
    """
    Returns (script_lines, events_list).
    We keep the entire script lines in memory so we can rewrite them with updated times.
    'events_list' is a list of dicts:
      [{'start': float_seconds, 'end': float_seconds, 'dialogue_line': original_line, 'idx': line_index_in_file}, ...]
    We'll update only the 'start' and 'end' times in the "Dialogue:" lines.
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    events = []
    in_events = False
    format_cols = []
    for i, line in enumerate(lines):
        line_stripped = line.strip().lower()
        # Detect [Events] section
        if line_stripped.startswith("[events]"):
            in_events = True
            continue
        # If we see new section or empty bracket, events are done
        if in_events and line_stripped.startswith("["):
            in_events = False
            continue

        if in_events:
            # Example lines:
            # Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            if line_stripped.startswith("format:"):
                # parse format fields
                # e.g. "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
                parts = line.split(":", 1)[1].split(",")
                format_cols = [p.strip().lower() for p in parts]
                continue

            # Dialogue lines
            if line_stripped.startswith("dialogue:"):
                # e.g. "Dialogue: 0,0:00:03.20,0:00:07.10,StyleName,,0,0,0,,Text"
                # split into up to len(format_cols) parts
                content = line.split(":", 1)[1]
                if format_cols:
                    parts = content.split(",", len(format_cols)-1)
                else:
                    # fallback if format is unknown
                    parts = content.split(",", 9)

                # find start/end indexes
                if len(parts) < 3:
                    continue
                try:
                    start_idx = format_cols.index("start")
                    end_idx   = format_cols.index("end")
                except ValueError:
                    # fallback if 'start' or 'end' not found
                    start_idx, end_idx = 1, 2

                start_str = parts[start_idx].strip()
                end_str   = parts[end_idx].strip()

                start_sec = ass_time_to_seconds(start_str)
                end_sec   = ass_time_to_seconds(end_str)

                events.append({
                    'start': start_sec,
                    'end': end_sec,
                    'dialogue_line': line,  # keep original
                    'idx': i               # line index in file
                })

    return lines, events

def ass_time_to_seconds(ass_time):
    # "H:MM:SS.xx" (centiseconds) or "HH:MM:SS.mmm" if extended
    # typical format is "0:00:03.20" => 3.2 seconds
    # We'll handle it robustly
    parts = ass_time.split(':')
    if len(parts) < 3:
        return 0.0
    h = int(parts[0])
    m = int(parts[1])
    s_cs = parts[2]  # e.g. "03.20"
    if '.' in s_cs:
        s, cs = s_cs.split('.')
    else:
        s = s_cs
        cs = "00"
    # check if cs is length 2 => centiseconds, length 3 => milliseconds, etc.
    if len(cs) == 2:
        # centiseconds
        fraction = float(cs) / 100.0
    else:
        # treat as ms
        fraction = float(cs) / 1000.0
    return h*3600 + m*60 + int(s) + fraction

def seconds_to_ass_time(sec):
    # Typically "H:MM:SS.cc" for .ass
    # We'll produce centiseconds
    # but if you prefer, you can produce hundredths or thousandths
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s_float = sec - (h*3600 + m*60)
    s = int(s_float)
    fraction = s_float - s
    # convert fraction to centiseconds
    csecs = int(round(fraction * 100))

    return f"{h}:{m:02d}:{s:02d}.{csecs:02d}"

def write_ass(original_lines, events, out_path):
    """
    Overwrites the "Dialogue:" lines in 'original_lines' with updated times from 'events'.
    Then writes out to 'out_path'.
    """
    # We'll build a quick index by 'idx' => event
    events_by_idx = {e['idx']: e for e in events}

    out_data = []
    for i, line in enumerate(original_lines):
        if i in events_by_idx:
            ev = events_by_idx[i]
            # we must rewrite the line with new start/end times
            old_line = ev['dialogue_line']
            prefix, content = old_line.split(":", 1)
            # e.g. content = " 0,0:00:03.20,0:00:07.10,Default,,0,0,0,,Text"
            # we match the format from parse
            # we need to figure out how many fields => use the line's prior "Format:" reference
            # but let's do a simpler approach: split on commas to reinsert times
            fields = content.split(",", 9)  # up to 10 parts

            if len(fields) >= 3:
                # assume fields[1] is start, fields[2] is end
                fields[1] = seconds_to_ass_time(ev['start'])
                fields[2] = seconds_to_ass_time(ev['end'])
                new_content = ",".join(fields)
                new_line = prefix + ":" + new_content
                out_data.append(new_line)
            else:
                # fallback
                out_data.append(line)
        else:
            out_data.append(line)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.writelines(out_data)


# --------------------------
# SHIFTING LOGIC
# --------------------------
def shift_events(events, shift_seconds):
    """
    Add 'shift_seconds' to each event's start/end time.
    """
    for ev in events:
        ev['start'] += shift_seconds
        ev['end']   += shift_seconds


# --------------------------
# MAIN BULK SCRIPT
# --------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Bulk realign subtitle files (e.g. .zh.ass) to match the start time of reference subtitles (e.g. .en.ass)."
    )
    parser.add_argument("--folder", default=".", help="Folder to scan for subtitle pairs. Default is current directory.")
    parser.add_argument("--src-ext", required=True,
                        help="Source subtitle extension to be realigned (e.g. .zh.ass or .cn.srt). "
                             "We'll shift these times to match the reference’s first line start.")
    parser.add_argument("--ref-ext", required=True,
                        help="Reference subtitle extension (e.g. .en.ass or .en.srt). "
                             "We'll read the earliest start time from here and realign the source to it.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    folder = args.folder
    src_ext = args.src_ext.lower()
    ref_ext = args.ref_ext.lower()

    logger.info(f"Realigning all '{src_ext}' subtitles in {folder} to match earliest start times of '{ref_ext}' subtitles.")

    # 1) Find all source subtitle files that match the src_ext
    pattern = os.path.join(folder, f"*{src_ext}")
    src_files = glob.glob(pattern)
    if not src_files:
        logger.warning(f"No source files found matching {pattern}")
        sys.exit(0)

    for src_path in src_files:
        base = src_path[:-len(src_ext)]  # remove the extension (including the dot)
        ref_path = base + ref_ext
        if not os.path.exists(ref_path):
            logger.info(f"No matching reference found for: {os.path.basename(src_path)}. Skipping.")
            continue

        logger.info(f"\n--- Realigning ---\n Source: {os.path.basename(src_path)}\n Ref   : {os.path.basename(ref_path)}")

        # 2) parse both subtitles
        source_events, reference_events = None, None
        # parse source
        if src_ext.endswith(".ass"):
            src_lines, src_evs = parse_ass(src_path)
            source_events = src_evs
        else:
            source_events = parse_srt(src_path)

        # parse reference
        if ref_ext.endswith(".ass"):
            ref_lines, ref_evs = parse_ass(ref_path)
            reference_events = ref_evs
        else:
            reference_events = parse_srt(ref_path)

        if not source_events or not reference_events:
            logger.info("No events found in either source or reference. Skipping.")
            continue

        # 3) find earliest start times
        src_min = min(ev['start'] for ev in source_events)
        ref_min = min(ev['start'] for ev in reference_events)
        shift_secs = ref_min - src_min
        logger.info(f" Earliest source start = {src_min:.3f}s; reference start = {ref_min:.3f}s")
        logger.info(f" => Shifting source by {shift_secs:+.3f} seconds.")

        # 4) shift all source events
        shift_events(source_events, shift_secs)

        # 5) write out
        out_path = src_path  # overwrite or you can create a new name if you prefer
        if src_ext.endswith(".ass"):
            # must rewrite lines with new times
            write_ass(src_lines, source_events, out_path)
        else:
            # rewrite srt
            write_srt(source_events, out_path)

        logger.info(f" => Updated times in: {os.path.basename(out_path)}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
