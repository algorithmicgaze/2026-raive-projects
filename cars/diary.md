# Cars: clean plate diary

Source: `media/147A3791.MP4`, 30 min of a four-lane highway from a bridge,
4K at 25 fps, fixed camera. Goal: an instrument where each lane has a
slider for the amount of traffic. First step: an empty road (clean plate).

Working set: every second keyframe (1 per 0.96 s), scaled to 1920x1080,
1918 JPEG frames in `media/frames-1080/`. Scripts in `plate/`.

## 01 Source frame

`diary/01_source_frame.jpg`. A typical moment. The left lane and hard
shoulder are often empty; the two middle lanes are jammed for long
stretches, trucks stand still for minutes.

## 02 Temporal median

`diary/02_median.jpg`, `plate/clean_plate.py`, every 3rd frame (640).
Per pixel, sort the 640 values and take the middle one. Where the road
is visible more than half of the time, the middle value is road. Lane 1
and the shoulder come out clean. The middle lanes show soft ghosts.

## 03 Spread map

`diary/03_spread.jpg`. Median absolute deviation per pixel. Bright means
the samples disagree a lot, so the median is a guess. It lights up
exactly the two middle lanes.

## 04 Mode (most frequent colour) fails

`diary/04_mode.jpg`. Idea: instead of the middle value, take the most
common one, so road wins even below 50%. Result: black and white
speckle. Black cars and white trucks each land in one saturated colour
bin; grey asphalt spreads over many neighbouring bins and loses the
vote. Not a bug, a lesson: the road is not the most consistent colour,
it is the most common surface.

## 05 Iterative masked median

`plate/clean_plate2.py`, all 1918 frames via a disk memmap (12 GB).
Start from the median. For each frame and pixel: if the value is close
to the current plate (tolerance 18 after a 5x5 blur), call it road.
Recompute the plate as the median of the road samples only. Repeat.
`diary/06_iter1.jpg` is one pass; ghosts in the middle lanes are mostly
gone. `diary/07_roadfrac.jpg` shows how often each pixel was road:
the middle lanes only 20 to 30 percent of the time.

## 06 Three rounds, holes, timeline

`diary/08_iter3.jpg` after three rounds (holes 0.12% of pixels, kept
from the plain median). `diary/09_holes.jpg` marks the holes in orange:
tree edges, lamp posts, the crash barriers. Those are not vehicles.
`diary/10_occupancy.jpg`: fraction of road pixels that differ from the
plate, per second. The road is never empty: best moment 28% occupied
(`diary/11_emptiest_frame.jpg`, t=202 s), median 57%. So no single
frame can serve as plate; it has to be assembled.

## 07 Camera drift

Frederik spotted that the camera shifted. `plate/measure_drift.py`:
phase correlation of the graffiti panel against frame 0 gives the
per-frame shift, `diary/13_drift.png`. About 1 px steps in x, a slow
2 px wander in y at 1080p, so 2 to 4 px at 4K. Enough to blur every
edge and to misalign sprites later. Fix: `plate/stabilize.py`, SIFT on
the static parts (road polygon masked out), RANSAC similarity transform
to frame 0, transforms saved in `output-plate/transforms.npy` for reuse
on the 4K frames. Then the plate is rebuilt on the aligned frames.

After stabilisation the residual drift is below 0.3 px on every frame
(`diary/14_drift_after.png`). Transforms: shift up to 11 px, rotation
below 0.07 degrees, scale within 0.06 percent, so a similarity transform
is enough; no need for a homography.

## Next: the instrument

Reference: Fernando Livschitz, Rush Hour (one intersection, many takes,
cars cut out and layered). Plan:

1. Vehicle clips: frame minus plate gives a mask; track each vehicle
   from under the bridge to the bottom edge; store as a short clip with
   alpha and its lane. Harvest only from light-traffic moments (see
   occupancy timeline) so masks do not merge.
