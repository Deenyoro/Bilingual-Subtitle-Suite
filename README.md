# Bilingual Subtitle Merger

A Python script to **automatically merge** English and Chinese subtitles into a single subtitle track. It can handle both external `.srt` or `.ass` subtitle files or **extract** embedded subtitle tracks from any container supported by:

- [MKVToolNix](https://mkvtoolnix.download/) for **MKV** files  
- [FFmpeg](https://ffmpeg.org/) for **MP4**, **MOV**, **AVI**, **FLV**, **TS**, and other containers  

Additionally, it can perform **bulk operations** on all relevant video files in a folder.

---

## Features

1. **Automatic Detection**  
   - Looks for **external** Chinese (`.zh.srt`, `.zh.ass`, etc.) or English (`.en.srt`, `.en.ass`, etc.) subtitle files **in the same folder**.  
   - If no external file is found, the script will attempt to **extract** them from embedded tracks using `mkvextract` (for MKV) or `ffmpeg` (for everything else).  
   - Prompts you to pick a track if multiple candidates match.

2. **Multiple Formats**  
   - Supports merging and outputting as **SRT** (SubRip `.srt`) or **ASS** (Advanced SubStation Alpha `.ass`).

3. **Bilingual Output**  
   - **SRT**: Merges Chinese and English text by overlapping time segments, producing blocks with `Chinese\nEnglish`.  
   - **ASS**: Utilizes two different styles (top-aligned for Chinese, bottom-aligned for English).

4. **Heuristic Check for Forced/Partial Subtitles**  
   - Warns if one track is significantly shorter than the other (less than half the line count).

5. **Bulk Mode**  
   - Automatically process an entire directory of media files (`.mkv`, `.mp4`, `.m4v`, `.mov`, `.avi`, `.flv`, `.ts`) to generate bilingual subtitles for each.

6. **Flexible Container Support**  
   - **MKV**: Uses `mkvmerge`/`mkvextract` to read and extract subtitles.  
   - **MP4/MOV/AVI/etc.**: Uses **FFmpeg** to detect and extract embedded subtitles.

7. **Naming Convention**  
   - By default, if no output path is specified, the script creates **`<video_basename>.zh-en.srt`** or **`<video_basename>.zh-en.ass`**, ensuring easy identification in media players like Plex.

---

## Requirements

1. **Python 3**  
   - Verify with `python --version` or `python3 --version`.

2. **MKVToolNix** (for handling embedded subtitles in MKV):
   - Install from official site or your package manager.  
   - **Windows** (PowerShell):
     ```powershell
     winget install MoritzBunkus.MKVToolNix
     ```
   - **Linux**:
     ```bash
     sudo apt-get install mkvtoolnix
     # or
     sudo dnf install mkvtoolnix
     ```
   - **macOS**: [Download from official site](https://mkvtoolnix.download/).

   Ensure `mkvmerge` and `mkvextract` are in your PATH.

3. **FFmpeg** (for handling embedded subtitles in MP4, MOV, etc.):
   - Official site: <https://ffmpeg.org>  
   - **Windows** (PowerShell):
     ```powershell
     winget install Gyan.FFmpeg
     ```
   - **Linux**:
     ```bash
     sudo apt-get install ffmpeg
     ```
   - **macOS**:
     ```bash
     brew install ffmpeg
     ```
   Make sure `ffmpeg` is available in your system PATH.

4. **UTF-8 Environment**  
   - Subtitles are processed in UTF-8. If you see encoding issues, set your locale to UTF-8.  
   - On Windows, you can use `chcp 65001` in CMD or PowerShell.

---

## Installation

1. **Obtain the script**: Copy or download `bilingual_subtitle_merger.py`.
2. **(Optional) Make executable** on Linux/macOS:
   ```bash
   chmod +x bilingual_subtitle_merger.py
   ```
3. **Verify** that `mkvextract`/`mkvmerge` (if dealing with MKVs) **and** `ffmpeg` (for other containers) are accessible in your PATH.

---

## Usage

### Basic Command
```bash
python bilingual_subtitle_merger.py [options]
```
*(On some systems, you may need `python3`.)*  
```bash
python3 bilingual_subtitle_merger.py [options]
```

### Command-Line Arguments

| Option               | Description                                                                                                 |
|----------------------|-------------------------------------------------------------------------------------------------------------|
| **-v, --video**      | Path to a video file (e.g. `.mkv`, `.mp4`). Will auto-detect or extract Chinese/English subs if none given. |
| **-e, --english**    | Path to an external English subtitle (`.srt` or `.ass`).                                                    |
| **-c, --chinese**    | Path to an external Chinese subtitle (`.srt` or `.ass`).                                                    |
| **-o, --output**     | Path to output file (e.g. `MyBilingualSubs.srt`). Default: `<video_basename>.zh-en.srt`/`.ass`.            |
| **-f, --format**     | Output format: `srt` or `ass`. Default is `srt`.                                                            |
| **--bulk**           | Process **all** relevant media files in a directory.                                                        |
| **--help**           | Show help text.                                                                                             |

### Operation Modes

1. **Merge External-Only**  
   - Provide **both** `-e` and `-c` with no `-v`.  
   - Example:  
     ```bash
     python bilingual_subtitle_merger.py -e Movie.en.srt -c Movie.zh.srt -o Movie.zh-en.srt
     ```
   - Merges directly, ignoring embedded subtitles.

2. **Single Video Auto**  
   - Provide `-v <movie>` to detect or extract both languages.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --video "Movie.mkv"
     ```
     - Searches for external `.en.srt` / `.zh.srt` in the same folder.
     - If not found, scans embedded tracks to pick English and Chinese.

3. **Video + One External**  
   - Supply `-v` plus `-e` **or** `-c`.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --video "Movie.mp4" --chinese "Movie.zh.ass"
     ```
     - Uses the external `.ass` for Chinese.
     - Searches or extracts English from `Movie.mp4`.

4. **Bulk Mode**  
   - Use `--bulk` with an optional folder.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --bulk
     ```
     - Processes all `.mkv`, `.mp4`, etc. in the current folder.

---

## Examples

### Example 1: Merge Two External SRT Files
**Windows**:
```powershell
python .\bilingual_subtitle_merger.py -e "MyMovie.en.srt" -c "MyMovie.zh.srt" -o "MyMovie.zh-en.srt"
```
**Linux/macOS**:
```bash
python3 bilingual_subtitle_merger.py -e MyMovie.en.srt -c MyMovie.zh.srt -o MyMovie.zh-en.srt
```
- No `-v/--video`. Just merges the two external files.

### Example 2: Single MKV With Embedded English, External Chinese
```bash
python bilingual_subtitle_merger.py --video "MyMovie.mkv" --chinese "MyMovie.zh.srt"
```
- Uses `MyMovie.zh.srt` for Chinese.  
- Searches the MKV for English subs. If multiple are found, prompts you to pick.

### Example 3: Bulk Mode on All Files in Current Directory
```bash
python bilingual_subtitle_merger.py --bulk
```
- Finds all `.mkv`, `.mp4`, `.mov`, etc. in the current folder.  
- Attempts to produce `<filename>.zh-en.srt` or `.ass` for each.

### Example 4: Force Output in ASS Format
```bash
python bilingual_subtitle_merger.py -v "MyMovie.mkv" -f ass
```
- Creates **`MyMovie.zh-en.ass`** with top-aligned Chinese and bottom-aligned English.

---

## How It Works

1. **Collecting Subtitles**  
   - Tries `--english`, `--chinese` if provided.  
   - If those are missing, looks for external `.en.srt/.ass` or `.zh.srt/.ass` next to the video.  
   - If still missing, tries **embedded** track extraction:  
     - **MKV**: uses `mkvmerge`/`mkvextract`.  
     - **MP4 / MOV / AVI / etc.**: uses `ffmpeg -i` to list tracks, then extracts the chosen one with `-map`.

2. **Parsing**  
   - **SRT**: Splits based on numeric index and `HH:MM:SS,ms --> HH:MM:SS,ms`.  
   - **ASS**: Reads styles, script info, and dialogue lines.

3. **Merging**  
   - For **SRT**: calculates unique time segments across both languages, merging overlapping lines into a single block with line breaks.  
   - For **ASS**: assigns a top style to Chinese, bottom style to English, and writes each line with the correct style.

4. **Writing Output**  
   - Appends BOM (Byte Order Mark) to ensure most players see it as UTF-8.  
   - Default name is `<video_basename>.zh-en.srt`/`.ass`.

5. **Forced Track Heuristic**  
   - If one track is < 50% the line count of the other, warns it may be forced or partial.

---

## Notes & Limitations

- **Manual Track Selection**  
  If your tracks aren’t labeled properly, you’ll be prompted to choose from a list of subtitle streams.
- **Minimal ASS Styling**  
  The script sets two baseline styles (one top, one bottom). You can customize them further in the output `.ass` if desired.
- **Time Overlaps**  
  The merged lines in SRT rely on time overlap. If your subtitles are misaligned, you may see unexpected merges or splits.
- **FFmpeg** is used for **non-MKV** containers. If your container isn’t recognized, try renaming to a standard extension or using `--english/--chinese` explicitly.

---

## Platform-Specific Notes

### Windows
1. **Install Python 3** from [python.org](https://www.python.org/downloads/) or Windows Store.  
2. **Install MKVToolNix** (if dealing with MKV):
   ```powershell
   winget install MoritzBunkus.MKVToolNix
   ```
3. **Install FFmpeg** (if dealing with MP4/MOV/etc.):
   ```powershell
   winget install Gyan.FFmpeg
   ```
4. Ensure `mkvextract`, `mkvmerge`, and `ffmpeg` are in your PATH or in the same folder as your script.  
5. Run the script:
   ```powershell
   python .\bilingual_subtitle_merger.py --help
   ```

### Linux / macOS
1. **Install Python 3** (`sudo apt-get install python3`, `brew install python`, etc.).  
2. **Install MKVToolNix** (for MKV):
   ```bash
   sudo apt-get install mkvtoolnix
   # or for Fedora:
   sudo dnf install mkvtoolnix
   # macOS:
   #   Download from https://mkvtoolnix.download/ or use homebrew
   ```
3. **Install FFmpeg**:
   ```bash
   sudo apt-get install ffmpeg
   ```
   or  
   ```bash
   brew install ffmpeg
   ```
4. Mark the script executable (optional):
   ```bash
   chmod +x bilingual_subtitle_merger.py
   ```
5. Run:
   ```bash
   ./bilingual_subtitle_merger.py --help
   ```

---

## License

This script is provided **AS IS**, without warranty of any kind. Use at your own risk. You are free to modify and distribute it as you see fit.
