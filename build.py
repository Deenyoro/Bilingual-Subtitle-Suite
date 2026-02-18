#!/usr/bin/env python3
"""
Build script for Bilingual Subtitle Suite (biss.exe).

Creates a self-contained Windows executable that:
- Launches GUI when double-clicked
- Works as CLI when run from PowerShell/CMD
- Bundles all third-party dependencies (PGSRip, tessdata, etc.)

Usage:
    python build.py              # Build with auto-detected components
    python build.py --onefile    # Single-file exe (default)
    python build.py --onedir     # Directory-based distribution
    python build.py --clean      # Clean build artifacts before building

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


def find_available_data_files():
    """Detect available data files and third-party components to bundle."""
    datas = []

    # Always bundle images
    images_dir = ROOT_DIR / "images"
    if images_dir.exists():
        for img in images_dir.glob("*.png"):
            datas.append((str(img), "images"))
        print(f"  [+] Images: {images_dir}")

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

    # Bundle pgsrip config
    pgsrip_config = ROOT_DIR / "third_party" / "pgsrip_install" / "pgsrip_config.json"
    if pgsrip_config.exists():
        datas.append((str(pgsrip_config), os.path.join("third_party", "pgsrip_install")))
        print(f"  [+] PGSRip config: {pgsrip_config}")

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


def build(onefile=True, clean=False):
    """Run PyInstaller build."""
    print("=" * 60)
    print("Bilingual Subtitle Suite - Build")
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
    datas = find_available_data_files()

    print("\nDetecting imports...")
    hidden_imports = get_hidden_imports()

    # Convert icon
    icon_path = None
    if ICON_FILE.exists():
        icon_path = convert_icon(ICON_FILE)

    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "biss",
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
        if onefile:
            exe_path = DIST_DIR / "biss.exe"
        else:
            exe_path = DIST_DIR / "biss" / "biss.exe"

        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful!")
            print(f"  Output: {exe_path}")
            print(f"  Size:   {size_mb:.1f} MB")
            print(f"\nUsage:")
            print(f"  Double-click biss.exe       -> GUI mode")
            print(f"  biss.exe merge file.mkv     -> CLI mode")
            print(f"  biss.exe --help             -> Show help")
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
    args = parser.parse_args()

    onefile = not args.onedir
    return build(onefile=onefile, clean=args.clean)


if __name__ == "__main__":
    sys.exit(main())
