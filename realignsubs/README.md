# Subtitle Realignment Script

This standalone Python script **scans a folder** for pairs of subtitles—one designated as the **source** (which needs shifting) and one as the **reference** (correctly aligned). It then **shifts** all timestamps in the source subtitle so that its **earliest line** begins at the same time as the earliest line in the reference subtitle. It works **in bulk**, handling all matching pairs in a directory.  
**All timing is handled internally in milliseconds**, ensuring finer control and easy offset adjustments.

---

## Key Features

1. **Automatic Pair Detection**  
   - Matches files by **base name** and extension.  
   - E.g., `MyEpisode.zh.ass` is paired with `MyEpisode.en.ass`.

2. **Handles ASS or SRT**  
   - Automatically parses `.ass` or `.srt` files.  
   - For `.srt`, it interprets `HH:MM:SS,mmm` → integer milliseconds.  
   - For `.ass`, it reads lines in `[Events]` and converts times to/from milliseconds.

3. **Millisecond Time-Shift**  
   - The script computes:  
     \[
       \text{shift\_ms} = (\text{reference\_earliest\_ms}) - (\text{source\_earliest\_ms})
     \]  
   - Then **adds** `shift_ms` to **every** subtitle event in the source file.  
   - Negative results are clamped to `0` ms, so times don’t go below zero.

4. **Bulk Processing**  
   - Provide `--src-ext` (e.g., `.zh.ass`) and `--ref-ext` (e.g., `.en.ass`), and **all** matching pairs in a folder are processed in one go.

5. **Minimal Dependencies**  
   - Uses only **Python’s standard library**—no external modules needed.

6. **Overwrite or Rename**  
   - By default, **overwrites** the source file with the updated times.  
   - Easily change this to output a fresh file (e.g., `.realigned.ass`).

---

## Example Usage

```bash
python realign_subtitles.py \
  --src-ext .zh.ass \
  --ref-ext .en.ass \
  --folder "Z:/Videos/Anime Shows/Fullmetal Alchemist (2003)"
```

- The script looks for all `.zh.ass` files in `"Z:/Videos/Anime Shows/Fullmetal Alchemist (2003)"`.  
- For each one, it checks if a **`.en.ass`** with the same base name is present.  
- If found, it:
  1. Parses both subtitles, identifies the earliest start time in ms for each.
  2. Computes the offset (`reference_earliest_ms - source_earliest_ms`).
  3. Shifts **all** lines in the source by that offset.
  4. Updates (or overwrites) the `.zh.ass` file with the realigned times.

---

## Step-by-Step Process

1. **Find “Source” Files**  
   - The script scans the given folder (`--folder`) for any file ending with `--src-ext` (e.g., `.zh.ass`).

2. **Locate Matching “Reference”**  
   - For each “source” file found, it replaces that extension with `--ref-ext` (e.g., `.en.ass`) to see if a file with the same base name exists.

3. **Parsing Subtitles**  
   - **SRT**:  
     - Splits text by blank lines for each event.  
     - Parses `HH:MM:SS,mmm` into an integer millisecond value.  
   - **ASS**:  
     - Focuses on lines within `[Events]`.  
     - For `dialogue` lines, extracts times (`H:MM:SS.xx` or `H:MM:SS.mmm`) and converts them into ms.

4. **Compute Shift (in ms)**  
   - Let `src_min_ms` = earliest start time in the source file (ms).  
   - Let `ref_min_ms` = earliest start time in the reference file (ms).  
   - `shift_ms` = `ref_min_ms - src_min_ms`.  
   - Example: if `ref_min_ms=10000` and `src_min_ms=6500`, shift is `+3500` ms.

5. **Apply the Shift**  
   - Add `shift_ms` to each event’s start and end time in the source.  
   - If any time becomes negative, it’s clamped to `0`.

6. **Rewrite the Source**  
   - **SRT**: Re-generates the `HH:MM:SS,mmm --> HH:MM:SS,mmm` lines with the updated ms.  
   - **ASS**: Replaces the relevant portion of each `Dialogue:` line with the new times.

7. **Result**  
   - The source file’s earliest line now starts exactly where the reference file’s earliest line begins.  
   - All subsequent lines remain consistently offset.

---

## Tips & Tricks

1. **Output to a New File**  
   - Currently, the script overwrites the source.  
   - To create a new file, find the line:
     ```python
     out_path = src_path
     ```
     and change it to something like:
     ```python
     out_path = src_path.replace(src_ext, f".realigned{src_ext}")
     ```
     This yields new files (e.g. `MyEpisode.zh.realigned.ass`) without touching the original.

2. **Add a Manual Offset**  
   - If you want to shift the source an extra 1 second (1000 ms) forward, do:
     ```python
     shift_ms += 1000
     ```
     or shift half a second backward:
     ```python
     shift_ms -= 500
     ```
     This is handy if the reference is close but not perfectly aligned.

3. **Handling Zero Starts**  
   - Sometimes both subs might have an event at `0 ms`, causing no shift.  
   - Check your reference subtitle if you suspect it’s not truly aligned at zero.

4. **Language/Extension Flexibility**  
   - The script doesn’t care about real language codes—it just matches file extensions.  
   - You can do `--src-ext .fr.srt --ref-ext .en.srt` or similar for any combination.

---
