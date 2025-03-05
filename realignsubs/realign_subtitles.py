#!/usr/bin/env python3
import argparse
import os
import re
import glob
import logging
import sys

# ----------------------------------------------------
# LOGGING SETUP
# ----------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("subtitle_realign_ms")


# ----------------------------------------------------
# HELPER: SHIFT EVENTS
# ----------------------------------------------------
def shift_events_ms(events, shift_ms):
    """
    Add 'shift_ms' (integer milliseconds) to each event's start/end time.
    """
    for ev in events:
        ev['start'] += shift_ms
        ev['end']   += shift_ms

        # Ensure no negative times:
        if ev['start'] < 0:
            ev['start'] = 0
        if ev['end'] < 0:
            ev['end'] = 0


# ----------------------------------------------------
# SRT PARSING & WRITING (IN MS)
# ----------------------------------------------------
def parse_srt_ms(file_path):
    """
    Read an SRT file and return a list of events with start/end in milliseconds:
    [
      {
        'start': int_milliseconds,
        'end'  : int_milliseconds,
        'text' : str
      },
      ...
    ]
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        data = f.read()

    blocks = re.split(r'\r?\n\r?\n', data.strip())
    events = []
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        # If block starts with an integer index, skip it
        if re.match(r'^\d+$', lines[0]):
            lines = lines[1:]
        if not lines:
            continue

        # e.g. "00:00:01,000 --> 00:00:04,000"
        match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', lines[0])
        if not match:
            continue
        start_str, end_str = match.groups()

        # Convert to ms
        start_ms = srt_timestamp_to_ms(start_str)
        end_ms   = srt_timestamp_to_ms(end_str)

        text = "\n".join(lines[1:]) if len(lines) > 1 else ""
        events.append({
            'start': start_ms,
            'end'  : end_ms,
            'text' : text
        })
    return events

def srt_timestamp_to_ms(timestr):
    """
    Convert "HH:MM:SS,mmm" (or with '.') to integer milliseconds.
    Example: "00:01:02,345" -> 62345 ms
    """
    timestr = timestr.replace(',', '.')  # unify decimal
    h_str, m_str, s_str = timestr.split(':')
    h = int(h_str)
    m = int(m_str)
    # s_str might have a decimal, e.g. "03.200"
    if '.' in s_str:
        s, ms_str = s_str.split('.')
    else:
        s, ms_str = s_str, '0'
    s = int(s)
    ms = int(ms_str.ljust(3, '0')[:3])  # ensure up to 3 digits
    total_ms = (h*3600 + m*60 + s) * 1000 + ms
    return total_ms

def write_srt_ms(events, out_path):
    """
    Write a list of event dicts (with start/end in ms) to an SRT file.
    """
    with open(out_path, 'w', encoding='utf-8') as f:
        # If you want a UTF-8 BOM, uncomment:
        # f.write('\ufeff')
        for i, ev in enumerate(events, start=1):
            start_str = ms_to_srt_timestamp(ev['start'])
            end_str   = ms_to_srt_timestamp(ev['end'])
            text_block = ev['text']
            f.write(f"{i}\n{start_str} --> {end_str}\n{text_block}\n\n")

def ms_to_srt_timestamp(ms):
    """
    Convert integer ms to "HH:MM:SS,mmm".
    """
    if ms < 0:
        ms = 0
    h  = ms // 3600000
    ms = ms % 3600000
    m  = ms // 60000
    ms = ms % 60000
    s  = ms // 1000
    ms = ms % 1000

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ----------------------------------------------------
# ASS PARSING & WRITING (IN MS)
# ----------------------------------------------------
def parse_ass_ms(file_path):
    """
    Parse an ASS file, returning:
    (original_lines, events) where events = [
      {
        'start': int_milliseconds,
        'end':   int_milliseconds,
        'dialogue_line': str,
        'idx': int_line_index
      },
      ...
    ]
    We'll only modify times in "Dialogue:" lines within the [Events] section.
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    events = []
    in_events = False
    format_cols = []

    for i, line in enumerate(lines):
        line_lower = line.strip().lower()

        if line_lower.startswith("[events]"):
            in_events = True
            continue
        if in_events and line_lower.startswith("["):
            # new section => done with events
            in_events = False
            continue

        if in_events:
            if line_lower.startswith("format:"):
                # e.g. Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
                parts = line.split(":", 1)[1].split(",")
                format_cols = [p.strip().lower() for p in parts]
                continue

            if line_lower.startswith("dialogue:"):
                # e.g.: "Dialogue: 0,0:00:03.20,0:00:07.10,Style,,0,0,0,,Text"
                content = line.split(":", 1)[1]
                if format_cols:
                    parts = content.split(",", len(format_cols)-1)
                else:
                    parts = content.split(",", 9)

                if len(parts) < 3:
                    continue

                # find start/end indexes
                try:
                    start_idx = format_cols.index("start")
                    end_idx   = format_cols.index("end")
                except ValueError:
                    start_idx, end_idx = 1, 2

                start_str = parts[start_idx].strip()
                end_str   = parts[end_idx].strip()

                start_ms = ass_timestamp_to_ms(start_str)
                end_ms   = ass_timestamp_to_ms(end_str)

                events.append({
                    'start': start_ms,
                    'end'  : end_ms,
                    'dialogue_line': line,
                    'idx': i
                })

    return lines, events

