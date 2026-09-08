# Repository conventions

This is public-facing source from RAIVE 2026. Private assets are shared separately
through OneDrive; see ASSETS.md for group mapping and setup.

- No photos, movies, audio recordings, model weights, datasets, generated likenesses,
  notebook outputs or embedded media in the repository.
- No participant surnames, contact details, personal machine addresses or credentials.
  First names and required third-party license attribution are allowed.
- Keep service settings as placeholders; never commit `.env` files.
- Run `python3 tools/check_public_tree.py` and inspect changes before committing.
- Python uses `uv run`; standalone scripts use PEP 723 dependency metadata.
- Figment ONNX exports use static shapes, fp32 input/output in [-1, 1], input/output
  names `input` and `output`, and opset 17. Weights may use fp16.
