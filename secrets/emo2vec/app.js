import * as ort from "./node_modules/onnxruntime-web/dist/ort.webgpu.min.mjs";

const MODEL_URL = "./models/emotion2vec_plus_base.onnx";
const HEAD_URL = "./models/emotion2vec_head.json";
const SR = 16000;
const MAX_WINDOW_S = 5;
const HOP_MS = 250;
const HISTORY_S = 60;
const SILENCE_DB = -45;

// Stack order, bottom to top. Colors come from CSS custom properties --c-<key>.
const EMOTIONS = ["sad", "surprised", "neutral", "happy", "other", "disgusted", "fearful", "angry", "unknown"];

const $ = (id) => document.getElementById(id);
const ui = {
  status: $("status"),
  progress: $("progress"),
  startMic: $("start-mic"),
  file: $("file"),
  stop: $("stop"),
  sources: $("sources"),
  window: $("window"),
  ep: $("ep"),
  latency: $("latency"),
  level: $("level"),
  levelLabel: $("level-label"),
  hero: $("hero"),
  heroValue: $("hero-value"),
  bars: $("bars"),
  chart: $("chart"),
  tooltip: $("tooltip"),
};

// ---------- model ----------

let session = null;
let head = null; // { labels, weight: Float32Array(9*768), bias: Float32Array(9), order: index per EMOTIONS }

async function fetchWithProgress(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const total = Number(res.headers.get("content-length")) || 0;
  const reader = res.body.getReader();
  const chunks = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    onProgress(received, total);
  }
  const out = new Uint8Array(received);
  let pos = 0;
  for (const c of chunks) {
    out.set(c, pos);
    pos += c.length;
  }
  return out;
}

async function loadModel() {
  const headJson = await (await fetch(HEAD_URL)).json();
  head = {
    labels: headJson.labels,
    weight: Float32Array.from(headJson.weight.flat()),
    bias: Float32Array.from(headJson.bias),
    dim: headJson.weight[0].length,
    // EMOTIONS[i] -> row index in the head
    order: EMOTIONS.map((k) => headJson.labels.indexOf(k)),
  };

  setStatus("Downloading model…");
  const bytes = await fetchWithProgress(MODEL_URL, (n, total) => {
    const mb = (n / 1e6).toFixed(0);
    ui.progress.value = total ? n / total : 0;
    setStatus(`Downloading model… ${mb} MB${total ? ` / ${(total / 1e6).toFixed(0)} MB` : ""}`);
  });

  if (crossOriginIsolated) {
    ort.env.wasm.numThreads = Math.min(8, navigator.hardwareConcurrency || 4);
  }

  const providers = navigator.gpu ? ["webgpu", "wasm"] : ["wasm"];
  for (const ep of providers) {
    setStatus(`Creating ${ep} session…`);
    ui.progress.removeAttribute("value");
    try {
      session = await ort.InferenceSession.create(bytes, { executionProviders: [ep] });
      ui.ep.textContent = ep === "wasm" ? `wasm × ${ort.env.wasm.numThreads} threads` : ep;
      return;
    } catch (e) {
      console.warn(`${ep} session failed`, e);
    }
  }
  throw new Error("No execution provider could load the model");
}

function softmax(logits) {
  const m = Math.max(...logits);
  const e = logits.map((v) => Math.exp(v - m));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((v) => v / s);
}

// Mean-pool the frame features, apply the linear head, softmax. Returns probs in EMOTIONS order.
function classify(feats, frames, dim) {
  const pooled = new Float32Array(dim);
  for (let t = 0; t < frames; t++) {
    const off = t * dim;
    for (let d = 0; d < dim; d++) pooled[d] += feats[off + d];
  }
  for (let d = 0; d < dim; d++) pooled[d] /= frames;

  const logits = new Array(head.labels.length);
  for (let c = 0; c < logits.length; c++) {
    let acc = head.bias[c];
    const off = c * dim;
    for (let d = 0; d < dim; d++) acc += head.weight[off + d] * pooled[d];
    logits[c] = acc;
  }
  const probs = softmax(logits);
  return head.order.map((i) => probs[i]);
}

// ---------- audio ----------

