# Cars — playable highway

Turn highway footage into an instrument: control the number and speed of vehicles
in each lane with sliders or webcam hand tracking.

## Components

- `plate/`: stabilize extracted video frames and build a clean road background.
- `instrument/`: extract vehicle/train clips, pack them, and generate Figment patches.
- `instrument/figment/`: the Highway renderer and Hand Keys controller.
- `instrument/repair_library/`: repair and check the extracted clip library.
- `piano-keys/` and `piano-roll/`: related Figment keyboard and falling-bar experiments.

## What you need and how to run

For the prepared demo, you need **Figment** and the complete private
**Cars/output-figment** folder: its patches, manifests, background image and clip
assets must stay together. Open `highway.fgmt` for sliders or
`highway-hands.fgmt` for hand control; the latter also needs a **webcam** and camera
permission. No training is needed to play the prepared instrument.

To rebuild the assets, you need a **highway video**, extracted frames, **Python
3.11+**, **uv** and **FFmpeg**. Run scripts from `cars/` using `uv run`; standalone
scripts declare their Python dependencies. The road masks and lane coordinates
are specific to the workshop footage and need adjusting for another camera view.
See the script arguments and [repair guide](instrument/repair_library/README.md).

Footage and generated assets are excluded from Git. See [asset locations](../ASSETS.md).
