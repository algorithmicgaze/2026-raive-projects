"""Lane geometry of the highway in 1080p plate coordinates.

Five boundary lines, each given by x at the bottom row (y=1080) and x at
the bridge line (y=430). Measured from the lane markings on the plate
with a Hough transform; the lane 3/4 boundary is interpolated from the
equal lane widths. Lane 1 is the leftmost driving lane; the hard
shoulder lies left of boundary 0.
"""
import numpy as np

Y_BOTTOM, Y_BRIDGE = 1080.0, 430.0
BOUNDS = np.array([
    [615.0, 884.0],    # solid line: shoulder | lane 1
    [942.0, 950.0],    # lane 1 | lane 2
    [1285.0, 1005.0],  # lane 2 | lane 3
    [1622.0, 1060.0],  # lane 3 | lane 4
    [1960.0, 1115.0],  # lane 4 | right barrier
])
NUM_LANES = 4


def bound_x(i, y):
    """x of boundary i at row y."""
    t = (y - Y_BRIDGE) / (Y_BOTTOM - Y_BRIDGE)
    return BOUNDS[i, 1] + t * (BOUNDS[i, 0] - BOUNDS[i, 1])


def lane_of(x, y):
    """0..3 for the four driving lanes, -1 for shoulder, 4 for right of the road."""
    xs = [bound_x(i, y) for i in range(len(BOUNDS))]
    if x < xs[0]:
        return -1
    for i in range(NUM_LANES):
        if x < xs[i + 1]:
            return i
    return NUM_LANES


def lane_center_x(lane, y):
    return 0.5 * (bound_x(lane, y) + bound_x(lane + 1, y))


def lane_polygon(lane, y_top=Y_BRIDGE, y_bot=Y_BOTTOM):
    return np.array([
        (bound_x(lane, y_top), y_top), (bound_x(lane + 1, y_top), y_top),
        (bound_x(lane + 1, y_bot), y_bot), (bound_x(lane, y_bot), y_bot),
    ], dtype=np.float32)
