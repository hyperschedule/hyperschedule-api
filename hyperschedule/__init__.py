"""
Top-level module for Hyperschedule, used to provide `ROOT_DIR`.
"""

import pathlib

# Root directory of the Hyperschedule repository (*not* Python
# package).
ROOT_DIR = pathlib.Path(__file__).parent.parent
