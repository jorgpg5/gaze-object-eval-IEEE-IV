#!/usr/bin/env python3
"""Evaluate gaze-to-object mapping on one or more recordings.

usage: run_eval.py RECORDING_DIR [RECORDING_DIR ...] --out OUT_DIR [--set key=value ...] [--no-figures] [--no-robustness]

Each RECORDING_DIR holds recording.json, gaze.csv and objects.csv (docs/schema.md).
A directory holding several recordings can be given instead; its sub-folders are used.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import goeval  # noqa: E402


def expand(paths):
    out = []
    for p in paths:
        if os.path.exists(os.path.join(p, "recording.json")):
            out.append(p)
        else:
            subs = sorted(os.path.join(p, d) for d in os.listdir(p) if os.path.exists(os.path.join(p, d, "recording.json")))
            if not subs:
                sys.exit(f"{p}: no recording.json here or in its sub-folders")
            out += subs
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recordings", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a setting from goeval/config.py, e.g. --set look_gate_deg=15")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--no-robustness", action="store_true")
    a = ap.parse_args()
    overrides = {}
    for kv in a.set:
        k, v = kv.split("=", 1)
        overrides[k] = json.loads(v)
    goeval.evaluate(expand(a.recordings), a.out, overrides, figures=not a.no_figures, robustness=not a.no_robustness)


if __name__ == "__main__":
    main()
