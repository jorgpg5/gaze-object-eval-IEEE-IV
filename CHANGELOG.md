# Changelog

## 0.1.2

- **Competitor episodes.** New `goeval.metrics.competitor_episodes` and `competitor_summary`, written to `competitor_episodes.csv` and `competitor_summary.csv`, with a section in `report.md`. The competitor table in `tables.md` / `tables.tex` now splits the competitor subset by the competitor's source (3D, camera-only, other target) and adds the 3D-first cone and the centre ray. New setting `episode_gap_s` (0.5 s).
- The per-sample table names the best competing candidate's source, class and angular box (`other_repr`, `other_class`, `other_az0` .. `other_el1`).
- `goeval.metrics.cone_3d_first_of`: the 3D-first cone, shared by the robustness check and the competitor episodes.
- Both reference rules now accept a candidate at exactly the tolerance in the same way (`baselines.EPS`).
- Files are closed after reading, and text output is written as UTF-8 on every platform.
- `requirements.txt` gives the tested versions as minimums. `run_eval.py --help` prints its usage once.
- Docs: offsets fitted after recording should be fitted on data that is not scored (`docs/protocol.md`); the 2° cone is named as a nearest-box rule.
- No change to any existing number: every CSV and figure in `examples/synthetic/expected` is the same as in 0.1.1; `report.md`, `tables.md` and `tables.tex` gain the competitor results.

## 0.1.1

- Wording: "attribution" is now "mapping" throughout, to match the paper. Output files `attribution.csv` and `attribution_units.csv` are now `mapping.csv` and `mapping_units.csv`, and the car-phase column `attributed_in_3d_from_m` is now `mapped_in_3d_from_m`. `goeval.metrics.attribution` is now `goeval.metrics.mapping_scores`.
- Report tables are named by content (gaze input, mapping) instead of by number.
- `docs/protocol.md`: the two-pedestrian protocol tests identity at wide separation; the looked-at pedestrian is the one nearer the gaze; logging cue times is recommended.
- `goeval/table.py`: the module description of the target box now gives the order the code uses (a moving target takes its camera-only box before an interpolated 3D box).
- No change to any result: every number in `examples/synthetic/expected` is the same as in 0.1.0.

## 0.1.0

First version.
