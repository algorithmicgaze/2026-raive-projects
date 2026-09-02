# AGENTS.md

Projects for the RAIVE 2026 summer school. One folder per project at the
root (`fruit-drama/`, `faces/`); `secrets/` groups the projects of the
Secrets team (`emo2vec/`, `mmwave-sensor/`). A project can carry its own
`CLAUDE.md` with its GPU machine and conventions. Commit from the repo root.

## No personal data in the repo

Participants are real people. This repo is public-facing work; they did not
sign up to be in it.

- No photos or video of a person, and no model output that shows a real
  person's likeness. Training samples, diary images, ONNX check strips and
  test clips from a face dataset all count.
- First names are fine. No full names, no e-mail addresses, no phone numbers,
  no other contact details of participants.
- Pose skeletons, face-mesh renders and landmark files without the photo are
  fine, and so are generated characters that are not a real person.
- Datasets, snapshots, model outputs and image diaries stay on the machine
  that made them. `datasets/`, `media/`, `output-*/`, `*.onnx` and the
  projects' `diary/` image folders are git-ignored; sync them with `rsync`.
  A text diary can be committed when its images stay out.

Before `git add`, check what a new file shows, not only what it is named.
Never `git add -A` in a folder that holds a dataset.

## Conventions

- Python through `uv run`; standalone scripts declare their dependencies
  with PEP 723 inline metadata.
- Models for Figment go out as ONNX with static shapes, fp32 input and
  output in [-1, 1], names `input` and `output`, opset 17.
