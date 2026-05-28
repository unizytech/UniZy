"""Wrapper to run scripts/backfill_accuracy_metrics.py without triggering
services/__init__.py's eager Gemini-client import. The backfill never calls
Gemini — it only reads/writes Supabase — so we short-circuit the package
init by injecting an empty `services` module before submodules are loaded.
"""

import sys
import types

_pkg = types.ModuleType("services")
_pkg.__path__ = [
    __import__("os").path.join(
        __import__("os").path.dirname(__file__), "..", "services"
    )
]
sys.modules["services"] = _pkg

import runpy

runpy.run_path(
    __import__("os").path.join(
        __import__("os").path.dirname(__file__), "backfill_accuracy_metrics.py"
    ),
    run_name="__main__",
)