const ring = {
  buf: new Float32Array(SR * MAX_WINDOW_S),
  pos: 0,
  total: 0,
  push(chunk) {
    for (let i = 0; i < chunk.length; i++) {
      this.buf[this.pos] = chunk[i];
      this.pos = (this.pos + 1) % this.buf.length;
    }
    this.total += chunk.length;
  },
  latest(n) {
    n = Math.min(n, this.total, this.buf.length);
    const out = new Float32Array(n);
    let start = (this.pos - n + this.buf.length) % this.buf.length;
    const first = Math.min(n, this.buf.length - start);
    out.set(this.buf.subarray(start, start + first), 0);
    if (first < n) out.set(this.buf.subarray(0, n - first), first);
    return out;
  },
  get seconds() {
    return this.total / SR;
  },
};

// Linear resampler that carries phase across chunks. Only used if the
// AudioContext could not be opened at 16 kHz.
function makeResampler(from, to) {
  const step = from / to;
  let last = 0;
  let phase = 0; // position in the incoming chunk, relative to index -1 (= last)
  return (chunk) => {
    const out = [];
    while (phase < chunk.length) {
      const i = Math.floor(phase);
      const frac = phase - i;
      const a = i < 0 ? last : chunk[i];
      const b = chunk[i + 1] ?? chunk[chunk.length - 1];
      out.push(a + (b - a) * frac);
      phase += step;
    }
    phase -= chunk.length;
    last = chunk[chunk.length - 1];
    return Float32Array.from(out);
  };
}

let audio = null; // { ctx, stop }
let running = false;
let currentDb = -Infinity;

function dbOf(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return 10 * Math.log10(sum / samples.length + 1e-12);
}

// AudioContext + capture worklet. Sources connect to the returned node.
async function openAudio() {
  const ctx = new AudioContext({ sampleRate: SR });
  await ctx.audioWorklet.addModule("./pcm-worklet.js");
  const capture = new AudioWorkletNode(ctx, "pcm-capture");
  const resample = ctx.sampleRate === SR ? null : makeResampler(ctx.sampleRate, SR);
  capture.port.onmessage = (e) => {
    const chunk = resample ? resample(e.data) : e.data;
    ring.push(chunk);
    currentDb = dbOf(chunk);
  };
  return { ctx, capture };
}

async function startMic() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
  });
  const { ctx, capture } = await openAudio();
  ctx.createMediaStreamSource(stream).connect(capture);
  audio = { ctx, stop: () => stream.getTracks().forEach((t) => t.stop()) };
  return `Live mic · ${ctx.sampleRate} Hz`;
}

// Plays the file through the speakers and through the analysis pipeline.
async function startFile(file) {
  const { ctx, capture } = await openAudio();
  const buffer = await ctx.decodeAudioData(await file.arrayBuffer());
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.connect(capture);
  src.connect(ctx.destination);
  src.onended = () => {
    if (audio && audio.src === src) stopAll(`Finished ${file.name}`);
  };
  src.start();
  audio = { ctx, src, stop: () => src.stop() };
  return `Playing ${file.name} · ${buffer.duration.toFixed(1)} s`;
}

function stopAll(statusText) {
  running = false;
  if (audio) {
    audio.stop();
    audio.ctx.close();
    audio = null;
  }
  currentDb = -Infinity;
  ui.sources.hidden = false;
  ui.stop.hidden = true;
  setStatus(statusText);
}

// ---------- analysis loop ----------

const history = []; // { t, probs|null, db }

async function analyzeLoop() {
  while (running) {
    const t0 = performance.now();
    const windowSamples = Number(ui.window.value) * SR;
    let probs = null;
    let db = -Infinity;
    const wave = ring.seconds >= 1 ? ring.latest(windowSamples) : null;

    if (wave) db = dbOf(wave);
    if (db > SILENCE_DB) {
      const input = new ort.Tensor("float32", wave, [1, wave.length]);
      const out = await session.run({ input });
      const feats = out.output;
      probs = classify(feats.data, feats.dims[1], feats.dims[2]);
      ui.latency.textContent = `${(performance.now() - t0).toFixed(0)} ms`;
    }

    history.push({ t: ring.seconds, probs, db });
    while (history.length && history[0].t < ring.seconds - HISTORY_S - 1) history.shift();

    const wait = HOP_MS - (performance.now() - t0);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  }
}

