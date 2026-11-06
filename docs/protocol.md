# Protocols

The vehicle is stationary and the driver sits in the driver's seat. Pedestrians and a car stand or move at known positions, and the driver is told which one to look at. Because the cue fixes the looked-at object, the evaluation needs no annotation of where the driver looked.

Before each session, calibrate the gaze for the driver as your DMS requires. If you fit per-driver offsets after recording instead, fit them on data that is not scored (a separate calibration segment, or leaving out the stop being scored), and say so when you report the gaze input: offsets fitted on the scored stops make the bias look smaller than a calibration done beforehand would. Then record each protocol as a separate recording, for each driver and each input condition (e.g. `standard`, and a `degraded` condition such as eyeglasses that reduce the DMS's accuracy).

## The four protocols

The layouts below are the ones used in the reference recordings. Distances are from the driver's eye.

| Protocol | Layout | Driver's task | What it isolates |
|---|---|---|---|
| `walkaway` | One pedestrian in the lane ahead (\|y\| < 1 m) stops at increasing distances, e.g. about 7, 12, 17, 22, 32 and 42 m, standing about 15 s at each and walking away between stops. | Look at the pedestrian throughout, standing and walking. | Distance: the same isolated target as its angular size shrinks; the hand-over from 3D to camera-only at range. |
| `crossing` | One pedestrian stands at the left and right edges of the road (\|y\| ≈ 4–5.5 m) at three depths, e.g. 13, 23 and 33 m. At each depth they cross from side to side, giving two repeats of each position of about 10 s. | Look at the pedestrian throughout, including while they cross. | Bearing and lateral motion (pursuit); repeats of the same position; objects behind the pedestrian (e.g. parked cars) as competing candidates. |
| `two_pedestrians` | Two pedestrians, one on each side of the road, step back together through stations at, e.g., 13, 23, 33 and 43 m, about 30 s each. | Switch between the two pedestrians when told, and follow the one you are looking at while they walk. | Identity at wide separation: two objects of the same class at the same depth, on opposite sides of the road, so far apart compared with the gaze error. Does the system map the gaze to the one looked at, and not to the other? Close competitors need a protocol of their own. |
| `car_approach` | A car drives towards the vehicle in its lane from beyond the 3D perception range (e.g. 70 m and more) to a few metres, twice. | Look at the car throughout. | A larger target from far away: camera-only lead-in, the moment it enters 3D, and any range limit of the mapping. |

## What the evaluation finds by itself

No manual time stamps are needed. From the object lists it finds:

- **The cued target.** The pedestrian seen most often, followed across tracker ID changes. For two pedestrians, every pedestrian ID on each side of the lane (|y| > `side_m`). For the car, the car or unknown-class tracks in the ego lane (|y| < `lane_half_m`).
- **Stops.** Stretches where the target's position holds still for at least `min_stop_s` (3 s) after trimming `stop_trim_s` (0.5 s) at both ends.
- **Crossing positions.** Each stop is labelled by depth (stops within `depth_gap_m` of each other in x share a depth) and side (L / C / R), e.g. `13 m L #2`. Crossings are the walks between positions that change side at one depth.
- **Two-pedestrian stations.** Where both pedestrians stand at once. The looked-at pedestrian is taken as the one nearer the gaze, within the look gate.
- **Car approaches.** Runs of in-lane 3D rows split at gaps longer than `approach_gap_s`, extended back to the first track's camera-only detections.
- **Walks.** The time between consecutive standing units, scored as the `walking` phase.

If a scene breaks these assumptions (another pedestrian lingers in view, or a target was misplaced), give the target's track IDs in `recording.json` (`schema.md`).

## Recording checklist

- Log the gaze **as the system uses it**, after per-driver calibration and any smoothing, on the same clock as the object lists.
- Log the object lists the system mapped against, including camera-only detections and empty lists (`schema.md`).
- Keep other pedestrians out of the scene. Parked cars and other static objects are welcome: they are the competing candidates.
- Hold each position for at least 6 s (10 s or more is better), so that a stop survives trimming and blinks.
- Brief the driver to keep looking at the target while it walks, and, for two pedestrians, to switch only when told. If you can, log the time of each cue (a button press or an audio track): the evaluation does not use it yet, but it gives an independent check of which pedestrian was looked at.
- Note anything that went wrong (the driver looked away, a pedestrian stood in the wrong place). The robustness checks show how much looking time the look gate removed.

## Adding a protocol

A protocol is a function that turns the object lists into units (`goeval/segment.py`) plus a branch in `goeval/table.py:build` that says which object is the cued target in each unit. The metrics, baselines and report work on the resulting per-sample table unchanged.