def ass_timestamp_to_ms(ass_time):
    """
    Convert an ASS timestamp string to integer ms.
    Typical format: "H:MM:SS.xx" (centiseconds) or "H:MM:SS.mmm" (ms).
    We'll handle variable decimals by converting to ms as best as possible.
    e.g. "0:00:03.20" -> 3.20s => 3200 ms
    """
    parts = ass_time.split(':')
    if len(parts) < 3:
        return 0
    h = int(parts[0])
    m = int(parts[1])

    s_part = parts[2]  # e.g. "03.20" or "10.005"
    if '.' in s_part:
        s_str, frac_str = s_part.split('.', 1)
    else:
        s_str, frac_str = s_part, '0'

    s = int(s_str)
    # We'll treat frac_str as ms if length >= 3, else as centiseconds if length=2
    if len(frac_str) >= 3:
        # assume it's ms
        ms = int(frac_str[:3].ljust(3, '0'))
    else:
        # treat as centiseconds or tenths, convert to ms
        # e.g. "20" = 20 cs = 200 ms
        # e.g. "2" = 2 tenths = 200 ms
        frac_int = int(frac_str)
        if len(frac_str) == 2:
            ms = frac_int * 10  # 20cs => 200ms
        elif len(frac_str) == 1:
            ms = frac_int * 100
        else:
            ms = 0

    total_ms = (h*3600 + m*60 + s)*1000 + ms
    return total_ms

def ms_to_ass_timestamp(ms):
    """
    Convert integer ms back into an ASS-style "H:MM:SS.cs" or "H:MM:SS.xxx".
    By tradition, ASS often uses 2-digit centiseconds, but to keep more precision
    we can output 3-digit ms. We'll do 2 digits for a typical approach (like Aegisub).
    If you prefer 3-digit ms, just adjust the formatting below.
    """
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    remain_ms     = ms % 1000

    h = total_seconds // 3600
    total_seconds %= 3600
    m = total_seconds // 60
    s = total_seconds % 60

    # Convert remain_ms to centiseconds (2 digits)
    #  remain_ms is 0..999, so centiseconds = remain_ms // 10
    centi = int(round(remain_ms / 10.0))  # integer 0..100
    # but ensure it's max 99 if rounding pushes it to 100
    if centi >= 100:
        # means it was 999 ms, e.g. 9.99 => roll over?
        centi = 99

    return f"{h}:{m:02d}:{s:02d}.{centi:02d}"

def write_ass_ms(original_lines, events, out_path):
    """
    Overwrite the "Dialogue:" lines with updated times in ms form.
    """
    events_by_idx = {e['idx']: e for e in events}
    out_data = []

    for i, line in enumerate(original_lines):
        if i in events_by_idx:
            ev = events_by_idx[i]
            old_line = ev['dialogue_line']
            prefix, content = old_line.split(":", 1)  # "Dialogue", ...
            fields = content.split(",", 9)
            if len(fields) >= 3:
                fields[1] = ms_to_ass_timestamp(ev['start'])
                fields[2] = ms_to_ass_timestamp(ev['end'])
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


# ----------------------------------------------------
# MAIN BULK SCRIPT
# ----------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Bulk realign subtitle files (e.g. .zh.ass) to match the start time "
            "of reference subtitles (e.g. .en.ass). Now everything is in ms!"
        )
    )
    parser.add_argument("--folder", default=".",
                        help="Folder to scan for subtitle pairs. Default is current directory.")
    parser.add_argument("--src-ext", required=True,
                        help="Source subtitle extension to be realigned (e.g. .zh.ass or .cn.srt). "
                             "We'll shift these times to match the reference’s first line start.")
    parser.add_argument("--ref-ext", required=True,
                        help="Reference subtitle extension (e.g. .en.ass or .en.srt). "
                             "We'll read the earliest start time from here and realign the source to it.")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    folder = args.folder
    src_ext = args.src_ext.lower().strip()
    ref_ext = args.ref_ext.lower().strip()

    logger.info(f"Realigning all '{src_ext}' subtitles in {folder} to match earliest start times of '{ref_ext}' subtitles.")

    pattern = os.path.join(folder, f"*{src_ext}")
    src_files = glob.glob(pattern)
    if not src_files:
        logger.warning(f"No source files found matching {pattern}")
        sys.exit(0)

    for src_path in src_files:
        base = src_path[:-len(src_ext)]
        ref_path = base + ref_ext
        if not os.path.exists(ref_path):
            logger.info(f"No matching reference for: {os.path.basename(src_path)} => skip.")
            continue

        logger.info(f"\n--- Realigning ---\n Source: {os.path.basename(src_path)}\n Ref   : {os.path.basename(ref_path)}")

        # Parse source
        if src_ext.endswith(".ass"):
            src_lines, src_events = parse_ass_ms(src_path)
        else:
            src_events = parse_srt_ms(src_path)
            src_lines = None

        # Parse reference
        if ref_ext.endswith(".ass"):
            ref_lines, ref_events = parse_ass_ms(ref_path)
        else:
            ref_events = parse_srt_ms(ref_path)
            ref_lines = None

        if not src_events or not ref_events:
            logger.info("No events in source or reference. Skipping.")
            continue

        # Find earliest start times (in ms)
        src_min_ms = min(e['start'] for e in src_events)
        ref_min_ms = min(e['start'] for e in ref_events)
        shift_ms = ref_min_ms - src_min_ms

        logger.info(f" Earliest source start = {src_min_ms} ms; reference start = {ref_min_ms} ms.")
        logger.info(f" => Shifting source by {shift_ms:+} ms.")

        # Shift
        shift_events_ms(src_events, shift_ms)

        # Write output
        out_path = src_path  # Overwrite in place or change if you prefer
        if src_ext.endswith(".ass"):
            write_ass_ms(src_lines, src_events, out_path)
        else:
            write_srt_ms(src_events, out_path)

        logger.info(f" => Updated times in: {os.path.basename(out_path)}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
