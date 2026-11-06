#!/usr/bin/env python3
"""Check recording folders against the log schema (docs/schema.md).

usage: check_schema.py RECORDING_DIR [RECORDING_DIR ...]
Exit code 1 if any recording has an error.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from goeval.io import check_recording  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    bad = False
    for p in sys.argv[1:]:
        print(p)
        for lvl, msg in check_recording(p):
            print(f"  {lvl.upper():8s}{msg}")
            bad |= lvl == "error"
    sys.exit(1 if bad else 0)
