```markdown
# Subtitle Realignment Script

This **standalone Python script** scans a folder for pairs of subtitles – one designated as the **source** (which needs shifting) and one designated as the **reference** (correctly aligned). It then **shifts** all timestamps in the source subtitle so that its earliest line begins at the same time as the earliest line in the reference subtitle. This works **in bulk**, handling all matching pairs in a given directory.

---

## Features

1. **Automatic Pair Detection**  
   - Matches filenames up to the language/extension part (e.g., `S01E03.zh.ass` vs `S01E03.en.ass`).

2. **ASS or SRT Parsing**  
   - Automatically identifies whether each file is ASS (`.ass`) or SRT (`.srt`) and parses accordingly.

3. **Time Shift Computation**  
   - Determines the offset as:  
     ```
     shift = reference_first_start - source_first_start
     ```
   - Shifts **all** events in the source subtitle by this offset.

4. **Bulk Processing**  
   - Searches a directory for source files (given by `--src-ext`) and locates corresponding reference files (given by `--ref-ext`).

5. **Minimal Dependencies**  
   - Uses only Python’s standard library; no external modules required.

6. **Configurable Overwrite**  
   - By default, **overwrites** the source file with the newly shifted times.  
   - You can easily alter the script to output to a new name instead.

---

## Usage Example

```bash
python realign_subtitles.py \
  --src-ext .zh.ass \
  --ref-ext .en.ass \
  --folder "Z:/Videos/Anime Shows/Fullmetal Alchemist (2003)"
```

- The script looks for all **`.zh.ass`** files in `"Z:/Videos/Anime Shows/Fullmetal Alchemist (2003)"`.
- For each `.zh.ass`, it checks if a **`.en.ass`** file with the same base name exists.
- If found, it parses both, calculates the time shift, and applies that shift to the `.zh.ass` file in-place.

---

## How the Script Works

1. **Find All “Source” Files**  
   The script reads `--folder` (default `.` if not specified) and looks for all files ending with `--src-ext` (e.g. `.zh.ass`).

2. **Locate Matching “Reference”**  
   For each “source” file, it replaces that extension with `--ref-ext` (e.g. `.en.ass`) to see if a **reference** file of the same base name exists.

3. **Parse Both Subtitles**  
   - **SRT**  
     - Splits file into blocks by blank lines.  
     - Matches each block’s time line with a pattern like `(\d+:\d+:\d+[,\.]\d+) --> (\d+:\d+:\d+[,\.]\d+)`.
   - **ASS**  
     - Reads the `[Events]` section line by line.  
     - Stores the entire file content so it can rewrite lines with updated times.

4. **Compute Shift**  
   - Finds each file’s earliest start time:  
     ```
     shift_seconds = (reference_earliest_start) - (source_earliest_start)
     ```
   - Example: if the reference starts at `10.0s` and the source starts at `6.5s`, then shift = `+3.5s`.

5. **Apply Shift**  
   - Adds `shift_seconds` to **every** event’s start and end times in the source file.  
   - **ASS**: rewrites the original “Dialogue:” lines with updated time fields.  
   - **SRT**: regenerates time lines with updated values.

6. **Result**  
   - The source file’s earliest line now begins exactly when the reference file’s earliest line does.  
   - All subsequent lines remain consistently offset.

---

## Tips

1. **Output to a New File**  
   - By default, the script **overwrites** `src_path`.  
   - To create a new file instead, change:
     ```python
     out_path = src_path
     ```
     to
     ```python
     out_path = src_path.replace(src_ext, f".realigned{src_ext}")
     ```

2. **Additional Manual Offset**  
   - If you want to **nudge** the alignment further, you can add or subtract a fixed amount:
     ```python
     shift_secs += 1.0  # e.g. shift an extra 1 second forward
     ```
     or  
     ```python
     shift_secs -= 0.5  # half-second backward shift
     ```

3. **Zero Start Times**  
   - If both files have lines starting at `0.0s`, the shift might be 0s. Verify your reference subtitles if you notice no change.

4. **Language Tags**  
   - You can specify `--src-ext` and `--ref-ext` for any “extension” you like, e.g., `.fr.srt`, `.pt.ass`, etc.
