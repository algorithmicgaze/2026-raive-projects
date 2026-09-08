# Secrets — voice, breath and faces

Experiments that turn voice, breathing and facial movement into signals for
interactive performance. The face-image project lives separately in [faces/](../faces/).

## Components and requirements

- **[emo2vec/](emo2vec/README.md)**: speech-emotion probabilities in a browser or
  Max. Needs a **microphone or audio file** and trained model files. For the browser
  version, install **Bun**, copy `Secrets/emo2vec/models` from the private share into
  `emo2vec/models`, then run `bun install` and `bunx serve .` from `emo2vec/`.
  Open the local URL in Chrome. The ready-built Max package in the share needs
  **Max on Apple Silicon/macOS 14+**; its README explains installation.
- **`mmwave-sensor/`**: breathing-motion sensing over MQTT. Needs a **Seeed MR60BHA2
  mmWave sensor**, a compatible **Wi-Fi microcontroller**, Arduino tooling and the
  Seeed mmWave, Adafruit NeoPixel and MQTT libraries. Configure the board's serial
  wiring, Wi-Fi and your own Shiftr broker credentials in `breath_demo.ino`, then
  upload it. Open `mmwave-max/shiftr-mqtt.maxpat` in **Max with Node for Max** and
  configure the same broker. No video or trained model is needed.
- **`grain-recordings/`**: live granular resampling. Needs **Max**, a **microphone**
  and audio output. Keep all three patches together and open `granular.maxpat`.
  Enable audio and recording, capture some sound, then enable playback.
  `grain-voice.maxpat` supplies each grain and `rand-range.maxpat` randomizes controls.
  No prerecorded audio file or model is required.

Media, models and working credentials are excluded from Git. See
[private asset locations](../ASSETS.md); use your own inputs if you do not have share access.
