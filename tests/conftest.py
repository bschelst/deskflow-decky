"""Make py_modules importable in tests the same way Decky does at runtime."""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PY_MODULES = os.path.join(_ROOT, "py_modules")

if _PY_MODULES not in sys.path:
    sys.path.insert(0, _PY_MODULES)
