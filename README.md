# Bilingual Subtitle Merger

This Python script merges **Chinese** and **English** subtitles into a single synchronized subtitle track. It can:

1. **Look for external** `.srt` or `.ass` files for both languages.
2. **Automatically extract** embedded subtitle tracks from videos (in `.mkv`, `.mp4`, `.m4v`, `.avi`, etc.) using **FFmpeg**.
3. **Combine** the two languages (Chinese on top, English on bottom in ASS mode, or merged lines in SRT mode) into one **bilingual subtitle**.

## Screenshots

Below are example images demonstrating the output of the script:

| Image                                             | Description                                       |
|---------------------------------------------------|---------------------------------------------------|
| ![Official Combined Subtitles](example/houseofficial.jpg) | An example of official combined subtitles. |
| ![Script Output](example/fma03script.png)                 | An example produced by the script.      |

---

## Table of Contents
1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Usage Overview](#usage-overview)
5. [Command-Line Arguments](#command-line-arguments)
6. [Detailed Operation Modes](#detailed-operation-modes)
7. [Examples](#examples)
8. [Real-World Example (Eden of the East)](#real-world-example-eden-of-the-east)
9. [How It Works Internally](#how-it-works-internally)
10. [Notes & Caveats](#notes--caveats)
11. [Platform-Specific Instructions](#platform-specific-instructions)
12. [License](#license)

---

## Features

1. **Automatic Language Detection**  
   - Locates **external** `.zh.srt` / `.zh.ass` (or `.en.srt` / `.en.ass`) for Chinese/English in the same directory as your video.  
   - If not found, tries to **extract** them from embedded subtitle streams using `ffprobe` + `ffmpeg`.

2. **Multiple Subtitle Formats**  
   - Supports merging to either **SRT** (`--format srt`) or **ASS** (`--format ass`).

3. **Merged/Stacked Bilingual Output**  
   - **SRT**: Merges time segments so lines read:
     ```
     这是一句中文
     This is an English line
     ```
   - **ASS**: Uses two styles:
     - A top-aligned style for Chinese text.
     - A bottom-aligned style for English text.

4. **Heuristic Forced-Track Check**  
   - If one subtitle track is <5% the number of lines as the other, the script warns that it might be a “forced” (partial) subtitle.

5. **Bulk Mode**  
   - Processes all media files (`.mkv`, `.mp4`, `.mov`, etc.) in a given directory for **batch merging**.

6. **Remapping & Track Selection**  
   - `--remap-eng <lang>` or `--remap-chi <lang>` helps treat unusual language codes as English/Chinese.  
   - `--eng-track` or `--chi-track` can target a specific track ID if you already know it.

7. **Output Naming**  
   - Default output is **`<videobasename>.zh-en.srt`** or **`.zh-en.ass`**, so you can easily identify the merged subtitles.

8. **UTF-8 Compatible**  
   - Writes out a **UTF-8** BOM to ensure better compatibility with media players.

---

## Requirements

1. **Python 3.6+**  
   - Verify with `python --version` or `python3 --version`.

2. **FFmpeg**  
   - Must be installed and accessible in your system’s `PATH`.
   - Check installation by running `ffmpeg -version` in a terminal.

3. **A UTF-8 Environment** (especially on Windows)  
   - If you see odd encoding issues, ensure your console is set to UTF-8. For PowerShell, you may run:
     ```powershell
     chcp 65001
     ```
     or ensure your editor/IDE is using UTF-8.

No other external tools (like `mkvextract` or `mkvmerge`) are needed — all containers, including `.mkv`, are handled by FFmpeg’s built-in support.

---

## Installation

1. **Download/Copy** the script to your machine (e.g., `bilingual_subtitle_merger.py`).
2. **(Optional) Make Executable** on Linux/macOS:
   ```bash
   chmod +x bilingual_subtitle_merger.py
   ```
3. **Ensure FFmpeg** is installed:
   - **Windows**: 
     ```powershell
     winget install Gyan.FFmpeg
     # or get the static build from https://ffmpeg.org/
     ```
   - **Linux**:
     ```bash
     sudo apt-get install ffmpeg
     ```
   - **macOS**:
     ```bash
     brew install ffmpeg
     ```

4. **Check** that running `ffmpeg` in your terminal works without error.

---

## Usage Overview

Use:

```
python bilingual_subtitle_merger.py [OPTIONS]
```

- On some systems, replace `python` with `python3`.
- For quick help, run:
  ```
  python bilingual_subtitle_merger.py --help
  ```

---

## Command-Line Arguments

| Short / Long            | Description                                                                                                                                   | Example                                        |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------|
| **-v**, `--video`       | Video file to analyze (`.mkv`, `.mp4`, `.m4v`, `.mov`, `.avi`, etc.). Script tries to find or extract Chinese/English subs if none are given. | `-v "MyVideo.mkv"`                             |
| **-e**, `--english`     | External English subtitle file (`.srt` or `.ass`).                                                                                            | `-e "MyVideo.en.srt"`                          |
| **-c**, `--chinese`     | External Chinese subtitle file (`.srt` or `.ass`).                                                                                            | `-c "MyVideo.zh.ass"`                          |
| **-o**, `--output`      | Output filename for the merged subtitles. Defaults to `<video_basename>.zh-en.srt` (or `.ass`) if not specified.                              | `-o "MergedSubs.srt"`                          |
| **-f**, `--format`      | Output format: `srt` or `ass`. Default = `srt`.                                                                                               | `-f ass`                                       |
| **--bulk**              | Bulk-process all media files in a directory. If `--video` is given as a folder, processes that folder; else processes current directory.      | `--bulk`                                       |
| **--remap-eng**         | Treat tracks labeled with this language code as **English**.                                                                                 | `--remap-eng jpn`                              |
| **--remap-chi**         | Treat tracks labeled with this language code as **Chinese**.                                                                                 | `--remap-chi jpn`                              |
| **--eng-track**         | Force usage of a specific track number for English.                                                                                          | `--eng-track 0:3`                              |
| **--chi-track**         | Force usage of a specific track number for Chinese.                                                                                          | `--chi-track 0:4`                              |
| **--prefer-external**   | Prefer any detected external `.en/.zh.srt/.ass` over embedded tracks.                                                                         | `--prefer-external`                            |
| **--prefer-embedded**   | Prefer embedded tracks over external subtitle files.                                                                                          | `--prefer-embedded`                            |
| **--debug**             | Enables debug-level logging (lots of detail).                                                                                                 | `--debug`                                      |
| **-h**, `--help`        | Show help message and exit.                                                                                                                   | `--help`                                       |

---

## Detailed Operation Modes

1. **Merge Two External Files**  
   - Provide `-e` and `-c`, no `--video`.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py \
       --english "MyShow.en.srt" \
       --chinese "MyShow.zh.srt" \
       --output "MyShow.zh-en.srt"
     ```
   - **No** embedded track extraction occurs; script simply merges.

2. **Single Video (Auto)**  
   - Provide `-v <file>`.  
   - Script tries to find external `.en.srt/.ass` or `.zh.srt/.ass`.  
   - If not found, attempts to **ffprobe** the video and **extract** a likely English and Chinese track.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py \
       --video "Episode01.mkv" \
       --format srt
     ```

3. **Video + One External**  
   - If you only have, say, a Chinese subtitle externally, specify `--chinese`.  
   - The script will look for an English track in the video or vice versa.

4. **Bulk Mode**  
   - Use `--bulk` to process all videos in a folder.  
   - If you do `--video <folder>` it processes that entire folder. If you do not specify `--video`, it uses the **current directory**.  
   - Example:
     ```bash
     python bilingual_subtitle_merger.py --bulk
     ```

5. **Remapping & Forcing Track IDs**  
   - If your English track is incorrectly labeled as `jpn`, do `--remap-eng jpn`.  
   - If you know exactly which embedded track ID you want, do `--eng-track 0:3` for English and/or `--chi-track 0:4` for Chinese.

6. **Preference for External vs. Embedded**  
   - By default, the script tries external first, then embedded.  
   - If you explicitly want to prefer external, pass `--prefer-external`.  
   - If you prefer embedded, pass `--prefer-embedded`.  
   - If both are given, the script logs a warning and resets to default behavior (external first if found).

---

## Examples

### Example 1: Directly Merge Two External Files
```bash
python bilingual_subtitle_merger.py \
  -e "Movie.en.srt" \
  -c "Movie.zh.srt" \
  -o "Movie.zh-en.srt"
```
- Outputs a single SRT combining both English and Chinese lines.

### Example 2: Single MKV (No External Provided)
```bash
python bilingual_subtitle_merger.py \
  --video "AnimeEpisode.mkv" \
  --format ass
```
- The script looks for `AnimeEpisode.en.*` or `.zh.*` in the folder. If none found, it checks for embedded subs in the MKV.  
- Merged output is `AnimeEpisode.zh-en.ass`.

### Example 3: Bulk Mode on Current Folder
```bash
python bilingual_subtitle_merger.py --bulk
```
- Finds all `.mkv`, `.mp4`, `.mov`, etc. in the current directory, merges Chinese + English subs for each.

### Example 4: Re-map Japanese as English
If you have an anime where track language is labeled “jpn” but it’s actually an English fansub:
```bash
python bilingual_subtitle_merger.py \
  --video "AnimeEpisode.mkv" \
  --remap-eng jpn
```
- The script looks for a track labeled `jpn` and treats it as English.

### Example 5: Force Output in SRT and Custom Output Name
```bash
python bilingual_subtitle_merger.py \
  -v "Show.mkv" \
  -f srt \
  -o "Show.simplified.zh-en.srt"
```

---

## Real-World Example (Eden of the East)

Consider a folder of episodes named like `Eden.of.the.East.S01E01.v2.1080p-Hi10p.BluRay.FLAC5.1.x264-CTR.[0426FF42].mkv` and so on. Perhaps you already have `.zh.ass` files, or you want the script to merge them with embedded English signs.

**Check your streams** with FFmpeg:
```powershell
PS Z:\Videos\Anime Shows\Eden of the East (2009)\Season 01> ffmpeg -i "Eden.of.the.East.S01E01.v2.1080p-Hi10p.BluRay.FLAC5.1.x264-CTR.[0426FF42].mkv"
```
You might see something like:

> ```
> Stream #0:3(eng): Subtitle: ass (ssa) (default) (forced)
>   Metadata:
>     title           : Signs [Coalgirls]
> [...]
> Stream #0:4(jpn): Subtitle: ass (ssa)
>   Metadata:
>     title           : Subtitles [Coalgirls]
> [...]
> ```

If you suspect `jpn` track is your “English” translation, or want to override its code, you can run:

```powershell
PS Z:\Videos\Anime Shows\Eden of the East (2009)\Season 01> python C:\bilingual_subtitle_merger.py --bulk --remap-eng jpn
```

This will:

1. **Bulk process** every `.mkv` in `Season 01`.
2. Treat any `jpn`-tagged subtitles as if they were English.
3. Look for `.zh.srt` or `.zh.ass` in the same folder to handle Chinese (if present).
4. Create merged SRT or ASS subtitles (default is SRT) named `Eden.of.the.East.S01E01.v2.1080p-Hi10p.BluRay.FLAC5.1.x264-CTR.[0426FF42].zh-en.srt`, etc.

---

## How It Works Internally

1. **Locates Subtitles**  
   - If **external** subs are explicitly given (`-e` / `-c`), those override everything for that language.  
   - Otherwise, the script checks for local external files: `*.en.srt`, `*.en.ass`, `*.zh.srt`, `*.zh.ass` in the same directory.  
   - If none are found, it uses **FFmpeg** to `ffprobe` the video, analyzing its subtitle streams.

2. **Extracts with FFmpeg**  
   - The script calls FFmpeg with `-map <track>` and tries to convert or copy the subtitles.  
   - By default, it tries to convert to either `.ass` or `.srt`, or do a “copy” if the input track is already the correct format.

3. **Parses**  
   - SRT input is parsed line-by-line, extracting times and text blocks.  
   - ASS input is parsed to extract `dialogue:` lines and style info.

4. **Merging**  
   - **SRT**:  
     - Finds all unique time segments.  
     - Overlaps lines that appear at the same time, appending them with a line break.  
     - Avoids flicker by combining adjacent segments if they have identical text.  
   - **ASS**:  
     - Creates two styles: `Chinese` (aligned top-center) and `English` (aligned bottom-center).  
     - Writes each event with the appropriate style.  

5. **Writes Output**  
   - SRT or ASS, with a UTF-8 BOM for broad media player compatibility.  
   - Named either as specified (`--output`), or automatically `<video_basename>.zh-en.<ext>`.

6. **Forces Check**  
   - If the line count for one language is drastically lower (less than half) compared to the other, logs a warning that it might be forced or partial.

---

## Notes & Caveats

- **Encodings**: The script tries multiple encodings (`utf-8`, `latin-1`, `cp1252`, `gbk`, etc.) to read existing subtitles. If it fails for an extremely unusual encoding, you may need to convert them manually.
- **Alignment in ASS**: The default styling is top for Chinese, bottom for English. You can edit the resulting `.ass` file to tweak fonts, sizes, alignment, etc.
- **Overlapping Subtitles**: In SRT, lines that overlap in time are combined. If your subs are out-of-sync, you might see partial merges or short display times.
- **Forcing Tracks**: If your video has multiple English or Chinese tracks, you can specify exactly which track ID to pick with `--eng-track` / `--chi-track`.
- **No mkvmerge / mkvextract**: This script exclusively uses FFmpeg for all containers (including MKVs).

---

## Platform-Specific Instructions

### Windows

1. Install [Python 3](https://www.python.org/downloads/) or use the Windows Store app.  
2. Install FFmpeg (e.g. `winget install Gyan.FFmpeg`).
3. Open **Command Prompt** or **PowerShell**:
   ```powershell
   cd "C:\path\to\folder\with\script"
   python .\bilingual_subtitle_merger.py --help
   ```
4. **(Optional)** use `chcp 65001` to set console to UTF-8 if you see encoding issues.

### Linux

1. `sudo apt-get install python3 ffmpeg` (Ubuntu/Debian)  
2. Place the script wherever you like, `chmod +x bilingual_subtitle_merger.py`, and run:
   ```bash
   ./bilingual_subtitle_merger.py --help
   ```
3. If you want it globally available, move it to `/usr/local/bin` or similar.

### macOS

1. Install [Python 3](https://www.python.org/downloads/) or via Homebrew: `brew install python`.
2. Install FFmpeg: `brew install ffmpeg`.
3. Run:
   ```bash
   python3 bilingual_subtitle_merger.py --help
   ```
4. You may need to allow the script to be run in Security & Privacy settings if you get permission prompts.

---

## License

This script is provided “**AS IS**,” without warranty of any kind. You may use, modify, or distribute it at your own discretion. The author is **not liable** for any potential issues or damages arising from its use. Enjoy merging your bilingual subtitles!
