"""Scratch folders for tests.

Every test folder goes under one parent, <system temp>/biss-tests, instead of
loose biss-* folders in the temp dir. Folders are left in place (so a failed
run can be inspected); remove biss-tests by hand when you like.
"""

import tempfile
from pathlib import Path


def scratch_dir(prefix: str = "biss-") -> Path:
    base = Path(tempfile.gettempdir()) / "biss-tests"
    base.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=base))
