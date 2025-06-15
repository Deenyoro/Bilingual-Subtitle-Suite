"""
Third-party integrations for the Unified Subtitle Processor.

This package contains integrations with external tools and libraries:
- PGSRip: For converting PGS (Presentation Graphic Stream) subtitles to SRT
- Tesseract OCR: For optical character recognition
- MKVToolNix: For video container manipulation

All third-party tools are installed in isolated subdirectories to maintain
clean separation from the main application.
"""

from .pgsrip_wrapper import PGSRipWrapper, PGSRipNotInstalledError, is_pgsrip_available, get_pgsrip_wrapper

__all__ = [
    'PGSRipWrapper',
    'PGSRipNotInstalledError',
    'is_pgsrip_available',
    'get_pgsrip_wrapper'
]
