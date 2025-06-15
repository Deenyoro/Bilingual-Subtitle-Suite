#!/usr/bin/env python3
"""
Setup script for Unified Subtitle Processor.

This script helps users set up the application and check for dependencies.
"""

import sys
import subprocess
import platform
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required.")
        print(f"   Current version: {platform.python_version()}")
        return False
    else:
        print(f"✅ Python {platform.python_version()} - Compatible")
        return True


def check_ffmpeg():
    """Check if FFmpeg is installed and accessible."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg - {version_line}")
            return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    print("❌ FFmpeg not found or not accessible")
    print("   FFmpeg is required for video processing operations.")
    print("   Installation instructions:")
    
    system = platform.system().lower()
    if system == "windows":
        print("   - Download from: https://ffmpeg.org/download.html")
        print("   - Or use chocolatey: choco install ffmpeg")
        print("   - Or use winget: winget install FFmpeg")
    elif system == "darwin":  # macOS
        print("   - Install with Homebrew: brew install ffmpeg")
    elif system == "linux":
        print("   - Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg")
        print("   - CentOS/RHEL/Fedora: sudo dnf install ffmpeg")
    
    return False


def check_optional_dependencies():
    """Check for optional Python dependencies."""
    optional_deps = {
        'charset_normalizer': 'charset-normalizer (recommended for encoding detection)',
        'chardet': 'chardet (alternative encoding detection)',
        'curses': 'curses (enhanced interactive interface)'
    }
    
    available = []
    missing = []
    
    for module, description in optional_deps.items():
        try:
            __import__(module)
            available.append(description)
        except ImportError:
            missing.append(description)
    
    if available:
        print("\n✅ Available optional dependencies:")
        for dep in available:
            print(f"   - {dep}")
    
    if missing:
        print("\n⚠️  Missing optional dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print("\n   Install with: pip install charset-normalizer")
        if platform.system().lower() == "windows":
            print("   For Windows curses: pip install windows-curses")
    
    return len(missing) == 0


def install_dependencies():
    """Install Python dependencies."""
    print("\n📦 Installing Python dependencies...")
    
    try:
        # Install charset-normalizer for better encoding detection
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'charset-normalizer'], 
                      check=True)
        print("✅ Installed charset-normalizer")
        
        # Install windows-curses on Windows
        if platform.system().lower() == "windows":
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', 'windows-curses'], 
                              check=True)
                print("✅ Installed windows-curses")
            except subprocess.CalledProcessError:
                print("⚠️  Failed to install windows-curses (optional)")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def test_application():
    """Test if the application can be imported and run."""
    print("\n🧪 Testing application...")
    
    try:
        # Test import
        sys.path.insert(0, str(Path(__file__).parent))
        from biss import main
        print("✅ Application imports successfully")

        # Test help command
        import subprocess
        result = subprocess.run([sys.executable, 'biss.py', '--help'],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Application help command works")
            return True
        else:
            print("❌ Application help command failed")
            return False
            
    except Exception as e:
        print(f"❌ Application test failed: {e}")
        return False


def main():
    """Main setup function."""
    print("🚀 Unified Subtitle Processor Setup")
    print("=" * 50)
    
    # Check system requirements
    print("\n📋 Checking system requirements...")
    
    python_ok = check_python_version()
    ffmpeg_ok = check_ffmpeg()
    
    if not python_ok:
        print("\n❌ Setup failed: Python version incompatible")
        return 1
    
    # Check optional dependencies
    deps_ok = check_optional_dependencies()
    
    # Offer to install dependencies
    if not deps_ok:
        response = input("\n❓ Install missing Python dependencies? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            install_dependencies()
    
    # Test application
    app_ok = test_application()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Setup Summary:")
    print(f"   Python: {'✅' if python_ok else '❌'}")
    print(f"   FFmpeg: {'✅' if ffmpeg_ok else '❌'}")
    print(f"   Application: {'✅' if app_ok else '❌'}")
    
    if python_ok and app_ok:
        print("\n🎉 Setup completed successfully!")
        print("\n🚀 You can now run the application:")
        print("   python biss.py                    # Interactive mode")
        print("   python biss.py --help             # Command line help")
        print("   python biss.py merge movie.mkv    # Example command")
        
        if not ffmpeg_ok:
            print("\n⚠️  Note: Video processing will not work without FFmpeg")
        
        return 0
    else:
        print("\n❌ Setup incomplete. Please resolve the issues above.")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
