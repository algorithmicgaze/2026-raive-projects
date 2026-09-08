# Source-footage masks and contact shadows

This pipeline keeps the vehicle pixels from the stabilized video and adds a
soft, translucent contact shadow. It uses SAM 2.1 box/point segmentation, retained
vehicle tracks, component cleanup and hole filling. Tracking prompts follow a
continuous identity span, excluding unreliable observations and sudden switches
to other vehicles. Shadows are estimated from
local luminance attenuation relative to the clean plate.

## Inputs

Keep these private assets under a Cars folder:

- `media/highway-stabilized-1080p.mp4`: the complete 1080p, 25 fps recording.
- `output-figment/plate.png` and the original `manifest.json`.
- `output-figment/masked/tracking/*/{job,motion,detections}.json`: retained tracks.
- `output-clips/` and `output-clips-groups/` metadata (`meta.json`).
- A SAM 2.1 Base checkpoint, `sam2.1_b.pt`. No new training is required.

Python 3.11+, uv, FFmpeg and Node.js are needed to build and review. The prepared
Figment instrument needs none of these tools or model weights at playback time.
The default device is Apple Silicon (`mps`); pass `--device cpu` or `--device cuda`
on other hardware. Dependencies are declared inline in the Python scripts.

## Build, review and activate

Run from this directory, substituting your own asset and runtime paths:

```sh
uv run build.py --root /path/to/Cars --checkpoint /path/to/sam2.1_b.pt
uv run review.py /path/to/Cars
# Optional: apply visually reviewed ranges, then regenerate contact sheets.
uv run trim.py /path/to/Cars /path/to/Cars/output-figment/masked/review-overrides.json
uv run review.py /path/to/Cars
npm install --prefix /path/to/local-runtime @napi-rs/canvas
uv run integrate.py /path/to/Cars --prepare
node verify-renderer.cjs /path/to/Cars /path/to/local-runtime/node_modules /path/to/Cars/output-figment/masked/review/highway-candidate-source.js
uv run integrate.py /path/to/Cars
```

Builds resume by completed clip. `--only lane1_f0_0048` limits a trial; `--refresh`
rebuilds existing results. Optional `masked/prompt-overrides.json` (under
`output-figment/`) maps atlas IDs to `extend_top` (a fraction of the tracked height)
and `min_top` (a source-image y coordinate). `hold_height: true` keeps the
expansion from shrinking when the cab exits the image. This corrects truck tracks that cover
only the cab; the resulting segmentation still uses actual source pixels. Review
these overrides carefully because a wider prompt can include following traffic.
Changing an override invalidates that clip’s cached build. Optional `--shards N --shard K` splits independent clips
across processes; use distinct K values from zero through N−1. Finish all shards
before reviewing or activating. Outputs are written atomically.

Review contact sheets, flagged crop boundaries, crowded approaches and exit
frames in `output-figment/masked/review/`. Automatic checks cannot establish visual
quality on their own. `trim.py` accepts a JSON map of atlas IDs to inclusive
source-window `start`/`end` frame numbers and a `reason`. It retains the full atlas
and an `untrimmed-jobs/` metadata backup, changes only the playback range, and
rebuilds the manifest while preserving occupancy variants. Run it after all builds
and retries have finished.

The renderer check exercises both old grid atlases and new
variable-size shelf atlases, forward/reverse frame selection, lane masks and
lane borrowing. Live webcam input is not part of this check.

`integrate.py` requires a complete manifest and renderer verification. It updates
only the embedded Highway code and manifest path in `highway.fgmt` and
`highway-hands.fgmt`. Runnable `*-original-backup.fgmt` files stay alongside them,
referencing the untouched original `manifest.json` and `clips/`. Other controls,
connections and node layout remain unchanged.

## Data format and limits

The new manifest is `manifest-masked.json`. PNG atlases in `masked/clips/` carry
real RGBA transparency. `frameRects` lists `[x,y,width,height]` for each stored
frame inside its atlas; `boxes` holds placement in plate coordinates at 25 fps.
Every second source frame is stored, preserving the original 12.5 fps sprite
sampling rate. Intermediate positions are interpolated. New rendering code also
accepts legacy grid atlases, including the backup projects.

The scene and tracking metadata are specific to the workshop recording. Clip
labels encode their start time in seconds; source indices are checked against the
retained detection filenames. Occluded parts remain occluded; this process does
not invent hidden vehicle surfaces. Dark or closely overlapping vehicles and
unusual shadows require visual review.

Model/API reference: [Ultralytics SAM 2 documentation](https://docs.ultralytics.com/models/sam-2/).
Footage, checkpoints, generated atlases, reports and node dependencies belong
outside the public source repository.
