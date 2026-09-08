# Figment — webcam detection starter

A small patch for exploring body, hand and face tracking together. It draws and
combines the detected landmarks so they can become inputs to other visual projects.

## Components

- `detect-everything.fgmt`: Webcam Image, Detect Pose, Detect Hands, Detect Faces,
  image compositing and an output node.

## What you need and how to run

You need **Figment** with these detection nodes and a **webcam**. Open
`detect-everything.fgmt`, allow camera access and inspect the detector/output nodes.
Select your camera if it is not picked up automatically. Keep the relevant body
parts visible in the frame.

This patch uses Figment's detector models; **no workshop-trained ONNX file,
private dataset or prerecorded video is required**. Detector assets must be
available to your Figment installation. Adjust the detection and smoothing settings
in the nodes, then reuse their outputs in your own patches.
