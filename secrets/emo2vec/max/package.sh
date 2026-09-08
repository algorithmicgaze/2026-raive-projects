#!/usr/bin/env bash
# Assembles the distributable Max package in ../emotion2vec-max and zips it.
#
# Signs the external with the Developer ID Application identity in the keychain
# (hardened runtime, timestamp). Set SIGN_IDENTITY to pick one, or SIGN_IDENTITY=-
# for an ad-hoc signature. With a .env (see setup-secrets.sh) the zip is
# notarized and the ticket stapled to the external.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

OUT=../emotion2vec-max
for f in "externals/emotion2vec~.mxo" models/emotion2vec.mlmodelc "help/emotion2vec~.maxhelp" package-info.json; do
  [[ -e "$f" ]] || { echo "missing $f (run ./build.sh first)" >&2; exit 1; }
done

rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT/externals" "$OUT/models" "$OUT/help"
cp -R "externals/emotion2vec~.mxo" "$OUT/externals/"
cp -R models/emotion2vec.mlmodelc "$OUT/models/"
cp "help/emotion2vec~.maxhelp" "$OUT/help/"
cp package-info.json "$OUT/"
cat > "$OUT/README.md" <<'EOF'
# emotion2vec~ for Max

Realtime speech emotion recognition. `emotion2vec~` runs emotion2vec+ base as a
Core ML model on the GPU (CPU fallback is automatic).

Requirements: Max 9, macOS 14 or later, Apple Silicon.

## Install

1. Copy this folder to `~/Documents/Max 9/Packages/emotion2vec`.
2. Restart Max and open `help/emotion2vec~.maxhelp`.

The external is signed with a Developer ID and notarized.

## Object

`emotion2vec~ @hop 0.25 @gate -45.`

- Inlet: signal at any sample rate.
- Outlets, left to right: probability list (angry disgusted fearful happy
  neutral other sad surprised unknown), top emotion, top probability, info
  messages (`db <level>`, `ms <inference time>`).
- `@hop`: seconds between inferences. `@gate`: dBFS below which a window is
  skipped. `@model`: path to another `.mlmodelc` (the bundled model uses a 3 s
  window).
EOF

EXTERN="$OUT/externals/emotion2vec~.mxo"
if [[ -z "${SIGN_IDENTITY:-}" ]]; then
  SIGN_IDENTITY=$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -1)
  SIGN_IDENTITY=${SIGN_IDENTITY:--}
fi
if [[ "$SIGN_IDENTITY" == "-" ]]; then
  codesign --force --sign - "$EXTERN"
  echo "signed ad hoc"
else
  codesign --force --options runtime --timestamp --sign "$SIGN_IDENTITY" "$EXTERN"
  echo "signed: $SIGN_IDENTITY"
fi
codesign --verify --strict "$EXTERN"

zip_package() {
  rm -f "$OUT.zip"
  ditto -c -k --keepParent "$OUT" "$OUT.zip"
}
zip_package

if [[ -n "${NOTARY_PASSWORD:-}" ]]; then
  xcrun notarytool submit "$OUT.zip" --apple-id "$NOTARY_APPLE_ID" --team-id "$NOTARY_TEAM_ID" \
    --password "$NOTARY_PASSWORD" --wait
  xcrun stapler staple "$EXTERN"
  zip_package
  echo "notarized and stapled"
fi

echo "$(du -sh "$OUT" | cut -f1) $OUT, $(du -sh "$OUT.zip" | cut -f1) $OUT.zip"
