# Changelog

All notable changes to Bilingual Subtitle Suite are listed here.

## [2.2.2] - 2026-09-24

Build and release changes only; the app itself is unchanged.

### Added
- GitLab CI pipeline (`.gitlab-ci.yml`) that replaces the GitHub Actions release workflow. It runs on `v*` tags and on manual web/API runs, never on plain pushes.
  - **test** (Linux, Python 3.11): `python -m unittest discover -s tests` under Xvfb. For a release it also checks that `APP_VERSION` matches the tag and that this file has an entry for the version.
  - **build-windows-lite / build-windows-full** (Windows runner): build `biss.exe` and `biss-full.exe` with `build.py`, using Python 3.11.9 + Tk from pinned, SHA-256-checked downloads (`ci/tools-windows.ps1`) and PyInstaller 6.22.3 version-pinned (`ci/requirements-build.txt`). The full build bundles pinned Tesseract data (eng, chi_sim, chi_tra, jpn, kor) and `pgsrip==0.2.1` (`ci/prepare-full-windows.ps1`). `ci/check-exe.ps1` smoke-tests each exe.
  - **release** (`v*` tags or `RELEASE_VERSION`): `build-windows-full` uploads `biss-full.exe` straight to the GitLab Package Registry (`ci/publish-windows.ps1`; it is too large to be a job artifact), the release job uploads `biss.exe` and creates or updates the GitLab release. Neither overwrites a file that is already published.
- README: "Building / Releases (GitLab CI)" section.

### Changed
- Releases are built and published on GitLab only (GitHub Actions is disabled). The README download links now point to GitLab Releases; older releases stay on GitHub Releases.

## [2.2.1] - 2026-09-24

Changes since v2.2.0 (commit 84da642).

### Already on master before this round of fixes (since v2.2.0)
- New `biss sync` command: auto-aligns external subtitles to an embedded video track.
- **Behaviour change:** `merge` now runs auto-sync timing detection by default before merging (use `--no-auto-sync` to turn it off).
- Post-anchor validation to prevent false realignment during sync.
- ASS font fixing and ASS-to-ASS merge support.
- HTML tags are stripped in ASS output; bilingual subtitle files are detected.
- README: English is the default again; the Chinese README moved to README.zh.md.

### Fixed
- `biss batch-convert <folder> --parallel` no longer crashes with "name 'Tuple' is not defined"; parallel conversion works again.
- GUI error dialogs now show the real error message. Before, 13 background tasks crashed with a NameError while trying to report an error, so the user never saw it.
- Batch > "Merge from videos" in the GUI no longer hangs on an invisible console prompt in the packaged exe. It also now honours "Include subdirectories", only counts video files, moves the progress bar, and can be cancelled.
- Successful GUI batch conversions are no longer reported as "Batch operation failed" (the GUI read a result key that did not exist).
- The Merge tab's "Language" choice now actually selects which embedded track is used; it was ignored before.
- Tools menu entries open the right tab (they were off by one since Split was added).
- Embedded-track Preview works again (it passed a track id where a track object was expected).
- The saved merged file now puts on top the track the window says is on top, including after Swap Tracks and for Korean, kana-only Japanese, or French + English. The track titles ("Top Subtitle" / "Bottom Subtitle") follow the "On top" choice.
- A background language check can no longer swap Track 1 and Track 2 after Merge is clicked or while the "Replace?" dialog is open.
- Shift > Match a video: the output file is written only after the offset is detected, so a failed sync no longer leaves an unshifted ".shifted.srt" or destroys an earlier good file.
- Batch > Convert encoding with "Keep backups" and "Include subfolders" no longer re-converts the files in `subtitle_backups/` on a second run.
- Batch > Merge failure rows explain the cause (translated), including when FFmpeg is missing, instead of a raw English log line.
- The header logo and the window/taskbar icon now show in the exe (they needed Pillow, which the build excludes).
- Crash with Tk 9 (canvas sizes returned with units) fixed.
- The status bar no longer shows an old result next to a newer action-bar message, and no longer repeats the action bar word for word; it shows the output folder.
- Controls that need FFmpeg (Detect Offset, Load Tracks, Sync Subtitle) are disabled with an explanation while FFmpeg is missing, instead of failing on click.

### Changed
- GUI redesign: every tab has a scrolling body and a fixed action bar (status, progress, Cancel, main button), so the main button is visible on 1366x768 screens and at 150% scaling. The log moved into a collapsible Details pane (View > Show Details, Ctrl+L).
- The GUI no longer freezes: file parsing, language/encoding detection and tool checks run in the background.
- Results show the saved file with Open folder and Preview; errors show the actual reason; bad input (e.g. an offset of "1.5 minutes") gets an inline explanation.
- Merge, Shift, ASS to SRT and PGS ask "Replace X?" before overwriting an existing output file.
- Shift saves "name.shifted.srt" by default ("Overwrite the original" is an explicit option); the offset starts empty and Apply is enabled only for a valid, non-zero offset.
- Missing FFmpeg or MKVToolNix is shown as a banner with Check again, Locate folder and Download page on every screen that needs it, including Batch > Merge from videos.
- Native look on Windows (vista theme, Segoe UI, DPI-aware sizing, sharp text at 125-200%), consistent colours and spacing.
- The translation option is disabled, with an explanation, when no API key is configured.
- On Windows, track previews reuse one `%TEMP%\biss-preview` folder instead of leaving new temp folders behind.
- CLI behaviour is unchanged by this round of fixes (the new `sync` command and the auto-sync default are listed above); all new merger/batch options are keyword-only with CLI-compatible defaults.

### Added
- Full GUI translation into Chinese, Japanese and Korean; View > Language switches in place without a restart.
- Drag and drop from Explorer onto the Merge tab, path fields and every tab's main input (when tkinterdnd2 is available).
- "Add subtitle files..." picks both files at once and places each on the right track by language.
- Shift Timing > "Match a video (automatic)".
- Batch results are listed live, one row per file, with the failure reason.
- Remembered GUI settings (last folders, window size/position, tab, options) in `%APPDATA%\BISS\gui_settings.json` (`~/.config/biss` elsewhere; `BISS_CONFIG_DIR` overrides).
- Friendly offset input: "-2.5s", "+1500ms", "1.5 seconds", "HH:MM:SS,mmm".
- Keyboard shortcuts: Ctrl+1-6 for tabs, Ctrl+Tab, Ctrl+Enter for the current tab's action; a Split entry in the Tools menu.
- New `ui/gui_support.py` and `ui/widgets.py` modules, and pre-sized logo/icon PNGs in `images/`.
- First automated tests (`python -m unittest discover -s tests`): batch conversion, batch/merge GUI hooks, merge track order, sync-to-new-file, GUI support helpers, i18n completeness and GUI smoke tests. Test scratch folders go under `<temp>/biss-tests`.

### Dependencies
- Added `tkinterdnd2==0.6.3` (optional at runtime; pinned because the release build bundles its native tkdnd library).

### CI / Build
- Both release jobs in `.github/workflows/release.yml` install `tkinterdnd2==0.6.3`.
- `build.py` and `biss.spec` bundle tkinterdnd2 and its tkdnd library when installed (a build without it still works).

### Version
- Version bumped to 2.2.1 (`utils/constants.py` `APP_VERSION`, shown by `biss --version`, the GUI header and About dialog; `biss.py` docstring).
