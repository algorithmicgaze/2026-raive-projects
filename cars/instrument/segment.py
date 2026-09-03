"""Vehicle masks: what differs from the clean plate."""
import cv2
import numpy as np

# Road area in 1080p plate coordinates: the four lanes plus the shoulder,
# from the underside of the bridge to the bottom edge. Everything outside
# (sky, trees, barriers) is ignored: clouds and leaves move too.
ROAD_ROI = np.array([(560, 425), (1135, 425), (1920, 900), (1920, 1080), (140, 1080)], dtype=np.int32)
_roi_cache = {}


def road_roi(shape):
    if shape not in _roi_cache:
        m = np.zeros(shape, np.uint8)
        cv2.fillPoly(m, [ROAD_ROI], 255)
        _roi_cache[shape] = m
    return _roi_cache[shape]


def vehicle_mask(frame, plate, tol=28, min_area=500):
    """Binary mask (uint8 0/255) of pixels that are not plate.
    Shadows are kept on purpose: a car without its shadow floats."""
    d = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(-1).astype(np.uint8)
    d = cv2.GaussianBlur(d, (5, 5), 0)
    m = (d > tol).astype(np.uint8) * 255
    m &= road_roi(m.shape)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[lab], 255, 0).astype(np.uint8)


def soft_alpha(mask, feather=3):
    """0..1 alpha with a soft edge so sprites do not cut hard."""
    a = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), feather)
    return a


def local_plate(files, global_plate, step=10, tol=45, min_samples=8):
    """Plate with this window's own lighting: median of the samples that
    are near the global plate (the global plate is only the hint).
    Pixels with too few road samples fall back to the global plate."""
    idx = list(range(0, len(files), step))
    stack = np.stack([cv2.imread(str(files[i])) for i in idx])
    d = np.abs(stack.astype(np.int16) - global_plate.astype(np.int16)).max(-1)
    d = np.stack([cv2.blur(x.astype(np.float32), (5, 5)) for x in d])
    road = d < tol
    f = stack.astype(np.float32); f[~road] = np.nan
    med = np.nanmedian(f, axis=0)
    ok = road.sum(0) >= min_samples
    med[~ok] = global_plate[~ok]
    return np.nan_to_num(med).astype(np.uint8)


def ratio_map(global_plate, local, sigma=40):
    """Per-pixel colour gain that turns this window's lighting into the
    global plate's lighting. Low frequency only, so car detail survives."""
    g = cv2.GaussianBlur(global_plate.astype(np.float32), (0, 0), sigma)
    l = cv2.GaussianBlur(local.astype(np.float32), (0, 0), sigma)
    return np.clip(g / np.maximum(l, 1.0), 0.5, 2.0)


def vehicle_labels(frame, plate, tol=28, seed_tol=55, seed_erode=5, min_seed_area=600, reach=30):
    """Label image of vehicles. Car bodies (strong difference) are the
    seeds; softer differences such as shadows join the nearest seed if
    they lie within `reach` px, else they are dropped. Touching cars end
    up with separate labels, unless their bodies overlap in the image.
    Returns (labels int32, stats like connectedComponentsWithStats)."""
    d = np.abs(frame.astype(np.int16) - plate.astype(np.int16)).max(-1).astype(np.uint8)
    d = cv2.GaussianBlur(d, (5, 5), 0)
    roi = road_roi(d.shape)
    low = ((d > tol).astype(np.uint8) * 255) & roi
    low = cv2.morphologyEx(low, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    low = cv2.morphologyEx(low, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    seeds = ((d > seed_tol).astype(np.uint8) * 255) & roi
    seeds = cv2.erode(seeds, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (seed_erode, seed_erode)))
    # one car, one seed: bridge the gap between windscreen and bonnet
    seeds = cv2.morphologyEx(seeds, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    n, slab, sstats, _ = cv2.connectedComponentsWithStats(seeds)
    small = sstats[:, cv2.CC_STAT_AREA] < min_seed_area
    small[0] = True
    slab[small[slab]] = 0
    # nearest seed pixel for every pixel, then its seed id
    dist, near = cv2.distanceTransformWithLabels((slab == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(slab)
    pix_to_seed = np.zeros(near.max() + 1, np.int32)
    pix_to_seed[near[ys, xs]] = slab[ys, xs]
    labels = pix_to_seed[near]
    labels[(low == 0) | (dist > reach)] = 0
    # compact ids and stats
    ids = np.unique(labels[labels > 0])
    remap = np.zeros(labels.max() + 1, np.int32); remap[ids] = np.arange(1, len(ids) + 1)
    labels = remap[labels]
    k = len(ids) + 1
    yy, xx = np.nonzero(labels)
    l = labels[yy, xx]
    x0 = np.full(k, 1 << 30); y0 = np.full(k, 1 << 30); x1 = np.zeros(k, int); y1 = np.zeros(k, int)
    np.minimum.at(x0, l, xx); np.minimum.at(y0, l, yy); np.maximum.at(x1, l, xx); np.maximum.at(y1, l, yy)
    area = np.bincount(l, minlength=k)
    stats = np.stack([x0, y0, x1 - x0 + 1, y1 - y0 + 1, area], 1).astype(np.int32)
    stats[0] = 0
    return labels, stats
