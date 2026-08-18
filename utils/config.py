# config.py
#
# The purpose of this file is to allow any notebook in the project to easily detect directories and import data files as needed

from pathlib import Path

# Resolve PROJECT_ROOT relative to this file (utils/config.py -> utils/ -> root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

PACKAGE_DIR = PROJECT_ROOT / "honey_bee_behavior"

# Current shared bee data and helper files
DATA_DIR = PACKAGE_DIR / "bees_lifetimetracking_2018data"

# Put it all together for export
__all__ = [
    "PROJECT_ROOT",
    "PACKAGE_DIR",
    "DATA_DIR",
]

