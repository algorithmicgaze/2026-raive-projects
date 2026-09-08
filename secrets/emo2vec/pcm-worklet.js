// Collects microphone samples into fixed-size chunks and posts them to the main thread.
class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Float32Array(2048);
    this.n = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.chunk[this.n++] = ch[i];
      if (this.n === this.chunk.length) {
        this.port.postMessage(this.chunk, [this.chunk.buffer]);
        this.chunk = new Float32Array(2048);
        this.n = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PCMCapture);
