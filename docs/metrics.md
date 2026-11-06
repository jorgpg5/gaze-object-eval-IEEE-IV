# Metrics

All settings named here are in `goeval/config.py`. Durations are sample counts divided by the recording's measured sample rate.

## Samples that are scored

1. **Units.** Each recording is cut into units from the cued target's own 3D track (`protocol.md`):
   - stops (walk-away);
   - standing positions and their repeats (crossing);
   - stations (two pedestrians);
   - the walks between consecutive standing units;
   - car approaches.
   
   Each sample belongs to a **phase**: `standing`, `walking` or `approach`.
2. **Clean samples.** Valid gaze samples that are neither a saccade (gaze angular speed above `saccade_deg_s`) nor a blink.
3. **Looking samples.** Clean samples whose gaze is within `look_gate_deg` (10°) of the cued target's box centre. With two pedestrians, the looked-at pedestrian is the one nearer the gaze, within the gate. Samples beyond the gate are glances elsewhere and are not scored. The robustness checks report how much time this leaves out.

**Ground truth = the cued target.** A looking sample is correct when the system's `attended_id` is the cued target (any of its track IDs) or a camera-only duplicate of it: a camera-only box with at least `dup_cover` (50%) of its angular extent inside the target's box, i.e. the same object seen by the camera, or something hidden behind it.

## The target's box at each sample

- **Standing target:** its 3D box. If it is not in the 3D list at that sample, its median 3D box over the unit (it stands still), else its camera-only box.
- **Moving target** (walks, crossings, car): its 3D box; else its camera-only box; else its 3D box interpolated over gaps up to `interp_max_s`.

**Input state** (object input layer) records how the target reached the mapping at each sample: `3d`, `2d` (camera-only only) or `absent`.

## Gaze input

On looking samples with the target in 3D, standing phases only, per unit:

- **yaw error** = gaze yaw − bearing of the box centre from the eye;
- **pitch error** = gaze pitch − elevation of the point at `upper_body_frac` of the box height;
- **bias** = median error;
- **precision** = 1.4826 × median absolute deviation (a robust SD).

Units are stops, standing-position repeats, or looks (station × pedestrian). Units with less than `min_unit_s` of samples are left out. A crossing repeat where the driver looked at the target in less than `repeat_min_looking_pct` (80%) of its samples is left out too, because the cue was not followed.

Per recording, the gaze input table reports:
- the median and the maximum |yaw bias| over units;
- the median yaw and pitch precision over units.

Yaw is the narrow axis for a pedestrian, so it decides most mappings.

## Mapping

On looking samples within the distance bands `bands_m` (5–55 m in 10 m bands), the mapping table reports the % mapped to the looked-at target by each of these:

| Mapping | Rule |
|---|---|
| **system** | `attended_id` is the target (or its camera-only duplicate) |
| **2° cone**, a nearest-box rule (`cone_tol_deg`, default 2°) | the candidate with the smallest angular distance from the gaze ray to its box, if within the tolerance. Ties (the ray inside both boxes) go to the nearer object |
| **centre ray** | the cone with 0° tolerance: the gaze ray must hit the box |

All three are scored on the same samples. The baselines see the same candidates as the system: every 3D object, and every camera-only detection as a box at its estimated depth. The angular distance is exact (`frames.md`).

**Other outcomes** reported next to the mapping score:
- `system_other_target`: the other pedestrian, in the two-pedestrian protocol;
- `system_other_object`: another object;
- `system_none`: no object.

**Distance bands:**
- standing target: the unit's median 3D distance;
- moving target: its 3D distance interpolated in time, and before its first 3D box, the camera's distance estimate.

Cells with less than `min_cell_s` (3 s) of looking time are not reported.

**Competitor subset:** looking samples where another candidate (not the target) is within the cone tolerance of the gaze. These are the samples where the mapping has a real choice to make. Away from them, a nearest-box rule scores whatever the gaze error allows.

**Competitor episodes** (`competitor_episodes.csv`): the competitor subset split into episodes. Samples of one unit (and, with two pedestrians, one looked-at pedestrian) with the same competitor source belong to one episode unless more than `episode_gap_s` (0.5 s) apart. Each episode gives:
- its time, duration, the target's distance and input state;
- its **main competitor**, the most frequent of its samples' competitors. A sample's competitor is the nearest other 3D object if one is within the tolerance (source `3D`, or `other target` for the other pedestrian), else the nearest other candidate (`camera-only`, or `other target`). For each: ID, source, class and distance, and how many different competitors the episode had;
- **box gap**: the angular gap between the target's box and the competitor's as seen from the eye (0 = they overlap in view, e.g. a car parked behind a pedestrian);
- the median angular distance from the gaze to the target's box and to the competitor's;
- the % of its samples mapped to the target by the system, the 2° cone, the 3D-first cone (Robustness) and the centre ray, and how often the system chose another object or none.

`competitor_summary.csv` pools the episodes per recording and by the competitor's source, weighting by samples. Pooled over all sources, its scores equal the competitor columns of the mapping table; its `3D` rows are the samples with another 3D object within the tolerance, as in the 3D-first robustness check. Because the cue fixes the looked-at object, these are the samples where the ground truth comes from the protocol and the gaze alone could not decide.

**Tolerance sweep:** the cone's score from 0° to `sweep_max_deg`, with the system's score for reference. Where nothing else is near the gaze, the cone's curve is the distribution of the gaze-to-box distance: it measures the gaze input, not the mapping.

## Crossings

The crossing protocol's walks between a left and a right position at the same depth. Per crossing, and pooled by depth and direction:
- the mapping score, as above;
- input state;
- **along-track error** = yaw error signed with the walking direction (+ = gaze ahead of the pedestrian), on samples where the pedestrian's lateral speed is at least `walk_min_lat_speed_m_s`.

A constant yaw bias shows as +b one way and −b the other. Their mean shows a systematic lead or lag, which includes the age of the object lists.

## Car approach phases

Per approach:
- **lead-in:** looking samples with the car camera-only only, before its first 3D box;
- **in 3D beyond:** in 3D, but farther than the farthest distance at which the system mapped the gaze to it in 3D;
- **in 3D within:** in 3D, within that distance.

Each phase reports its duration, the % mapped by the system, and, for the in-3D-beyond phase, the % mapped by the cone. A system that only maps within a fixed range shows up as time in "in 3D beyond".

## Robustness

| Check | What it shows |
|---|---|
| Look gate at `gate_sensitivity_deg` (5 / 10 / 15°) | whether the results depend on the gate; the table is rebuilt for each gate |
| Saccades kept | whether removing saccades removes misses |
| Unscored time | share of clean time inside the units with no box for the target or the gaze beyond the gate |
| 3D-first cone | a stronger baseline: 3D candidates first, camera-only ones only if no 3D box is within the tolerance. Scored on all samples, on the competitor subset, and on the samples with another 3D object within the tolerance (`competitor_3d_s`), where preferring 3D boxes can go wrong |

## Statistics

The protocol is repeated per driver and condition; the unit of analysis is the stop, repeat, look or approach. The tables pool samples per recording. `mapping_units.csv` and `gaze_input_units.csv` give the per-unit values behind them, for spreads or mixed models across drivers.
