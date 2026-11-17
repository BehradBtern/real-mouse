#!/usr/bin/env python
"""Run the test suite without needing the package installed.

    python scripts/test.py

Why this exists: some Python builds start with the working directory *not* on
sys.path (isolated mode / PYTHONSAFEPATH). This runner sets the import paths
explicitly, so `python scripts/test.py` works everywhere.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
for path in (str(ROOT), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(TESTS))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
