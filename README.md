# Bilingual Subtitle Merger

A Python script to **automatically merge** English and Chinese subtitles into a single subtitle track. The script can handle both external `.srt` or `.ass` subtitle files or extract embedded subtitle tracks from `.mkv` containers via [MKVToolNix](https://mkvtoolnix.download/) utilities. It can also perform "bulk" operations on multiple `.mkv` files at once.

## Features
1. **Automatic Detection**  
   - Looks for **external** Chinese (`.zh.srt`, `.zh.ass`, etc.) or English (`.en.srt`, `.en.ass`, etc.) subtitle files in the same folder.  
   - If no external file is found, it can extract them from **embedded** `.mkv` subtitle tracks (prompting the user to pick the correct track if necessary).

2. **Multiple Formats**  
   - Supports merging and outputting as **SRT** (SubRip `.srt`) or **ASS** (Advanced SubStation Alpha `.ass`).

3. **Bilingual Output**  
   - SRT: Combines Chinese and English text at overlapping times into a single block (`Chinese\nEnglish`).  
   - ASS: Places Chinese (top-aligned) and English (bottom-aligned) lines in separate styles, so they don’t visually overlap.

4. **Heuristic Check for Forced/Partial Subtitles**  
   - Warns if one track is significantly shorter than the other.

5. **Bulk Mode**  
   - Iterate over an entire folder of `.mkv` files and produce bilingual subtitles for each automatically.

## Requirements

1. **Python 3**  
   - Confirm you can run `python --version` or `python3 --version` in your terminal.

2. **MKVToolNix**  
   - [MKVToolNix](https://mkvtoolnix.download/) includes the `mkvextract` and `mkvmerge` commands required for embedded subtitle extraction.  
   - Verify they’re in your system PATH:  
     - **Windows**: open Command Prompt or PowerShell and run `mkvextract --version`.
     - **Linux/Mac**: open Terminal and run `mkvextract --version`.  
   - If not available, install from your package manager or [official downloads](https://mkvtoolnix.download/).

3. **UTF-8 Environment**  
   - The script reads/writes subtitles in UTF-8. Usually modern systems are fine, but if you see encoding errors, ensure your locale is set to UTF-8 or use `chcp 65001` on Windows.

## Installation

1. Download or copy the `bilingual_subtitle_merger.py` (the script above) onto your machine.
2. Make it executable if on Linux/Mac:
   ```bash
   chmod +x bilingual_subtitle_merger.py
   ```
3. Ensure `mkvextract` and `mkvmerge` are installed and in your PATH.

## Usage

### Basic Command
```bash
python bilingual_subtitle_merger.py [options]
```
On some systems you might need `python3`:
```bash
python3 bilingual_subtitle_merger.py [options]
```

### Command-Line Arguments

- `-v, --video`  
  Path to a **video file** (e.g. `.mkv`). The script will auto-detect or extract Chinese/English subs if not otherwise specified.

- `-e, --english`  
  Path to an **English subtitle** file (SRT or ASS). If given, the script will use this instead of searching for embedded or external subs.

- `-c, --chinese`  
  Path to a **Chinese subtitle** file (SRT or ASS). If given, the script will use this instead of searching for embedded or external subs.

- `-o, --output`  
  Output file path. If not specified, the script auto-generates a file named `<video_basename>.bilingual.srt` or `.ass`.

- `-f, --format`  
  Output subtitle format: `srt` or `ass`. Defaults to `srt`.

- `--bulk`  
  Processes **all** `.mkv` files in the current directory (or in the directory specified with `--video` if it’s a folder) in one go.  

### Operation Modes

1. **External-Only**  
   - Provide two external subtitle files via `-e` and `-c`.  
   - Example:  
     ```bash
     python bilingual_subtitle_merger.py -e Movie.en.srt -c Movie.zh.srt -o Movie.bilingual.srt
     ```
   - This merges `Movie.en.srt` and `Movie.zh.srt` directly into a single bilingual file named `Movie.bilingual.srt`.

2. **Single Video Auto**  
   - Provide a single `.mkv` with `-v`. The script attempts to find or extract English and Chinese subtitles automatically.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --video "Movie.mkv"
     ```
     - Looks in the same folder for external `.en.srt`, `.zh.srt`, etc.  
     - If not found, it scans embedded tracks in `Movie.mkv` and extracts whichever are recognized or manually chosen.

3. **Video with One External**  
   - Provide `-v` plus either `-e` or `-c` if you already have one track as an external file. The script will fill in the other from external or embedded.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --video "Movie.mkv" --chinese "Movie.zh.ass"
     ```
     - Will use `Movie.zh.ass` for the Chinese track.  
     - For English, the script first tries to find `Movie.en.srt/ass` or an embedded English track.

4. **Bulk Mode**  
   - Provide `--bulk` along with an optional directory or single `.mkv` via `--video`.  
   - Example:
     ```bash
     # Process all .mkv files in the current directory:
     python bilingual_subtitle_merger.py --bulk
     
     # OR specify a folder:
     python bilingual_subtitle_merger.py --video "/path/to/folder" --bulk
     ```
   - For each `.mkv`, it attempts to locate or extract Chinese/English subs and generate a bilingual `.srt` (or `.ass`).

## Examples

### Example 1: Merge Two External Subtitles
**Windows**:
```powershell
python .\bilingual_subtitle_merger.py -e "MyMovie.en.srt" -c "MyMovie.zh.srt" -o "MyMovie.bilingual.srt"
```
**Linux/macOS**:
```bash
python3 bilingual_subtitle_merger.py -e MyMovie.en.srt -c MyMovie.zh.srt -o MyMovie.bilingual.srt
```
- No `-v/--video` used here. This merges two external files directly.

### Example 2: Single MKV With Embedded English, External Chinese
```bash
python bilingual_subtitle_merger.py --video "MyMovie.mkv" --chinese "MyMovie.zh.srt"
```
- Uses `MyMovie.zh.srt` for Chinese.  
- Scans `MyMovie.mkv` for any embedded English track. If more than one is found, it prompts you to pick a track ID.

### Example 3: Bulk Processing
```bash
python bilingual_subtitle_merger.py --bulk
```
- In the current directory, every `.mkv` is processed automatically.  
- The script tries to find (or extract) Chinese/English subs for each file, then writes e.g. `file1.bilingual.srt`, `file2.bilingual.srt`, etc.

### Example 4: Output Format as ASS
```bash
python bilingual_subtitle_merger.py -v "MyMovie.mkv" -f ass
```
- Attempts to produce an **ASS** file instead of the default SRT, e.g. `MyMovie.bilingual.ass`.

## How It Works

1. **Subtitle Gathering**  
   - The script attempts to gather English (`--english`) and Chinese (`--chinese`) subtitles from (1) direct command-line arguments, (2) external files in the same folder as the video, or (3) embedded tracks in the `.mkv` file.

2. **Parsing**  
   - SRT subtitles are read and split into time-coded “events”.  
   - ASS subtitles are parsed, extracting the script info, styles, and dialogue lines.

3. **Merging**  
   - **SRT**: The script calculates all unique start/end times from both language tracks, combines overlapping lines, and merges Chinese + English text in one block.  
   - **ASS**: The script adds distinct styles for Chinese (top-aligned) and English (bottom-aligned) and writes each line as a separate Dialogue event.

4. **Output**  
   - The final combined subtitles are written as either `.srt` or `.ass`. A BOM (Byte Order Mark) is included to help some players/readers correctly detect UTF-8.

5. **Forced Track Detection**  
   - If one subtitle track has significantly fewer lines (less than half), it warns that it might be a “forced” or partial track.

## Notes & Limitations
- The script relies on simple heuristics to identify “Chinese” or “English” tracks within `.mkv`. If track metadata is incomplete or mislabeled, you may need to pick the right track manually in the prompt.
- For ASS output, the styling is minimal: it sets a top style for Chinese and a bottom style for English. You can further customize the style lines as needed.
- The script merges lines strictly by overlapping times (for SRT). If the original subs do not line up well in time, you may see slightly odd merges.
- **mkvextract** only works on Matroska (`.mkv`) files. If your video is in a different container (e.g., `.mp4`), embedded-extraction features won’t apply.

## Platform-Specific Instructions

### Windows
1. Install [Python 3 for Windows](https://www.python.org/downloads/).  
2. Install [MKVToolNix for Windows](https://mkvtoolnix.download/downloads.html#windows). Ensure `mkvmerge.exe` and `mkvextract.exe` are in your PATH or in the same folder as your script.  
3. Open PowerShell or Command Prompt, navigate to the script’s folder, and run:
   ```powershell
   python .\bilingual_subtitle_merger.py --help
   ```

### Linux / macOS
1. Install Python 3 from your package manager or [python.org](https://www.python.org/downloads/).  
2. Install MKVToolNix:  
   - **Ubuntu/Debian**:
     ```bash
     sudo apt-get install mkvtoolnix
     ```
   - **Fedora**:
     ```bash
     sudo dnf install mkvtoolnix
     ```
   - macOS: [Download from official site](https://mkvtoolnix.download/).  
3. Run the script:
   ```bash
   chmod +x bilingual_subtitle_merger.py
   ./bilingual_subtitle_merger.py --help
   ```

## License
This script is provided *AS IS*, without warranty of any kind. Use at your own risk. You are free to modify and distribute as you see fit.
