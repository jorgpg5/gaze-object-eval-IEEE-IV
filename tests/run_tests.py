#!/usr/bin/env python3
"""Runs every test_* function in tests/ without pytest (pytest works too)."""
import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == "__main__":
    failed = 0
    n = 0
    for f in sorted(os.listdir(HERE)):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        mod = importlib.import_module(f[:-3])
        for name in sorted(dir(mod)):
            if name.startswith("test_") and callable(getattr(mod, name)):
                n += 1
                t0 = time.time()
                try:
                    getattr(mod, name)()
                    print(f"PASS {f[:-3]}.{name} ({time.time() - t0:.1f} s)")
                except Exception:
                    failed += 1
                    print(f"FAIL {f[:-3]}.{name}")
                    traceback.print_exc()
    print(f"\n{n - failed} of {n} tests passed")
    sys.exit(1 if failed else 0)
