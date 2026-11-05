# Changelog

## 0.1.1

- Wording: "attribution" is now "mapping" throughout, to match the paper. Output files `attribution.csv` and `attribution_units.csv` are now `mapping.csv` and `mapping_units.csv`, and the car-phase column `attributed_in_3d_from_m` is now `mapped_in_3d_from_m`. `goeval.metrics.attribution` is now `goeval.metrics.mapping_scores`.
- Report tables are named by content (gaze input, mapping) instead of by number.
- `docs/protocol.md`: the two-pedestrian protocol tests identity at wide separation; the looked-at pedestrian is the one nearer the gaze; logging cue times is recommended.
- `goeval/table.py`: the module description of the target box now gives the order the code uses (a moving target takes its camera-only box before an interpolated 3D box).
- No change to any result: every number in `examples/synthetic/expected` is the same as in 0.1.0.

## 0.1.0

First version.
