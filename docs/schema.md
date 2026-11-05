# Log format

Each recording is one folder with three files:

```
my_recording/
├── recording.json   what was recorded
├── gaze.csv         one row per gaze sample, with the system's output
└── objects.csv      the object lists the system mapped against
```

Check a folder with `python3 scripts/check_schema.py my_recording`. It reports **errors** (the evaluation will not run), **warnings** (it runs, but something looks off: units, conventions, unknown IDs) and **info** (sample rate, validity, how many samples have an object list).

Coordinates are in one vehicle frame (x forward, y left, z up, metres) and angles in degrees; see `frames.md`.

## recording.json

```json
{
  "name": "crossing_driver1",
  "protocol": "crossing",
  "condition": "standard"
}
```

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Label used in every table and figure. |
| `protocol` | yes | `walkaway`, `crossing`, `two_pedestrians` or `car_approach` (`protocol.md`). |
| `condition` | yes | Free label for the input condition, e.g. `standard`, `degraded`, `sunglasses`. Recordings with the same condition are grouped in the figures. |
| `target_ids` | no | The cued target's track IDs, if they should not be found from the object lists: a list for `walkaway` and `crossing`, `{"left": [...], "right": [...]}` for `two_pedestrians`. Not used for `car_approach`. |

Other keys are kept but not read.

## gaze.csv

One row per DMS sample, in time order.

| Column | Required | Meaning |
|---|---|---|
| `t_s` | yes | Time (s), strictly increasing, on the same clock as `objects.csv`. |
| `valid` | yes | 1 if the DMS has a gaze estimate for this sample, else 0. |
| `eye_x`, `eye_y`, `eye_z` | yes | Eye position (the origin of the gaze ray), vehicle frame (m). May be empty when `valid` = 0. |
| `gaze_yaw_deg`, `gaze_pitch_deg` | yes | Gaze direction, vehicle frame (deg). Yaw 0 = straight ahead, + = left; pitch + = up. May be empty when `valid` = 0. |
| `attended_id` | yes | **The system's output**: the ID (from `objects.csv`) of the object it maps this sample's gaze to; empty when it maps the gaze to no object. |
| `blink_count` | no | The DMS's cumulative blink counter. If present, blinks are removed around each increment. |
| `blink` | no | 1 at samples the DMS flags as a blink. Used if there is no `blink_count`. Without either, blinks are found from short pitch dips and dropouts. |

Log the gaze **as the system used it**, after any smoothing or per-driver calibration the system applies, so that the gaze input layer describes what the mapping actually received.

The sample rate is measured from `t_s` and used to turn sample counts into seconds; it does not need to be constant.

## objects.csv

The object lists the system mapped the gaze against, one row per object per list. Two sources:

- `3d`: objects with a box placed in 3D (e.g. LiDAR or fused tracks);
- `camera`: camera-only detections with no 3D placement, given as a box at their estimated depth.

| Column | Required | Meaning |
|---|---|---|
| `t_s` | yes | Time of the list (s). All rows of one list share the same `t_s`. |
| `source` | yes | `3d` or `camera`. |
| `id` | yes | Integer track ID. **Empty = an empty list** at this time (write one such row when a list holds no object, so that the previous list is not reused). |
| `class` | yes | `pedestrian`, `car`, `cyclist`, ..., or `unknown` (e.g. a far object that lost its camera class). |
| `x`, `y`, `z` | yes | Box centre, vehicle frame (m). |
| `length`, `width`, `height` | yes | Box size along its heading, across it, and vertically (m). |
| `yaw_deg` | yes | Box heading about the vertical axis (deg, + = left). |

**IDs.** 3D and camera-only objects share one ID space. An object keeps its ID when it moves between camera-only and 3D, and `attended_id` uses the same IDs. Two objects never share an ID at the same time.

**Which list a gaze sample uses.** For each valid gaze sample and each source, the evaluation uses the latest list at or before the sample, if it is at most `max_frame_age_s` (default 0.1 s) old. If your system logs the object list it used for each gaze sample, write that list with the gaze sample's `t_s`. Only valid gaze samples are scored.

**Camera-only boxes.** If your perception gives camera-only detections as image boxes with a depth estimate, convert them with `goeval.geom.image_box_to_vehicle`:

```python
from goeval.geom import image_box_to_vehicle
box = image_box_to_vehicle(u1, v1, u2, v2, depth_m, fx, fy, cx, cy, cam_x, cam_y, cam_z)
# -> x, y, z, length, width, height, yaw_deg (a box 0.3 m deep at the estimated depth)
```

It assumes a pinhole camera looking along +x (image u to the right, v down), with depth measured forward to the object's near face. Camera-only detections without a depth estimate cannot be candidates and should be left out.

## Example rows

`gaze.csv`
```
t_s,valid,eye_x,eye_y,eye_z,gaze_yaw_deg,gaze_pitch_deg,attended_id,blink_count
10.000000,1,1.0010,-0.3490,1.2003,14.2100,-0.9800,,12
10.021739,1,1.0012,-0.3488,1.2001,14.1400,-1.0200,17,12
10.043478,0,,,,,,,12
```

`objects.csv`
```
t_s,source,id,class,x,y,z,length,width,height,yaw_deg
9.933333,camera,40,car,61.95,7.80,0.82,0.30,1.75,1.46,0.0
10.000000,3d,17,pedestrian,13.02,3.01,0.88,0.50,0.60,1.75,0.0
10.000000,3d,21,car,25.00,-4.50,0.75,4.50,1.80,1.50,0.0
10.100000,3d,17,pedestrian,13.03,2.98,0.88,0.50,0.60,1.75,0.0
```

## What the evaluation does not need

It does not need the system's internals, settings, confidence values or source code, nor any manual time stamps. Stops, positions, crossings, stations and car approaches are found from the cued target's own 3D track (`protocol.md`).
