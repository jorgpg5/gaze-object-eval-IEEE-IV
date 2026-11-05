"""Every setting the evaluation uses, in one place.

Pass a dict with any of these keys to override them, e.g.
``goeval.evaluate(paths, params={"look_gate_deg": 15.0})``.
Durations are in seconds, angles in degrees, distances in metres.
"""

DEFAULTS = dict(
    # ---- object lists -> gaze samples
    max_frame_age_s=0.1,        # a gaze sample uses the latest object list of each source at most this old

    # ---- gaze artefacts (removed before scoring)
    saccade_deg_s=150.0,        # gaze angular speed above this = saccade
    blink_before_s=0.25,        # with a blink counter: window around each increment ...
    blink_after_s=0.30,         # ... (profile these on your own DMS: the counter lags the closure)
    blink_merge_s=0.2,          # blinks closer than this are one blink
    blink_pitch_drop_deg=1.5,   # without a blink signal: pitch dips below the running median by this much ...
    blink_median_window_s=1.0,  # ... (running-median window)
    blink_max_s=0.6,            # ... lasting at most this long (longer = a real downward look), and dropouts this short
    blink_min_s=0.065,          # ... and at least this long

    # ---- ground truth
    look_gate_deg=10.0,         # gaze farther than this from the cued target's centre = looking elsewhere

    # ---- following the target across tracker ID changes
    stitch_max_gap_s=2.5,       # a new ID continues the target if it starts within this after the last ID ends ...
    stitch_overlap_s=0.5,       # ... or up to this before ...
    stitch_base_m=1.0,          # ... within base + speed x gap of the last position ...
    stitch_speed_m_s=2.0,
    # (... with the same class, or class "unknown")

    # ---- standing / walking segmentation (from the target's 3D track)
    stop_bin_s=0.5,             # positions are binned at this interval
    stop_smooth_bins=5,         # median over this many bins before differencing
    stop_speed_m_s=0.25,        # slower than this = standing
    min_stop_s=3.0,             # a stop lasts at least this long (after trimming)
    stop_trim_s=0.5,            # trimmed off both ends of every stop
    walk_min_s=0.2,             # a gap between two stops shorter than this is not a walk
    side_m=1.5,                 # |y| above this = left / right of the lane, else centre
    depth_gap_m=4.0,            # stops further apart than this in x are at different depths
    cross_min_dy_m=3.0,         # a walk between stops is a crossing if y changes this much
    interp_max_s=2.0,           # a moving target missing from the object lists this long keeps an interpolated box

    # ---- car approach
    lane_half_m=4.0,            # the car drives in the ego lane: |y| below this
    approach_gap_s=5.0,         # in-lane rows further apart than this belong to different approaches
    min_track_s=0.43,           # ignore in-lane tracks seen for less than this
    car_lead_in_s=10.0,         # camera-only lead-in kept before the car enters 3D

    # ---- candidates for the baselines
    dup_cover=0.5,              # a camera-only box at least this much inside the target's box (in view) is the target

    # ---- metrics
    bands_m=[5, 15, 25, 35, 45, 55],    # distance bands (eye to object centre)
    min_cell_s=3.0,             # table cells with less looking time than this are not reported
    cone_tol_deg=2.0,           # tolerance of the nearest-box baseline in the main tables
    sweep_max_deg=4.0,          # tolerance sweep: 0 .. this ...
    sweep_step_deg=0.25,        # ... in these steps
    upper_body_frac=0.75,       # pitch reference: this fraction of the box height (upper body)
    min_unit_s=0.43,            # gaze-input table: units with less 3D looking time than this are left out
    repeat_min_looking_pct=80.0,  # crossing: repeats where the driver looked at the target less than this are left out
    walk_min_lat_speed_m_s=0.5,   # crossing: lateral speed above which the pedestrian is walking ...
    lat_speed_bin_s=0.25,       # ... measured between bins of this length ...
    lat_speed_smooth_bins=3,    # ... after a median over this many bins
    gate_sensitivity_deg=[5.0, 10.0, 15.0],   # robustness: the results with these look gates
    car_bin_m=4.0,              # car approach figure: distance bins
    fig_min_s=1.0,              # figures: a plotted value needs at least this much looking time
)


def params(overrides=None):
    p = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(p)
        if unknown:
            raise KeyError(f"unknown settings: {sorted(unknown)}")
        p.update(overrides)
    return p
