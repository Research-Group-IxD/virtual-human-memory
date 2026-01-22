"""Version management for VHM workers.

This module provides functionality to read the project version from pyproject.toml,
allowing each worker to log its version at startup for debugging and monitoring.
"""

import pathlib
import logging

try:
    import toml
except ImportError:
    toml = None

logger = logging.getLogger(__name__)

_cached_version: str | None = None


def get_version(worker_name: str | None = None) -> str:
    """
    Reads the project version from pyproject.toml.
    
    Args:
        worker_name: Optional, kept for backwards compatibility but ignored.
                     All workers share the same project version.
    
    Returns:
        Version string (e.g., "0.1.3") or "0.0.0-unknown" if version cannot be read
    """
    global _cached_version
    
    if _cached_version is not None:
        return _cached_version
    
    if toml is None:
        logger.warning("toml package not available, cannot read version")
        return "0.0.0-unknown"
    
    try:
        # Find pyproject.toml relative to this file
        # This file is at: common/utils/vhm_common_utils/version.py
        # pyproject.toml is at: pyproject.toml (3 levels up)
        current_file = pathlib.Path(__file__)
        pyproject_path = current_file.parent.parent.parent.parent / "pyproject.toml"
        
        if not pyproject_path.exists():
            logger.warning(f"pyproject.toml not found at {pyproject_path}")
            return "0.0.0-unknown"
        
        data = toml.load(pyproject_path)
        version = data.get("project", {}).get("version")
        
        if version is None:
            logger.warning("Version not found in [project] section of pyproject.toml")
            return "0.0.0-unknown"
        
        _cached_version = str(version)
        return _cached_version
    except Exception as e:
        logger.warning(f"Could not read version: {e}")
        return "0.0.0-unknown"

