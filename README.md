# gaze-object-eval

An evaluation framework for **driver gaze-to-object mapping**: systems that join a driver monitoring system's (DMS) gaze estimate with the vehicle's perceived objects to decide which object in the traffic scene the driver is looking at.

Verifying such a system on the road is hard because the object the driver looked at is rarely known independently of the gaze estimate being tested. This framework fixes that by design. A driver is told which object to look at, in protocols where pedestrians and a car stand or move at known positions. The framework then scores the system against that cue, keeping three sources of error apart:

| Layer | Question | Main output |
|---|---|---|
| Gaze input | How far is the gaze estimate from the cued target? | yaw bias and yaw / pitch precision per stop |
| Object input | How did the target reach the mapping: as a 3D box, camera-only, or not at all? | share of looking time per input state |
| Mapping | Given that gaze and those objects, did the system map the gaze to the right object? | % mapped by distance band, against two reference rules scored on the same samples and candidates: a 2° cone (a nearest-box rule) and the centre ray |

It is **black-box**. The only thing it needs from the system under test is the ID of the object the system maps each gaze sample to, logged next to the gaze and object lists the system used. No internals, settings or source code of the system are needed.

## Quick start

```bash
pip install -r requirements.txt
python3 examples/synthetic/generate.py                       # five synthetic recordings
python3 scripts/check_schema.py examples/synthetic/data/*    # check them against the log format
python3 scripts/run_eval.py examples/synthetic/data --out out
```

Then open `out/report.md`. The synthetic recordings have a known gaze bias and noise, and a simple stand-in "system", so you can see every output before recording anything (`examples/synthetic/README.md`).

## Evaluating your system

1. **Record the protocols** in `docs/protocol.md`: walk-away, crossing, two pedestrians and an approaching car. Calibrate the gaze for each driver before each session (or, if you fit offsets afterwards, fit them on data you do not score; see `docs/protocol.md`).
2. **Log three files per recording** as described in `docs/schema.md`:
   - `gaze.csv`: gaze samples, with your system's `attended_id`;
   - `objects.csv`: the 3D and camera-only object lists your system mapped against;
   - `recording.json`: protocol and condition.
3. **Check** the logs with `scripts/check_schema.py`.
4. **Run** `scripts/run_eval.py RECORDINGS... --out OUT`.

Every setting (look gate, distance bands, cone tolerance, segmentation thresholds, ...) is in `goeval/config.py` and can be changed from the command line, e.g. `--set look_gate_deg=15`. The report lists the settings that differ from the defaults.

## What you get

`OUT/report.md` collects everything below, together with the figures (`fig_distance_<recording>.png`, `fig_sweep.png`):

- `tables.md` / `tables.tex`: the gaze input table, the mapping table by distance, standing vs walking, and the competitor table (samples where another object is within the cone tolerance, by the competitor's source).
- `mapping.csv`: the long form of the mapping table (every phase and band, input states, competitor columns).
- `gaze_input*.csv`, `sweep*.csv`, `offbox.csv`: per-unit gaze errors, the cone tolerance sweep, and the distribution of gaze-to-box distances.
- `crossing_*.csv`: the pedestrian walking across the lane (per crossing, by depth and direction, along-track gaze error).
- `car_phases.csv`: the approaching car (camera-only lead-in, in 3D but not yet mapped, mapped).
- `competitor_episodes.csv`, `competitor_summary.csv`: the samples where another object is within the cone tolerance of the gaze, split into episodes, each with its main competitor (source, class, distance, angular gap to the target) and what the system, the 2° cone, the 3D-first cone and the centre ray chose.
- `robust_*.csv`: robustness checks (look gate, saccades kept, unscored time, a 3D-first cone).
- `samples.pkl`: the per-sample tables, for your own analyses.

Definitions of every metric are in `docs/metrics.md`.

## Layout

```
goeval/        the package: io (schema and checker), signals (saccades, blinks), segment (stops, positions,
               crossings, stations, car approaches), table (per-sample table), baselines, metrics, figures, report
scripts/       run_eval.py, check_schema.py
docs/          schema.md, protocol.md, metrics.md, frames.md
examples/      synthetic recordings with known answers, the generator, and the expected report
tests/         geometry, schema and end-to-end tests (python3 tests/run_tests.py, or pytest)
```

Tested with Python 3.13, numpy 2.5, pandas 3.0 and matplotlib 3.11 (the minimums in `requirements.txt`). Older versions may work but are untested.

## Scope and assumptions

- The protocols are controlled and the target is known by instruction. Naturalistic driving is the next stage, not covered here.
- The cued target is found from the object lists: the pedestrian seen most often, followed across tracker ID changes; for two pedestrians, every pedestrian ID on each side of the lane; for the car, the car tracks in the ego lane. If your scene breaks these assumptions, give the target IDs in `recording.json` (`docs/schema.md`).
- Camera-only detections need a depth estimate to become candidates. `goeval.geom.image_box_to_vehicle` converts an image box and depth into a thin box for a camera aligned with the vehicle axes.

## Citation

The paper describing the framework is under review. Citation details will be added here.

## Licence

MIT. The code is shared here for peer review.
