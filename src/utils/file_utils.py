"""
File and directory utilities.
"""

import os
from pathlib import Path


def ensure_directory_exists(path: str | Path) -> Path:
    """
    Create the directory (and any missing parents) if it does not exist.

    Args:
        path: Directory path as string or Path.

    Returns:
        Resolved Path of the directory.
    """
    p = Path(path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p
