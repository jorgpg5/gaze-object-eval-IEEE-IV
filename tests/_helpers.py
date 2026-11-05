import functools
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples", "synthetic"))

import generate as GEN  # noqa: E402
import goeval  # noqa: E402

TMP = tempfile.mkdtemp(prefix="goeval_tests_")


@functools.lru_cache(maxsize=None)
def synthetic(name):
    """Write one synthetic recording (examples/synthetic/generate.py) and return (path, generator output)."""
    spec = next(s for s in GEN.RECORDINGS if s[0] == name)
    g, o, meta, res = GEN.make(*spec)
    return GEN.write(TMP, g, o, meta), (g, o, meta, res)


@functools.lru_cache(maxsize=None)
def built(name):
    path, _ = synthetic(name)
    rec = goeval.read_recording(path)
    s, info = goeval.build(rec)
    return rec, s, info


def variant(name, new_name, attended):
    """The same recording with a different system output (attended_id column)."""
    path, (g, o, meta, res) = synthetic(name)
    g = g.copy()
    g["attended_id"] = attended(g, res)
    return GEN.write(TMP, g, o, dict(meta, name=new_name))
