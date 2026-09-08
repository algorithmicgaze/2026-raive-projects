# Repository tools

Small maintenance utilities for keeping the public repository free of private
assets and common accidental disclosures.

## Components

- `check_public_tree.py`: checks for media/model files, local credential files,
  common secret patterns, personal paths, embedded media and saved notebook outputs.
  It also checks that JSON-based project files parse.

## Run

You need **Python 3.9+**; the checker uses only the standard library. From the
repository root, run:

```sh
python3 tools/check_public_tree.py
```

No video, webcam, model, account or dataset is needed. A successful check exits
with status zero. Review changes manually as well: the checker cannot identify
every personal detail in source text. It reports issues without printing matched
secret values and does not edit files.