// ---------- ui ----------

function setStatus(text) {
  ui.status.textContent = text;
}

function colorOf(key) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--c-${key}`).trim();
}

function buildBars() {
  ui.bars.innerHTML = "";
  for (const key of [...EMOTIONS].reverse()) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<span class="swatch" style="background:var(--c-${key})"></span><span class="name">${key}</span><span class="track"><span class="fill" style="background:var(--c-${key})"></span></span><span class="value">–</span>`;
    row.dataset.key = key;
    ui.bars.appendChild(row);
  }
}

function updatePanel() {
  const latest = history[history.length - 1];
  const probs = latest && latest.probs;
  const rows = ui.bars.querySelectorAll(".row");
  for (const row of rows) {
    const i = EMOTIONS.indexOf(row.dataset.key);
    const p = probs ? probs[i] : 0;
    row.querySelector(".fill").style.width = `${(p * 100).toFixed(1)}%`;
    row.querySelector(".value").textContent = probs ? `${(p * 100).toFixed(0)}%` : "–";
  }
  if (probs) {
    let best = 0;
    for (let i = 1; i < probs.length; i++) if (probs[i] > probs[best]) best = i;
    ui.hero.textContent = EMOTIONS[best];
    ui.hero.style.color = `var(--c-${EMOTIONS[best]})`;
    ui.heroValue.textContent = `${(probs[best] * 100).toFixed(0)}%`;
  } else if (running) {
    ui.hero.textContent = "listening";
    ui.hero.style.color = "";
    ui.heroValue.textContent = ring.seconds < 1 ? "buffering" : "silence";
  }

  const db = Number.isFinite(currentDb) ? currentDb : -90;
  ui.level.style.width = `${Math.max(0, Math.min(100, ((db + 60) / 60) * 100))}%`;
  ui.level.classList.toggle("open", db > SILENCE_DB);
  ui.levelLabel.textContent = running ? `${db.toFixed(0)} dB` : "";
}

// Stacked area over the last HISTORY_S seconds. Silence leaves a gap.
function drawChart() {
  const canvas = ui.chart;
  const dpr = devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const css = getComputedStyle(document.documentElement);
  const surface = css.getPropertyValue("--surface").trim();
  const grid = css.getPropertyValue("--grid").trim();
  const ink = css.getPropertyValue("--ink-muted").trim();

  ctx.fillStyle = surface;
  ctx.fillRect(0, 0, w, h);

  const pad = { l: 36, r: 12, t: 8, b: 22 };
  const pw = w - pad.l - pad.r;
  const ph = h - pad.t - pad.b;
  const now = ring.seconds;
  const x = (t) => pad.l + ((t - (now - HISTORY_S)) / HISTORY_S) * pw;
  const y = (v) => pad.t + (1 - v) * ph;

  // grid
  ctx.strokeStyle = grid;
  ctx.lineWidth = 1;
  ctx.fillStyle = ink;
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    ctx.beginPath();
    ctx.moveTo(pad.l, y(v));
    ctx.lineTo(w - pad.r, y(v));
    ctx.stroke();
    ctx.fillText(`${v * 100}%`, pad.l - 6, y(v));
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let s = 0; s <= HISTORY_S; s += 10) {
    const t = now - s;
    ctx.fillText(s === 0 ? "now" : `−${s}s`, x(t), h - pad.b + 6);
  }

  // contiguous runs of voiced samples
  const hopS = HOP_MS / 1000;
  const runs = [];
  let run = [];
  for (const s of history) {
    if (s.probs && (run.length === 0 || s.t - run[run.length - 1].t < 3 * hopS)) run.push(s);
    else {
      if (run.length) runs.push(run);
      run = s.probs ? [s] : [];
    }
  }
  if (run.length) runs.push(run);

  ctx.save();
  ctx.beginPath();
  ctx.rect(pad.l, pad.t, pw, ph);
  ctx.clip();
  for (const r of runs) {
    // single samples get a hop-wide slab so they stay visible
    const pts = r.length === 1 ? [{ ...r[0], t: r[0].t - hopS }, r[0]] : r;
    const bottom = new Float32Array(pts.length);
    for (let i = 0; i < EMOTIONS.length; i++) {
      ctx.beginPath();
      for (let k = 0; k < pts.length; k++) ctx.lineTo(x(pts[k].t), y(bottom[k] + pts[k].probs[i]));
      for (let k = pts.length - 1; k >= 0; k--) ctx.lineTo(x(pts[k].t), y(bottom[k]));
      ctx.closePath();
      ctx.fillStyle = colorOf(EMOTIONS[i]);
      ctx.fill();
      // 2px surface gap between stacked bands
      ctx.beginPath();
      for (let k = 0; k < pts.length; k++) ctx.lineTo(x(pts[k].t), y(bottom[k] + pts[k].probs[i]));
      ctx.strokeStyle = surface;
      ctx.lineWidth = 2;
      ctx.stroke();
      for (let k = 0; k < pts.length; k++) bottom[k] += pts[k].probs[i];
    }
  }

  // hover crosshair
  if (hover !== null) {
    const s = nearestSample(hover);
    if (s) {
      ctx.strokeStyle = ink;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x(s.t), pad.t);
      ctx.lineTo(x(s.t), pad.t + ph);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  ctx.restore();

  chartGeom = { pad, pw, now };
}

