#!/usr/bin/env python3
"""
Build script for Bilingual Subtitle Suite (biss.exe).

Creates a self-contained Windows executable that:
- Launches GUI when double-clicked
- Works as CLI when run from PowerShell/CMD
- Bundles all third-party dependencies (PGSRip, tessdata, etc.)

Usage:
    python build.py                            # Build full exe
    python build.py --lite                     # Build lite exe (no tessdata/pgsrip deps)
    python build.py --output-name biss-full    # Custom exe name
    python build.py --clean                    # Clean build artifacts before building
    python build.py --onedir                   # Directory-based distribution

Requirements:
    pip install pyinstaller
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
ENTRY_POINT = ROOT_DIR / "biss.py"
ICON_FILE = ROOT_DIR / "images" / "biss-logo.png"


def find_available_data_files(lite=False):
    """Detect available data files and third-party components to bundle.

    Args:
        lite: If True, skip tessdata and pgsrip python_packages (produces smaller exe).
    """
    datas = []

    # Always bundle images
    images_dir = ROOT_DIR / "images"
    if images_dir.exists():
        for img in images_dir.glob("*.png"):
            datas.append((str(img), "images"))
        print(f"  [+] Images: {images_dir}")

    # Always bundle locale files (i18n)
    locales_dir = ROOT_DIR / "locales"
    if locales_dir.exists() and any(locales_dir.glob("*.json")):
        langs = [f.stem for f in locales_dir.glob("*.json")]
        datas.append((str(locales_dir), "locales"))
        print(f"  [+] Locales: {', '.join(langs)}")
    else:
        print("  [-] Locales: not found (i18n unavailable)")

    if lite:
        print("  [~] Lite build: skipping tessdata, pgsrip package, and pgsrip dependencies")
    else:
        # Bundle tessdata if available
        tessdata_dir = ROOT_DIR / "third_party" / "pgsrip_install" / "tessdata"
        if tessdata_dir.exists() and any(tessdata_dir.glob("*.traineddata")):
            langs = [f.stem for f in tessdata_dir.glob("*.traineddata")]
            datas.append((str(tessdata_dir), os.path.join("third_party", "pgsrip_install", "tessdata")))
            print(f"  [+] Tessdata: {', '.join(langs)}")
        else:
            print("  [-] Tessdata: not found (PGS OCR unavailable in build)")

        # Bundle pgsrip Python package
        pgsrip_dir = ROOT_DIR / "third_party" / "pgsrip_install" / "pgsrip"
        if pgsrip_dir.exists():
            datas.append((str(pgsrip_dir), os.path.join("third_party", "pgsrip_install", "pgsrip")))
            print(f"  [+] PGSRip package: {pgsrip_dir}")
        else:
            print("  [-] PGSRip package: not found")

        # Bundle pgsrip Python dependencies
        pgsrip_packages = ROOT_DIR / "third_party" / "pgsrip_install" / "python_packages"
        if pgsrip_packages.exists():
            datas.append((str(pgsrip_packages), os.path.join("third_party", "pgsrip_install", "python_packages")))
            print(f"  [+] PGSRip dependencies: {pgsrip_packages}")
        else:
            print("  [-] PGSRip dependencies: not found")

    # Bundle pgsrip config (always — wrapper uses it for feature detection)
    pgsrip_config = ROOT_DIR / "third_party" / "pgsrip_install" / "pgsrip_config.json"
    if pgsrip_config.exists():
        datas.append((str(pgsrip_config), os.path.join("third_party", "pgsrip_install")))
        print(f"  [+] PGSRip config: {pgsrip_config}")

    # Always bundle pgsrip wrapper
    pgsrip_wrapper = ROOT_DIR / "third_party" / "pgsrip_wrapper.py"
    if pgsrip_wrapper.exists():
        print(f"  [+] PGSRip wrapper: {pgsrip_wrapper}")

    return datas


def get_hidden_imports():
    """Get list of hidden imports for PyInstaller."""
    hidden = [
        # Core app modules (imported dynamically in some paths)
        "core",
        "core.subtitle_formats",
        "core.video_containers",
        "core.encoding_detection",
        "core.language_detection",
        "core.timing_utils",
        "core.similarity_alignment",
        "core.translation_service",
        "core.track_analyzer",
        "core.ass_converter",
        "processors",
        "processors.merger",
        "processors.converter",
        "processors.realigner",
        "processors.timing_adjuster",
        "processors.batch_processor",
        "processors.splitter",
        "processors.bulk_aligner",
        "ui",
        "ui.cli",
        "ui.gui",
        "ui.interactive",
        "utils",
        "utils.constants",
        "utils.logging_config",
        "utils.file_operations",
        "utils.backup_manager",
        "utils.i18n",
        "third_party",
        "third_party.pgsrip_wrapper",
        # Third-party pip packages
        "requests",
        "pysrt",
    ]

    # Optional packages — include if available
    optional = [
        ("charset_normalizer", "charset_normalizer"),
        ("PIL", "PIL"),
        ("PIL.Image", "PIL.Image"),
        ("PIL.ImageTk", "PIL.ImageTk"),
        ("dotenv", "dotenv"),
    ]

    for module, import_name in optional:
        try:
            __import__(module)
            hidden.append(import_name)
            print(f"  [+] Optional: {module}")
        except ImportError:
            print(f"  [-] Optional: {module} (not installed)")

    return hidden


def convert_icon(png_path):
    """Convert PNG to ICO for Windows exe icon. Returns ICO path or None."""
    try:
        from PIL import Image
        ico_path = png_path.parent / "biss-logo.ico"
        img = Image.open(png_path)
        # Create multi-resolution icon
        img.save(str(ico_path), format='ICO',
                 sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print(f"  [+] Icon: {ico_path}")
        return ico_path
    except Exception as e:
        print(f"  [-] Icon conversion failed: {e}")
        return None


def build(onefile=True, clean=False, lite=False, output_name="biss"):
    """Run PyInstaller build.

    Args:
        onefile: Build single-file exe (True) or directory distribution (False).
        clean: Remove previous build artifacts before building.
        lite: Skip tessdata and pgsrip dependencies for a smaller exe.
        output_name: Base name for the output executable.
    """
    build_label = f"{'Lite' if lite else 'Full'} Build"
    print("=" * 60)
    print(f"Bilingual Subtitle Suite - {build_label}")
    print("=" * 60)

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"\nPyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("\nERROR: PyInstaller not installed. Run: pip install pyinstaller")
        return 1

    # Clean previous builds
    if clean:
        print("\nCleaning previous builds...")
        for d in [BUILD_DIR, DIST_DIR]:
            if d.exists():
                shutil.rmtree(d)
                print(f"  Removed: {d}")

    # Detect components
    print("\nDetecting components...")
    datas = find_available_data_files(lite=lite)

    print("\nDetecting imports...")
    hidden_imports = get_hidden_imports()

    # Convert icon
    icon_path = None
    if ICON_FILE.exists():
        icon_path = convert_icon(ICON_FILE)

    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", output_name,
        "--console",  # Console app: CLI works; GUI hides console automatically
        "--noconfirm",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Add icon
    if icon_path:
        cmd.extend(["--icon", str(icon_path)])

    # Add data files
    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # Add hidden imports
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    # Exclude unnecessary large packages
    excludes = [
        "matplotlib", "numpy", "scipy", "pandas",
        "pytest", "unittest", "test",
        "google.cloud",
    ]
    for exc in excludes:
        cmd.extend(["--exclude-module", exc])

    # Add entry point
    cmd.append(str(ENTRY_POINT))

    print(f"\nBuilding {'single-file' if onefile else 'directory'} executable...")
    print(f"Command: {' '.join(cmd[:6])}... ({len(cmd)} args)")

    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if result.returncode == 0:
        exe_name = f"{output_name}.exe"
        if onefile:
            exe_path = DIST_DIR / exe_name
        else:
            exe_path = DIST_DIR / output_name / exe_name

        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful!")
            print(f"  Output: {exe_path}")
            print(f"  Size:   {size_mb:.1f} MB")
            print(f"\nUsage:")
            print(f"  Double-click {exe_name}       -> GUI mode")
            print(f"  {exe_name} merge file.mkv     -> CLI mode")
            print(f"  {exe_name} --help             -> Show help")
        else:
            print(f"\nWARNING: Build completed but exe not found at {exe_path}")
        return 0
    else:
        print(f"\nBuild failed with exit code {result.returncode}")
        return 1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build biss.exe")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--onefile", action="store_true", default=True,
                      help="Build single-file exe (default)")
    mode.add_argument("--onedir", action="store_true",
                      help="Build directory-based distribution")
    parser.add_argument("--clean", action="store_true",
                        help="Clean build artifacts before building")
    parser.add_argument("--lite", action="store_true",
                        help="Lite build: skip tessdata and pgsrip dependencies")
    parser.add_argument("--output-name", default="biss",
                        help="Base name for the output executable (default: biss)")
    args = parser.parse_args()

    onefile = not args.onedir
    return build(onefile=onefile, clean=args.clean, lite=args.lite,
                 output_name=args.output_name)


if __name__ == "__main__":
    sys.exit(main())
