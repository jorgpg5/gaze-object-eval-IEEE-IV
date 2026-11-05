# Frames and conventions

**Vehicle frame.** Right-handed: x forward, y left, z up, in metres (ISO 8855). The origin can be anywhere fixed to the vehicle (rear axle, ground below the front bumper, ...), as long as the eye position and every object box use the same one.

**Gaze direction.** Yaw ψ and pitch θ in degrees, in the vehicle frame:

```
d = (cos θ cos ψ,  cos θ sin ψ,  sin θ)
```

ψ = 0 is straight ahead along +x, ψ > 0 to the left, θ > 0 up. The gaze ray starts at the eye position (`eye_x`, `eye_y`, `eye_z`). If your DMS reports gaze in its own camera frame, transform both the eye position and the direction into the vehicle frame before logging.

**Boxes.** Centre (x, y, z), size (length along the heading, width across it, height), and heading yaw about +z (deg, + = counter-clockwise seen from above, i.e. turning left). Boxes are upright: no pitch or roll.

**Bearing and elevation of a target** (used for the gaze input layer). Bearing = atan2(y − eye_y, x − eye_x) of the box centre. Elevation is taken to `upper_body_frac` (default 0.75) of the box height above its bottom face, because drivers look at a pedestrian's upper body rather than its centre.

**Angular distance to a box.** The angle between the gaze ray and the nearest point of the box: 0 when the ray hits the box, otherwise the minimum over its 12 edges (`goeval.geom.angle_to_box`). It is exact for any box orientation and distance.

**Distances.** From the eye to the box centre.

**Camera helper.** `image_box_to_vehicle` assumes a pinhole camera looking along +x with no rotation relative to the vehicle: image u to the right (towards −y), v down (towards −z), principal point (cx, cy) and focal lengths (fx, fy) in pixels, camera position (cam_x, cam_y, cam_z) in the vehicle frame.