2. Library sorted per lane.
3. Playback over the plate: per-lane spawn rate from a slider, clips
   kept at a safe gap. Zero is empty, maximum is a jam. The video always
   plays; only the density changes.
4. Figment node: JS + WebGPU, inputs plate, clip library, four numbers;
   the sliders can then be driven by MIDI, hand tracking or sensors.

## 08 The instrument, rush-hour style

Scripts in `instrument/`. Pipeline:

1. `lanes.py`: four lane polygons in plate coordinates, measured from the
   lane markings with a Hough transform (the lane 3/4 boundary is
   interpolated from equal lane widths).
2. Windows of 60 s are decoded at 25 fps, aligned to the plate's
   reference frame (`plate/stabilize.py --ref --est-scale 0.5`).
3. `segment.py`: per window a local plate (masked median of the window's
   own frames, global plate as hint) because cloud cover changes the
   asphalt tone between windows by more than the threshold. Vehicles are
   labelled with seeds: strong differences (car bodies) are seeds, weak
   differences (shadows) join the nearest seed within 30 px, the rest is
   dropped. Without this, shadows and the hedge shadow along the right
   barrier link every car in lanes 2 to 4 into one blob.
4. `harvest.py`: tracks by nearest bottom-centre, exclusive matching,
   merge and split detection by box overlap, flicker-tolerant taints
   (a fragment that lives under 15 frames does not count). A clip must
   enter under the bridge, leave at the bottom or right edge, stay in one
   lane and never merge with another vehicle. Gaps of a few frames hold
   the previous cut-out. Crops are colour-matched to the global plate
   with a low-frequency ratio map.
5. `play.py`: Python player. Per lane a number of cars wanted (0..8).
   Below the target a clip starts (with jitter) as soon as it can drive
   its whole life without touching another car in its lane; above the
   target the farthest car fades out over 20 frames. The same clip is
   not picked twice in a row. Far cars draw first. Writes an mp4.
6. `pack_clips.py` + `figment/highway.js`: sprite sheets and manifest,
   and the Figment node (fork any image node, paste the source; project
   files store forked node types). Inputs: plate image, manifest, four
   lane counts 0..8, fade frames, gap, seed. Draws on an OffscreenCanvas and
   uploads to the render target. Steps in real time in the editor, one
   step per frame on export.

`diary/17_lane_occupancy.png`: per-lane occupancy per second over the
film. Lane 1 averages 40%, lanes 2 to 4 65 to 70% with flat plateaus
(stopped traffic). Clips for lanes 2 to 4 only come from the moments in
between, so the harvest runs over thirteen 60 s windows.

Yield per 60 s window in lane 1: about 10 clips. Lanes 2 to 4: near zero
in jammed windows, a few in flowing ones.

Frederik's direction (3 Sep): a slider is the number of cars in that
lane, from none to a few; cars start under the bridge and roll; a
cross-fade is acceptable when the count drops. It is an art piece played
like an instrument, so close to accurate is enough. Implemented in the
page player, `play.py` and `figment/highway.js`.

Sanity rules added after inspecting lanes 2 to 4: every one of their
clips was a merged pack or a fragment. A vehicle is never wider than
1.3 lanes at its row, nor taller than 80% of the road; a crossing takes
at least 50 frames. `clean_clips.py` applies the rules to an existing
harvest (14 removed; lanes 2 and 4 went to zero, lane 3 to two).

Capacity: packed nose to tail only three flowing cars fit in a lane,
because under the bridge a car moves 1 px per frame while its cut-out is
74 px tall. Fixes: mid-road entry with a 20-frame fade-in when the
bridge has been blocked for a second, and the touch test on the core
60% of the box (the box holds shadow and padding). Capacity now 5 to 6.

Lane borrowing (toggle, default on): lanes with fewer than 8 own clips
take lane-1 clips slid sideways along the road plane, same rows, x
moved to the target lane's centre at that row (`lanes.lane_center_x`).
Same size and speed; the viewing angle is slightly off, most in lane 4.
