#!/usr/bin/env python3
"""
PGSRip Setup and Installation Script

This script automatically downloads, installs, and configures PGSRip
for converting PGS (Presentation Graphic Stream) subtitles to SRT format.

Features:
- Cross-platform installation (Windows, Linux, macOS)
- Automatic dependency management (Tesseract, MKVToolNix)
- Language data download (Chinese simplified/traditional, English)
- Clean installation in isolated directory
- Easy uninstallation option

Usage:
    python setup_pgsrip.py install
    python setup_pgsrip.py uninstall
    python setup_pgsrip.py check
"""

import os
import sys
import platform
import subprocess
import shutil
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logging_config import setup_logging

logger = setup_logging()


class PGSRipInstaller:
    """Handles PGSRip installation and configuration."""
    
    def __init__(self):
        """Initialize the installer."""
        self.script_dir = Path(__file__).parent
        self.install_dir = self.script_dir / "pgsrip_install"
        self.pgsrip_dir = self.install_dir / "pgsrip"
        self.tesseract_dir = self.install_dir / "tesseract"
        self.mkvtoolnix_dir = self.install_dir / "mkvtoolnix"
        self.tessdata_dir = self.install_dir / "tessdata"
        
        self.system = platform.system().lower()
        self.arch = platform.machine().lower()
        
        # Configuration file
        self.config_file = self.install_dir / "pgsrip_config.json"
        
        # Supported languages for OCR
        self.supported_languages = {
            'eng': 'English',
            'chi_sim': 'Chinese Simplified',
            'chi_tra': 'Chinese Traditional'
        }
    
    def install(self, languages: Optional[List[str]] = None) -> bool:
        """
        Install PGSRip and all dependencies.
        
        Args:
            languages: List of language codes to install (default: ['eng', 'chi_sim', 'chi_tra'])
            
        Returns:
            True if installation successful
        """
        if languages is None:
            languages = ['eng', 'chi_sim', 'chi_tra']
        
        logger.info("Starting PGSRip installation...")
        
        try:
            # Create installation directory
            self.install_dir.mkdir(parents=True, exist_ok=True)
            
            # Install components
            steps = [
                ("Installing Python dependencies", self._install_python_deps),
                ("Installing PGSRip", self._install_pgsrip),
                ("Installing Tesseract OCR", self._install_tesseract),
                ("Installing MKVToolNix", self._install_mkvtoolnix),
                ("Downloading language data", lambda: self._install_tessdata(languages)),
                ("Creating configuration", self._create_config)
            ]
            
            for step_name, step_func in steps:
                logger.info(f"Step: {step_name}")
                if not step_func():
                    logger.error(f"Failed: {step_name}")
                    return False
                logger.info(f"Completed: {step_name}")
            
            logger.info("✅ PGSRip installation completed successfully!")
            self._print_installation_summary()
            return True
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
    
    def uninstall(self) -> bool:
        """
        Uninstall PGSRip and remove all files.
        
        Returns:
            True if uninstallation successful
        """
        logger.info("Uninstalling PGSRip...")
        
        try:
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)
                logger.info("✅ PGSRip uninstalled successfully!")
            else:
                logger.info("PGSRip is not installed.")
            
            return True
            
        except Exception as e:
            logger.error(f"Uninstallation failed: {e}")
            return False
    
    def check_installation(self) -> Dict[str, bool]:
        """
        Check installation status of all components.
        
        Returns:
            Dictionary with component status
        """
        status = {
            'pgsrip': self._check_pgsrip(),
            'tesseract': self._check_tesseract(),
            'mkvtoolnix': self._check_mkvtoolnix(),
            'tessdata': self._check_tessdata(),
            'config': self.config_file.exists()
        }
        
        return status
    
    def _install_python_deps(self) -> bool:
        """Install required Python dependencies."""
        try:
            # Install PGSRip from GitHub
            cmd = [
                sys.executable, '-m', 'pip', 'install',
                'git+https://github.com/ratoaq2/pgsrip.git',
                '--target', str(self.install_dir / 'python_packages')
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to install PGSRip: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to install Python dependencies: {e}")
            return False
    
    def _install_pgsrip(self) -> bool:
        """Install PGSRip from GitHub."""
        try:
            # Clone PGSRip repository
            if self.pgsrip_dir.exists():
                shutil.rmtree(self.pgsrip_dir)
            
            cmd = [
                'git', 'clone',
                'https://github.com/ratoaq2/pgsrip.git',
                str(self.pgsrip_dir)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("Git clone failed, trying alternative download method...")
                return self._download_pgsrip_zip()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to install PGSRip: {e}")
            return False
    
    def _download_pgsrip_zip(self) -> bool:
        """Download PGSRip as ZIP file (fallback method)."""
        try:
            url = "https://github.com/ratoaq2/pgsrip/archive/refs/heads/main.zip"
            
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                urllib.request.urlretrieve(url, tmp_file.name)
                
                with zipfile.ZipFile(tmp_file.name, 'r') as zip_ref:
                    zip_ref.extractall(self.install_dir)
                
                # Rename extracted directory
                extracted_dir = self.install_dir / "pgsrip-main"
                if extracted_dir.exists():
                    if self.pgsrip_dir.exists():
                        shutil.rmtree(self.pgsrip_dir)
                    extracted_dir.rename(self.pgsrip_dir)
                
                os.unlink(tmp_file.name)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to download PGSRip ZIP: {e}")
            return False
    
    def _install_tesseract(self) -> bool:
        """Install Tesseract OCR."""
        try:
            if self.system == "windows":
                return self._install_tesseract_windows()
            elif self.system == "darwin":
                return self._install_tesseract_macos()
            elif self.system == "linux":
                return self._install_tesseract_linux()
            else:
                logger.error(f"Unsupported system: {self.system}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to install Tesseract: {e}")
            return False
    
    def _install_tesseract_windows(self) -> bool:
        """Install Tesseract on Windows with enhanced detection and auto-install."""
        # Check if Tesseract is already available (try common paths)
        tesseract_paths = [
            "tesseract",  # In PATH
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            # Additional common paths
            r"C:\tools\tesseract\tesseract.exe",  # Chocolatey path
            r"C:\ProgramData\chocolatey\lib\tesseract\tools\tesseract.exe"
        ]

        for tesseract_path in tesseract_paths:
            try:
                result = subprocess.run([tesseract_path, '--version'],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"✅ Tesseract is already installed: {version_line}")

                    # Store the working path for later use
                    tesseract_info = self.tesseract_dir / "tesseract_path.txt"
                    tesseract_info.parent.mkdir(parents=True, exist_ok=True)
                    tesseract_info.write_text(tesseract_path)

                    return True
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                continue

        # Try automatic installation via winget (Windows 10+)
        logger.info("Attempting automatic Tesseract installation via winget...")
        try:
            result = subprocess.run(['winget', 'install', 'UB-Mannheim.TesseractOCR', '--accept-package-agreements', '--accept-source-agreements'],
                                  capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("✅ Tesseract installed via winget")
                # Re-check for installation
                return self._install_tesseract_windows()
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            logger.debug("winget not available or installation failed")

        # Try chocolatey installation
        logger.info("Attempting automatic Tesseract installation via chocolatey...")
        try:
            result = subprocess.run(['choco', 'install', 'tesseract', '-y'],
                                  capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("✅ Tesseract installed via chocolatey")
                # Re-check for installation
                return self._install_tesseract_windows()
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            logger.debug("chocolatey not available or installation failed")

        # Manual installation instructions
        logger.warning("⚠️  Automatic Tesseract installation failed. Manual setup required.")
        logger.info("Please install Tesseract using one of these methods:")
        logger.info("1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki")
        logger.info("2. Use winget: winget install UB-Mannheim.TesseractOCR")
        logger.info("3. Use chocolatey: choco install tesseract")

        # Create detailed instructions file
        tesseract_info = self.tesseract_dir / "INSTALLATION_INSTRUCTIONS.txt"
        tesseract_info.parent.mkdir(parents=True, exist_ok=True)
        tesseract_info.write_text(
            "Tesseract OCR Installation Instructions for Windows\n"
            "=" * 50 + "\n\n"
            "AUTOMATIC INSTALLATION (Recommended):\n"
            "1. Using winget (Windows 10+):\n"
            "   winget install UB-Mannheim.TesseractOCR\n\n"
            "2. Using chocolatey:\n"
            "   choco install tesseract\n\n"
            "MANUAL INSTALLATION:\n"
            "1. Download from: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "2. Run the installer (tesseract-ocr-w64-setup-v5.x.x.exe)\n"
            "3. During installation, make sure to:\n"
            "   - Install to default location (C:\\Program Files\\Tesseract-OCR)\n"
            "   - Add Tesseract to PATH (check the option)\n"
            "   - Install additional language data if prompted\n\n"
            "VERIFICATION:\n"
            "After installation, open Command Prompt and run:\n"
            "   tesseract --version\n\n"
            "If successful, re-run the PGSRip setup:\n"
            "   python biss.py setup-pgsrip install\n"
        )

        # Return True to continue with other components
        return True
    
    def _install_tesseract_macos(self) -> bool:
        """Install Tesseract on macOS."""
        try:
            # Check if Homebrew is available
            result = subprocess.run(['brew', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Homebrew is required for Tesseract installation on macOS")
                return False
            
            # Install Tesseract via Homebrew
            cmd = ['brew', 'install', 'tesseract']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✅ Tesseract installed via Homebrew")
                return True
            else:
                logger.error(f"Failed to install Tesseract: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Tesseract installation failed on macOS: {e}")
            return False
    
    def _install_tesseract_linux(self) -> bool:
        """Install Tesseract on Linux with enhanced detection and auto-install."""
        # First check if Tesseract is already installed
        try:
            result = subprocess.run(['tesseract', '--version'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.info(f"✅ Tesseract is already installed: {version_line}")
                return True
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        # Detect Linux distribution
        distro_info = self._detect_linux_distro()
        logger.info(f"Detected Linux distribution: {distro_info['name']}")

        # Try distribution-specific installation
        if distro_info['family'] == 'debian':
            return self._install_tesseract_debian()
        elif distro_info['family'] == 'redhat':
            return self._install_tesseract_redhat()
        elif distro_info['family'] == 'arch':
            return self._install_tesseract_arch()
        elif distro_info['family'] == 'suse':
            return self._install_tesseract_suse()
        else:
            # Fallback to generic installation
            return self._install_tesseract_generic()

    def _detect_linux_distro(self) -> dict:
        """Detect Linux distribution and family."""
        try:
            # Try reading /etc/os-release
            if Path('/etc/os-release').exists():
                with open('/etc/os-release', 'r') as f:
                    lines = f.readlines()

                info = {}
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        info[key] = value.strip('"')

                name = info.get('NAME', '').lower()
                id_like = info.get('ID_LIKE', '').lower()
                distro_id = info.get('ID', '').lower()

                # Determine family
                if any(x in name + id_like + distro_id for x in ['ubuntu', 'debian', 'mint']):
                    family = 'debian'
                elif any(x in name + id_like + distro_id for x in ['rhel', 'centos', 'fedora', 'red hat']):
                    family = 'redhat'
                elif any(x in name + id_like + distro_id for x in ['arch', 'manjaro']):
                    family = 'arch'
                elif any(x in name + id_like + distro_id for x in ['suse', 'opensuse']):
                    family = 'suse'
                else:
                    family = 'unknown'

                return {'name': info.get('NAME', 'Unknown'), 'family': family, 'id': distro_id}

        except Exception:
            pass

        return {'name': 'Unknown', 'family': 'unknown', 'id': 'unknown'}

    def _install_tesseract_debian(self) -> bool:
        """Install Tesseract on Debian/Ubuntu systems."""
        try:
            logger.info("Installing Tesseract on Debian/Ubuntu system...")

            # Update package list
            update_result = subprocess.run(['sudo', 'apt-get', 'update'],
                                         capture_output=True, text=True, timeout=120)

            # Install Tesseract with language packs
            install_cmd = [
                'sudo', 'apt-get', 'install', '-y',
                'tesseract-ocr',
                'tesseract-ocr-eng',  # English
                'tesseract-ocr-chi-sim',  # Chinese Simplified
                'tesseract-ocr-chi-tra'   # Chinese Traditional
            ]

            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ Tesseract installed via apt-get")
                return True
            else:
                logger.error(f"Failed to install Tesseract: {result.stderr}")
                return False

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Tesseract installation failed on Debian/Ubuntu: {e}")
            return False

    def _install_tesseract_redhat(self) -> bool:
        """Install Tesseract on RedHat/CentOS/Fedora systems."""
        try:
            logger.info("Installing Tesseract on RedHat/CentOS/Fedora system...")

            # Try dnf first (newer systems), then yum
            package_managers = ['dnf', 'yum']

            for pm in package_managers:
                try:
                    # Check if package manager exists
                    subprocess.run([pm, '--version'], capture_output=True, check=True)

                    # Install Tesseract
                    install_cmd = ['sudo', pm, 'install', '-y', 'tesseract', 'tesseract-langpack-eng']
                    result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

                    if result.returncode == 0:
                        logger.info(f"✅ Tesseract installed via {pm}")
                        return True

                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

            logger.error("Could not install Tesseract with dnf or yum")
            return False

        except Exception as e:
            logger.error(f"Tesseract installation failed on RedHat/CentOS/Fedora: {e}")
            return False

    def _install_tesseract_arch(self) -> bool:
        """Install Tesseract on Arch Linux systems."""
        try:
            logger.info("Installing Tesseract on Arch Linux system...")

            install_cmd = [
                'sudo', 'pacman', '-S', '--noconfirm',
                'tesseract',
                'tesseract-data-eng',
                'tesseract-data-chi_sim',
                'tesseract-data-chi_tra'
            ]

            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ Tesseract installed via pacman")
                return True
            else:
                logger.error(f"Failed to install Tesseract: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Tesseract installation failed on Arch Linux: {e}")
            return False

    def _install_tesseract_suse(self) -> bool:
        """Install Tesseract on openSUSE systems."""
        try:
            logger.info("Installing Tesseract on openSUSE system...")

            install_cmd = ['sudo', 'zypper', 'install', '-y', 'tesseract-ocr', 'tesseract-ocr-traineddata-english']
            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ Tesseract installed via zypper")
                return True
            else:
                logger.error(f"Failed to install Tesseract: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Tesseract installation failed on openSUSE: {e}")
            return False

    def _install_tesseract_generic(self) -> bool:
        """Generic Tesseract installation fallback."""
        try:
            logger.warning("⚠️  Could not detect Linux distribution. Trying generic installation...")

            # Try common package managers
            package_managers = [
                (['apt-get', 'update'], ['apt-get', 'install', '-y', 'tesseract-ocr']),
                (['dnf', 'install', '-y', 'tesseract']),
                (['yum', 'install', '-y', 'tesseract']),
                (['pacman', '-S', '--noconfirm', 'tesseract']),
                (['zypper', 'install', '-y', 'tesseract-ocr'])
            ]

            for update_cmd, install_cmd in package_managers:
                try:
                    if update_cmd:
                        subprocess.run(['sudo'] + update_cmd, capture_output=True, timeout=120)

                    result = subprocess.run(['sudo'] + install_cmd, capture_output=True, text=True, timeout=300)
                    if result.returncode == 0:
                        logger.info(f"✅ Tesseract installed via {install_cmd[0]}")
                        return True

                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue

            # Manual installation instructions
            logger.error("⚠️  Automatic Tesseract installation failed. Manual setup required.")
            logger.info("Please install Tesseract manually using your distribution's package manager:")
            logger.info("• Debian/Ubuntu: sudo apt-get install tesseract-ocr tesseract-ocr-eng")
            logger.info("• CentOS/RHEL/Fedora: sudo dnf install tesseract tesseract-langpack-eng")
            logger.info("• Arch Linux: sudo pacman -S tesseract tesseract-data-eng")
            logger.info("• openSUSE: sudo zypper install tesseract-ocr tesseract-ocr-traineddata-english")

            return False

        except Exception as e:
            logger.error(f"Generic Tesseract installation failed: {e}")
            return False

    def _install_mkvtoolnix(self) -> bool:
        """Install MKVToolNix."""
        try:
            if self.system == "windows":
                return self._install_mkvtoolnix_windows()
            elif self.system == "darwin":
                return self._install_mkvtoolnix_macos()
            elif self.system == "linux":
                return self._install_mkvtoolnix_linux()
            else:
                logger.error(f"Unsupported system: {self.system}")
                return False

        except Exception as e:
            logger.error(f"Failed to install MKVToolNix: {e}")
            return False

    def _install_mkvtoolnix_windows(self) -> bool:
        """Install MKVToolNix on Windows with enhanced detection and auto-install."""
        # Check if MKVToolNix is already available (try common paths)
        mkvtoolnix_paths = [
            "mkvextract",  # In PATH
            r"C:\Program Files\MKVToolNix\mkvextract.exe",
            r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
            # Additional common paths
            r"C:\tools\mkvtoolnix\mkvextract.exe",  # Chocolatey path
            r"C:\ProgramData\chocolatey\lib\mkvtoolnix\tools\mkvextract.exe"
        ]

        for mkvextract_path in mkvtoolnix_paths:
            try:
                result = subprocess.run([mkvextract_path, '--version'],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"✅ MKVToolNix is already installed: {version_line}")

                    # Store the working path for later use
                    mkvtoolnix_info = self.mkvtoolnix_dir / "mkvextract_path.txt"
                    mkvtoolnix_info.parent.mkdir(parents=True, exist_ok=True)
                    mkvtoolnix_info.write_text(mkvextract_path)

                    return True
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                continue

        # Try automatic installation via chocolatey
        logger.info("Attempting automatic MKVToolNix installation via chocolatey...")
        try:
            result = subprocess.run(['choco', 'install', 'mkvtoolnix', '-y'],
                                  capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("✅ MKVToolNix installed via chocolatey")
                # Re-check for installation
                return self._install_mkvtoolnix_windows()
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            logger.debug("chocolatey not available or installation failed")

        # Manual installation instructions
        logger.warning("⚠️  Automatic MKVToolNix installation failed. Manual setup required.")
        logger.info("Please install MKVToolNix using one of these methods:")
        logger.info("1. Download installer: https://mkvtoolnix.download/")
        logger.info("2. Use chocolatey: choco install mkvtoolnix")

        # Create detailed instructions file
        mkvtoolnix_info = self.mkvtoolnix_dir / "INSTALLATION_INSTRUCTIONS.txt"
        mkvtoolnix_info.parent.mkdir(parents=True, exist_ok=True)
        mkvtoolnix_info.write_text(
            "MKVToolNix Installation Instructions for Windows\n"
            "=" * 50 + "\n\n"
            "AUTOMATIC INSTALLATION (Recommended):\n"
            "1. Using chocolatey:\n"
            "   choco install mkvtoolnix\n\n"
            "MANUAL INSTALLATION:\n"
            "1. Download from: https://mkvtoolnix.download/\n"
            "2. Run the installer (mkvtoolnix-xx.x.x-setup.exe)\n"
            "3. During installation, make sure to:\n"
            "   - Install to default location (C:\\Program Files\\MKVToolNix)\n"
            "   - Add MKVToolNix to PATH (check the option)\n\n"
            "VERIFICATION:\n"
            "After installation, open Command Prompt and run:\n"
            "   mkvextract --version\n\n"
            "If successful, re-run the PGSRip setup:\n"
            "   python biss.py setup-pgsrip install\n"
        )

        # Return True to continue with other components
        return True

    def _install_mkvtoolnix_macos(self) -> bool:
        """Install MKVToolNix on macOS."""
        try:
            cmd = ['brew', 'install', 'mkvtoolnix']
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("✅ MKVToolNix installed via Homebrew")
                return True
            else:
                logger.error(f"Failed to install MKVToolNix: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MKVToolNix installation failed on macOS: {e}")
            return False

    def _install_mkvtoolnix_linux(self) -> bool:
        """Install MKVToolNix on Linux with enhanced detection and auto-install."""
        # First check if MKVToolNix is already installed
        try:
            result = subprocess.run(['mkvextract', '--version'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.info(f"✅ MKVToolNix is already installed: {version_line}")
                return True
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        # Get distribution info (reuse from Tesseract detection)
        distro_info = self._detect_linux_distro()
        logger.info(f"Installing MKVToolNix for {distro_info['name']}...")

        # Try distribution-specific installation
        if distro_info['family'] == 'debian':
            return self._install_mkvtoolnix_debian()
        elif distro_info['family'] == 'redhat':
            return self._install_mkvtoolnix_redhat()
        elif distro_info['family'] == 'arch':
            return self._install_mkvtoolnix_arch()
        elif distro_info['family'] == 'suse':
            return self._install_mkvtoolnix_suse()
        else:
            # Fallback to generic installation
            return self._install_mkvtoolnix_generic()

    def _install_mkvtoolnix_debian(self) -> bool:
        """Install MKVToolNix on Debian/Ubuntu systems."""
        try:
            logger.info("Installing MKVToolNix on Debian/Ubuntu system...")

            # Update package list
            subprocess.run(['sudo', 'apt-get', 'update'],
                         capture_output=True, text=True, timeout=120)

            # Install MKVToolNix
            install_cmd = ['sudo', 'apt-get', 'install', '-y', 'mkvtoolnix']
            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ MKVToolNix installed via apt-get")
                return True
            else:
                logger.error(f"Failed to install MKVToolNix: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MKVToolNix installation failed on Debian/Ubuntu: {e}")
            return False

    def _install_mkvtoolnix_redhat(self) -> bool:
        """Install MKVToolNix on RedHat/CentOS/Fedora systems."""
        try:
            logger.info("Installing MKVToolNix on RedHat/CentOS/Fedora system...")

            # Try dnf first (newer systems), then yum
            package_managers = ['dnf', 'yum']

            for pm in package_managers:
                try:
                    # Check if package manager exists
                    subprocess.run([pm, '--version'], capture_output=True, check=True)

                    # Install MKVToolNix
                    install_cmd = ['sudo', pm, 'install', '-y', 'mkvtoolnix']
                    result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

                    if result.returncode == 0:
                        logger.info(f"✅ MKVToolNix installed via {pm}")
                        return True

                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

            logger.error("Could not install MKVToolNix with dnf or yum")
            return False

        except Exception as e:
            logger.error(f"MKVToolNix installation failed on RedHat/CentOS/Fedora: {e}")
            return False

    def _install_mkvtoolnix_arch(self) -> bool:
        """Install MKVToolNix on Arch Linux systems."""
        try:
            logger.info("Installing MKVToolNix on Arch Linux system...")

            install_cmd = ['sudo', 'pacman', '-S', '--noconfirm', 'mkvtoolnix-cli']
            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ MKVToolNix installed via pacman")
                return True
            else:
                logger.error(f"Failed to install MKVToolNix: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MKVToolNix installation failed on Arch Linux: {e}")
            return False

    def _install_mkvtoolnix_suse(self) -> bool:
        """Install MKVToolNix on openSUSE systems."""
        try:
            logger.info("Installing MKVToolNix on openSUSE system...")

            install_cmd = ['sudo', 'zypper', 'install', '-y', 'mkvtoolnix']
            result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ MKVToolNix installed via zypper")
                return True
            else:
                logger.error(f"Failed to install MKVToolNix: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"MKVToolNix installation failed on openSUSE: {e}")
            return False

    def _install_mkvtoolnix_generic(self) -> bool:
        """Generic MKVToolNix installation fallback."""
        try:
            logger.warning("⚠️  Trying generic MKVToolNix installation...")

            # Try common package managers
            package_managers = [
                (['apt-get', 'update'], ['apt-get', 'install', '-y', 'mkvtoolnix']),
                (['dnf', 'install', '-y', 'mkvtoolnix']),
                (['yum', 'install', '-y', 'mkvtoolnix']),
                (['pacman', '-S', '--noconfirm', 'mkvtoolnix-cli']),
                (['zypper', 'install', '-y', 'mkvtoolnix'])
            ]

            for update_cmd, install_cmd in package_managers:
                try:
                    if update_cmd:
                        subprocess.run(['sudo'] + update_cmd, capture_output=True, timeout=120)

                    result = subprocess.run(['sudo'] + install_cmd, capture_output=True, text=True, timeout=300)
                    if result.returncode == 0:
                        logger.info(f"✅ MKVToolNix installed via {install_cmd[0]}")
                        return True

                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue

            # Manual installation instructions
            logger.error("⚠️  Automatic MKVToolNix installation failed. Manual setup required.")
            logger.info("Please install MKVToolNix manually using your distribution's package manager:")
            logger.info("• Debian/Ubuntu: sudo apt-get install mkvtoolnix")
            logger.info("• CentOS/RHEL/Fedora: sudo dnf install mkvtoolnix")
            logger.info("• Arch Linux: sudo pacman -S mkvtoolnix-cli")
            logger.info("• openSUSE: sudo zypper install mkvtoolnix")

            return False

        except Exception as e:
            logger.error(f"Generic MKVToolNix installation failed: {e}")
            return False

    def _install_tessdata(self, languages: List[str]) -> bool:
        """Download Tesseract language data files."""
        try:
            self.tessdata_dir.mkdir(parents=True, exist_ok=True)

            base_url = "https://github.com/tesseract-ocr/tessdata/raw/main"

            for lang_code in languages:
                if lang_code not in self.supported_languages:
                    logger.warning(f"Unsupported language: {lang_code}")
                    continue

                lang_file = f"{lang_code}.traineddata"
                lang_path = self.tessdata_dir / lang_file

                # Check if file exists and is valid size
                if lang_path.exists():
                    file_size = lang_path.stat().st_size
                    if file_size > 1000000:  # At least 1MB for valid language data
                        logger.info(f"✅ {self.supported_languages[lang_code]} language data already exists ({file_size:,} bytes)")
                        continue
                    else:
                        logger.warning(f"Existing {self.supported_languages[lang_code]} language data is too small, re-downloading...")
                        lang_path.unlink()

                url = f"{base_url}/{lang_file}"
                logger.info(f"Downloading {self.supported_languages[lang_code]} language data...")

                try:
                    # Use urllib with better error handling and progress
                    def progress_hook(block_num, block_size, total_size):
                        if total_size > 0:
                            downloaded = block_num * block_size
                            if downloaded % (5 * 1024 * 1024) == 0:  # Log every 5MB
                                progress = min(100, (downloaded / total_size) * 100)
                                logger.info(f"   Progress: {progress:.1f}% ({downloaded:,}/{total_size:,} bytes)")

                    urllib.request.urlretrieve(url, lang_path, reporthook=progress_hook)

                    # Verify download
                    final_size = lang_path.stat().st_size
                    if final_size < 1000000:  # Less than 1MB is suspicious
                        logger.error(f"Downloaded file is too small ({final_size:,} bytes), may be corrupted")
                        lang_path.unlink()
                        return False

                    logger.info(f"✅ Downloaded: {lang_file} ({final_size:,} bytes)")

                except urllib.error.URLError as e:
                    logger.error(f"Failed to download {lang_file}: {e}")
                    if lang_path.exists():
                        lang_path.unlink()
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error downloading {lang_file}: {e}")
                    if lang_path.exists():
                        lang_path.unlink()
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed to install language data: {e}")
            return False

    def _create_config(self) -> bool:
        """Create configuration file."""
        try:
            config = {
                'installation_date': str(Path(__file__).stat().st_mtime),
                'system': self.system,
                'architecture': self.arch,
                'paths': {
                    'pgsrip': str(self.pgsrip_dir),
                    'tesseract': str(self.tesseract_dir),
                    'mkvtoolnix': str(self.mkvtoolnix_dir),
                    'tessdata': str(self.tessdata_dir),
                    'python_packages': str(self.install_dir / 'python_packages')
                },
                'languages': list(self.supported_languages.keys()),
                'version': '1.0.0'
            }

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to create configuration: {e}")
            return False

    def _check_pgsrip(self) -> bool:
        """Check if PGSRip is installed."""
        return self.pgsrip_dir.exists() and (self.pgsrip_dir / "pgsrip").exists()

    def _check_tesseract(self) -> bool:
        """Check if Tesseract is available across platforms."""
        # Platform-specific paths
        if self.system == 'windows':
            tesseract_paths = [
                "tesseract",  # In PATH
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\tools\tesseract\tesseract.exe",  # Chocolatey
                r"C:\ProgramData\chocolatey\lib\tesseract\tools\tesseract.exe"
            ]
        else:
            # Linux/macOS - typically in PATH
            tesseract_paths = [
                "tesseract",  # In PATH
                "/usr/bin/tesseract",  # Common Linux path
                "/usr/local/bin/tesseract",  # Common macOS/Linux path
                "/opt/homebrew/bin/tesseract"  # macOS ARM Homebrew
            ]

        # Also check if we stored a working path
        stored_path_file = self.tesseract_dir / "tesseract_path.txt"
        if stored_path_file.exists():
            try:
                stored_path = stored_path_file.read_text().strip()
                tesseract_paths.insert(0, stored_path)  # Try stored path first
            except Exception:
                pass

        for tesseract_path in tesseract_paths:
            try:
                result = subprocess.run([tesseract_path, '--version'],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                continue

        return False

    def _check_mkvtoolnix(self) -> bool:
        """Check if MKVToolNix is available across platforms."""
        # Platform-specific paths
        if self.system == 'windows':
            mkvextract_paths = [
                "mkvextract",  # In PATH
                r"C:\Program Files\MKVToolNix\mkvextract.exe",
                r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
                r"C:\tools\mkvtoolnix\mkvextract.exe",  # Chocolatey
                r"C:\ProgramData\chocolatey\lib\mkvtoolnix\tools\mkvextract.exe"
            ]
        else:
            # Linux/macOS - typically in PATH
            mkvextract_paths = [
                "mkvextract",  # In PATH
                "/usr/bin/mkvextract",  # Common Linux path
                "/usr/local/bin/mkvextract",  # Common macOS/Linux path
                "/opt/homebrew/bin/mkvextract"  # macOS ARM Homebrew
            ]

        # Also check if we stored a working path
        stored_path_file = self.mkvtoolnix_dir / "mkvextract_path.txt"
        if stored_path_file.exists():
            try:
                stored_path = stored_path_file.read_text().strip()
                mkvextract_paths.insert(0, stored_path)  # Try stored path first
            except Exception:
                pass

        for mkvextract_path in mkvextract_paths:
            try:
                result = subprocess.run([mkvextract_path, '--version'],
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                continue

        return False

    def _check_tessdata(self) -> bool:
        """Check if language data files exist."""
        if not self.tessdata_dir.exists():
            return False

        required_files = [f"{lang}.traineddata" for lang in self.supported_languages.keys()]
        existing_files = [f.name for f in self.tessdata_dir.glob("*.traineddata")]

        return all(f in existing_files for f in required_files)

    def _print_installation_summary(self):
        """Print comprehensive installation summary with guidance."""
        status = self.check_installation()

        print("\n" + "=" * 70)
        print("PGSRip Installation Summary")
        print("=" * 70)

        # Component status with detailed information
        component_details = {
            'pgsrip': 'PGSRip Python Package',
            'tesseract': 'Tesseract OCR Engine',
            'mkvtoolnix': 'MKVToolNix (Video Processing)',
            'tessdata': 'OCR Language Data Files',
            'config': 'Configuration File'
        }

        for component, installed in status.items():
            status_icon = "✅" if installed else "❌"
            detail = component_details.get(component, component.upper())
            print(f"{status_icon} {detail}: {'Installed' if installed else 'Not Available'}")

        print(f"\nInstallation Directory: {self.install_dir}")
        print(f"Configuration File: {self.config_file}")

        # Detailed status and next steps
        if all(status.values()):
            print("\n🎉 ALL COMPONENTS INSTALLED SUCCESSFULLY!")
            print("\nPGS subtitle conversion is now fully functional.")
            print("\nYou can now:")
            print("• Convert PGS subtitles: python biss.py convert-pgs [video.mkv] --language eng")
            print("• Use automatic PGS fallback in subtitle merging")
            print("• Force PGS conversion with --force-pgs flag")
            print("• Test the installation: python biss.py setup-pgsrip check")
        else:
            print("\n⚠️  MANUAL INSTALLATION REQUIRED FOR SOME COMPONENTS")

            # Specific guidance for missing components
            if not status['tesseract']:
                print("\n📋 TESSERACT OCR SETUP:")
                if self.system == 'windows':
                    print("   • Check: third_party/pgsrip_install/tesseract/INSTALLATION_INSTRUCTIONS.txt")
                    print("   • Quick install: winget install UB-Mannheim.TesseractOCR")
                    print("   • Or download: https://github.com/UB-Mannheim/tesseract/wiki")
                elif self.system == 'linux':
                    print("   • Debian/Ubuntu: sudo apt-get install tesseract-ocr tesseract-ocr-eng")
                    print("   • CentOS/RHEL/Fedora: sudo dnf install tesseract tesseract-langpack-eng")
                    print("   • Arch Linux: sudo pacman -S tesseract tesseract-data-eng")
                    print("   • openSUSE: sudo zypper install tesseract-ocr")
                elif self.system == 'darwin':
                    print("   • macOS: brew install tesseract")

            if not status['mkvtoolnix']:
                print("\n📋 MKVTOOLNIX SETUP:")
                if self.system == 'windows':
                    print("   • Check: third_party/pgsrip_install/mkvtoolnix/INSTALLATION_INSTRUCTIONS.txt")
                    print("   • Quick install: choco install mkvtoolnix")
                    print("   • Or download: https://mkvtoolnix.download/")
                elif self.system == 'linux':
                    print("   • Debian/Ubuntu: sudo apt-get install mkvtoolnix")
                    print("   • CentOS/RHEL/Fedora: sudo dnf install mkvtoolnix")
                    print("   • Arch Linux: sudo pacman -S mkvtoolnix-cli")
                    print("   • openSUSE: sudo zypper install mkvtoolnix")
                elif self.system == 'darwin':
                    print("   • macOS: brew install mkvtoolnix")

            if not status['tessdata']:
                print("\n📋 LANGUAGE DATA:")
                print("   • Language files may need re-download")
                print("   • Run: python biss.py setup-pgsrip install --languages eng chi_sim chi_tra")

            print(f"\n🔄 After manual installation, re-run: python biss.py setup-pgsrip check")
            print("   This will verify all components are working correctly.")

        # System information
        print(f"\nSystem Information:")
        print(f"• Operating System: {self.system.title()}")
        print(f"• Architecture: {self.arch}")
        print(f"• Python: {sys.version.split()[0]}")

        # Usage examples
        print(f"\nUsage Examples:")
        print(f"• Check status: python biss.py setup-pgsrip check")
        print(f"• Convert PGS: python biss.py convert-pgs video.mkv --language eng")
        print(f"• Merge with PGS fallback: python biss.py merge video.mkv --output merged.srt")
        print(f"• Force PGS usage: python biss.py merge video.mkv --force-pgs --output merged.srt")


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PGSRip Setup and Installation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'action',
        choices=['install', 'uninstall', 'check'],
        help='Action to perform'
    )

    parser.add_argument(
        '--languages',
        nargs='+',
        default=['eng', 'chi_sim', 'chi_tra'],
        help='Language codes to install (default: eng chi_sim chi_tra)'
    )

    args = parser.parse_args()

    installer = PGSRipInstaller()

    if args.action == 'install':
        success = installer.install(args.languages)
        sys.exit(0 if success else 1)
    elif args.action == 'uninstall':
        success = installer.uninstall()
        sys.exit(0 if success else 1)
    elif args.action == 'check':
        status = installer.check_installation()
        installer._print_installation_summary()
        sys.exit(0 if all(status.values()) else 1)


if __name__ == '__main__':
    main()
