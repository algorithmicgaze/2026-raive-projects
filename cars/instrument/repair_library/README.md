# Repairing the vehicle library

The repair pipeline separates **appearance** from **motion**. GPT Image repairs
four reference views of each vehicle. The renderer blends the accepted views
along a smoothed track measured from the source footage. This avoids asking an
image model to place the vehicle independently in hundreds of frames.

The resulting PNGs contain real alpha transparency. They are small pose atlases,
not drop-in replacements for the old frame-by-frame atlases: use the updated
Highway node and `manifest-repaired.json` together. The original manifest and
clips remain available.

## Run a batch

Run these commands from `cars/output-figment`. Python dependencies are declared
inline and installed by `uv`. Preparation uses the local YOLO checkpoint at
`repaired/models/yolo11n.pt`, the original clip metadata, and the stabilized
source JPEGs in `cars/media/clips-stab`.

1. Prepare one job per unique original sheet:

   ```sh
   uv run ../instrument/repair_library/pipeline.py prepare
   uv run ../instrument/repair_library/pipeline.py status
   ```

   Each `repaired/jobs/ID/` contains `input.png`, `prompt.txt`, detection data,
   source references and `job.json`. Inspect the input to confirm that all four
   panels show the same target. Crowded approaches may require a reviewed
   tracking override in `prepare`. `prepare --only ID --refresh` refreshes a
   prepared job; it deliberately leaves ingested jobs alone.

2. Use the built-in GPT Image editing tool once per job, with `input.png` as
   the reference and `prompt.txt` as the prompt. Save the actual prompt if it is
   adjusted. Return four isolated views on solid green. The tool is an explicit
   step; this script does not call a paid API or require an API key.

3. Inspect each generated sheet for identity, complete bumpers/roofs, matching
   camera angles and accidental inclusion of another vehicle. Then ingest it:

   ```sh
   uv run ../instrument/repair_library/pipeline.py ingest ID /absolute/result.png
   ```

   This saves `generated.png`, removes the green backdrop, protects dark green
   paint, resizes with premultiplied alpha and writes `repaired/clips/ID.png`.
   It rejects empty or edge-clipped panels. For a bad individual view, record
   its zero-based index in `job.json` as `excluded_poses`; at least two views
   must remain. Regenerate if fewer than two are usable. Reapply current keying
   and reviewed exclusions to every saved result with:

   ```sh
   uv run ../instrument/repair_library/pipeline.py reingest
   uv run ../instrument/repair_library/audit.py .
   ```

4. Build the motion tracks and manifest:

   ```sh
   uv run ../instrument/repair_library/refine_motion.py .
   uv run ../instrument/repair_library/pipeline.py build
   ```

   Motion refinement is resumable and invalidates its cache when the reviewed
   source track changes. It follows moving features through the exit, then
   extrapolates when the target is no longer trackable. Review long extrapolated
   tails. `build` refuses incomplete libraries or old alpha-keying versions.
   For a reviewed motion-only correction, put the accepted observations in
   `job.json` as `motion_track`; the original reference views are retained.

5. Verify and preview the actual renderer, then create repaired project variants:

   ```sh
   npm install --prefix repaired/review/runtime @napi-rs/canvas
   node ../instrument/repair_library/verify-renderer.cjs . --video
   uv run ../instrument/repair_library/integrate.py .
   ```

   Video preview requires `ffmpeg`. Verification exercises every asset, alpha
   crossfades, fractional positions, reverse sampling, lane masks and lane
   shifting. The preview and per-vehicle plate composites go to
   `repaired/review/`. This is a renderer check, not a webcam/hand-input test.

   Integration leaves `highway.fgmt` and `highway-hands.fgmt` untouched. It
   creates `highway-ai-repaired.fgmt` and `highway-hands-ai-repaired.fgmt`,
   updates their embedded Highway code and manifest path, and asserts that all
   other nodes, settings and connections are preserved. Open the desired file
   in Figment. Do not run the project generator over a manually adjusted
   project; use this integration script.

## Rendering and limitations

The renderer crops every accepted pose to its alpha bounds and maps it onto
the same source-derived vehicle box. It blends adjacent views in a temporary
premultiplied canvas using weighted additive compositing, keeping solid body
pixels opaque, then applies the existing lane mask and bridge occlusion. Positions remain fractional
until drawing. Hand control, piano-roll timing, reverse movement and trains
continue to use the existing project controls.

This is a stable few-view reconstruction. Fine details can still change during
a blend, and hidden parts are inferred. The source track is smoothed rather
than a claim of pixel-perfect registration. Starts before the bridge are trimmed
with pose timestamps adjusted, and motion continues until the car leaves the
plate. Keep review images and generated
outputs local in the ignored output folder. For the previous full-spritesheet
white-van experiment, see `ai-test/f383/stabilized/`.

The two project files without the `-ai-repaired` postfix continue to use the
untouched original library.
