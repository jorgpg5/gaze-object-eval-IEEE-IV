# Synthetic recordings

`generate.py` simulates the four protocols in `docs/protocol.md` in the log format of `docs/schema.md`. `data/` holds its output, and `expected/` the report the evaluation gives on it.

| Recording | Protocol | Condition | Yaw / pitch bias (deg) | Yaw / pitch noise SD (deg) |
|---|---|---|---|---|
| SYN-WALK | walkaway | standard | 0.8 / 0.4 | 0.3 / 0.5 |
| SYN-CROSS | crossing | standard | −0.6 / 0.3 | 0.3 / 0.5 |
| SYN-TWO | two_pedestrians | standard | 0.5 / −0.3 | 0.3 / 0.5 |
| SYN-CAR | car_approach | standard | 0.4 / 0.2 | 0.3 / 0.5 |
| SYN-CROSS-DEG | crossing | degraded | 2.5 / 1.5 | 1.2 / 1.5 |

Each recording also contains:
- **gaze:** blinks with a DMS blink counter, and glances at the instrument cluster;
- **object lists:** 3D detection that fades with distance, camera-only detections at an estimated depth, and one tracker ID switch (SYN-WALK);
- **competitors:** a car parked behind one crossing position, and a far car beside the approach lane.

`attended_id` comes from a stand-in "system": the nearest 3D box within 1.5° of the gaze, else the nearest camera-only box within 1.5°. It only exists so that the example produces a full report. It is not a model of any real system.

**What to look for in `expected/report.md`:**
- **The gaze input table recovers the simulated gaze input within sampling error.** SYN-TWO, for example, gives a median |yaw bias| of 0.50° and a yaw precision of 0.34°, against a simulated 0.5° and 0.3°.
- **Degraded input lowers every mapping alike.** The 2° cone scores above the stand-in's 1.5° rule only because it accepts more gaze error.
- **The crossing's along-track error carries the yaw bias,** +b one way and −b the other, plus a small lead from the 10 Hz object lists.
- **The car is mapped from where it enters 3D.** Before that, the system attends its camera-only detection.
- **The competitor episodes of SYN-CROSS all name the parked car** (3D, about 24 m away), overlapping the pedestrian in view (box gap 0°) at 13 and 23 m. The stand-in is itself a nearest-box rule, so it scores the same as the 3D-first cone there.

Regenerate with `python3 generate.py` (fixed seeds, so the output is identical).
