"""Version management for VHM workers.

This module provides functionality to read worker versions from pyproject.toml,
allowing each worker to log its version at startup for debugging and monitoring.
"""

import pathlib
import logging

try:
    import toml
except ImportError:
    toml = None

logger = logging.getLogger(__name__)


def get_version(worker_name: str) -> str:
    """
    Reads the version for a specific worker from the pyproject.toml file.
    
    Args:
        worker_name: Name of the worker (e.g., "indexer", "resonance", "reteller")
    
    Returns:
        Version string (e.g., "0.1.0") or "0.0.0-unknown" if version cannot be read
    """
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
        version = data.get("tool", {}).get("vhm", {}).get("versions", {}).get(worker_name)
        
        if version is None:
            logger.warning(f"Version not found for worker '{worker_name}' in pyproject.toml")
            return "0.0.0-unknown"
        
        return str(version)
    except Exception as e:
        logger.warning(f"Could not read version for '{worker_name}': {e}")
        return "0.0.0-unknown"

