"""Root conftest.py - configures Python path before pytest collects tests."""

import sys
from pathlib import Path


def pytest_configure(config):
    """Set up import paths for the test suite.
    
    This runs before test collection, ensuring modules are importable
    when pytest tries to import test files.
    """
    root = Path(__file__).resolve().parent
    
    # Add project root for `workers.vhm_*` imports
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    
    # Add common/utils for `vhm_common_utils` imports
    utils_path = root / "common" / "utils"
    if utils_path.exists():
        utils_str = str(utils_path)
        if utils_str not in sys.path:
            sys.path.insert(0, utils_str)