let hover = null; // time under the cursor, in ring seconds
let chartGeom = null;

function nearestSample(t) {
  let best = null;
  for (const s of history) {
    if (!s.probs) continue;
    if (!best || Math.abs(s.t - t) < Math.abs(best.t - t)) best = s;
  }
  return best && Math.abs(best.t - t) < 1 ? best : null;
}

ui.chart.addEventListener("mousemove", (e) => {
  if (!chartGeom) return;
  const rect = ui.chart.getBoundingClientRect();
  const px = e.clientX - rect.left;
  hover = chartGeom.now - HISTORY_S + ((px - chartGeom.pad.l) / chartGeom.pw) * HISTORY_S;
  const s = nearestSample(hover);
  if (!s) {
    ui.tooltip.hidden = true;
    return;
  }
  const lines = EMOTIONS.map((k, i) => ({ k, p: s.probs[i] }))
    .sort((a, b) => b.p - a.p)
    .slice(0, 4)
    .map(({ k, p }) => `<div><span class="swatch" style="background:var(--c-${k})"></span>${k} <b>${(p * 100).toFixed(0)}%</b></div>`);
  ui.tooltip.innerHTML = `<div class="muted">−${(chartGeom.now - s.t).toFixed(1)}s</div>${lines.join("")}`;
  ui.tooltip.hidden = false;
  const left = Math.min(px + 14, rect.width - ui.tooltip.offsetWidth - 4);
  ui.tooltip.style.left = `${left}px`;
  ui.tooltip.style.top = `${e.clientY - rect.top + 14}px`;
});
ui.chart.addEventListener("mouseleave", () => {
  hover = null;
  ui.tooltip.hidden = true;
});

function frame() {
  drawChart();
  updatePanel();
  requestAnimationFrame(frame);
}

// ---------- wiring ----------

async function startWith(startSource) {
  let statusText;
  try {
    statusText = await startSource();
  } catch (e) {
    stopAll(`Audio error: ${e.message}`);
    return;
  }
  running = true;
  ui.sources.hidden = true;
  ui.stop.hidden = false;
  setStatus(statusText);
  analyzeLoop().catch((e) => {
    stopAll(`Inference error: ${e.message}`);
    console.error(e);
  });
}

ui.startMic.addEventListener("click", () => startWith(startMic));
ui.file.addEventListener("change", () => {
  const file = ui.file.files[0];
  ui.file.value = "";
  if (file) startWith(() => startFile(file));
});
ui.stop.addEventListener("click", () => stopAll("Stopped"));

buildBars();
requestAnimationFrame(frame);

loadModel()
  .then(() => {
    ui.progress.hidden = true;
    ui.sources.hidden = false;
    setStatus("Model ready");
  })
  .catch((e) => {
    ui.progress.hidden = true;
    setStatus(`Model load failed: ${e.message}`);
    console.error(e);
  });
