/**
 * @name Highway
 * @description Play a highway with a traffic density per lane.
 * @category image
 */

// Composites vehicle clips over a clean plate. Each lane has a density
// slider: at 0 the lane is empty, at 1 it is as full as the clips allow
// without touching. The video always runs; the sliders only change how
// often a new car enters a lane. Clips come from instrument/pack_clips.py.

node.timeDependent = true;
const manifestIn = node.fileIn('manifest', '', { fileType: 'generic' });
const plateIn = node.fileIn('plate', '', { fileType: 'image' });
const lane1In = node.numberIn('lane 1', 0.3, { min: 0, max: 1, step: 0.01 });
const lane2In = node.numberIn('lane 2', 0.3, { min: 0, max: 1, step: 0.01 });
const lane3In = node.numberIn('lane 3', 0.3, { min: 0, max: 1, step: 0.01 });
const lane4In = node.numberIn('lane 4', 0.3, { min: 0, max: 1, step: 0.01 });
const maxRateIn = node.numberIn('max rate', 1.2, { min: 0.1, max: 5, step: 0.1 });
const gapIn = node.numberIn('gap', 24, { min: 0, max: 200, step: 1 });
const seedIn = node.numberIn('seed', 1, { min: 1, max: 9999, step: 1 });
const imageOut = node.imageOut('out');

const FPS = 25;
let target, canvas, ctx;
let library = null; // { byLane: [[clip]] }
let loadedManifest = '';
let plate = null;
let loadedPlate = '';
let cars = [];
let frame = 0;
let lastTime = 0;
let rng;

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

node.onStart = () => {
  target = new figment.RenderTarget({ label: 'highway' });
  cars = [];
  frame = 0;
  lastTime = performance.now();
  rng = mulberry32(seedIn.value);
  library = null;
  loadedManifest = '';
  plate = null;
  loadedPlate = '';
};

async function loadBitmap(path) {
  const blob = await (await fetch(figment.urlForAsset(path).toString())).blob();
  return createImageBitmap(blob);
}

async function loadLibrary(path) {
  const base = figment.urlForAsset(path).toString();
  const dir = base.slice(0, base.lastIndexOf('/') + 1);
  const manifest = await (await fetch(base)).json();
  const byLane = [[], [], [], []];
  for (const c of manifest.clips) {
    const blob = await (await fetch(dir + c.sheet)).blob();
    const sheet = await createImageBitmap(blob);
    byLane[c.lane - 1].push({ ...c, sheet, n: c.boxes.length });
  }
  return { byLane, fps: manifest.fps || FPS };
}

function boxesTouch(a, b, m) {
  return !(a[0] + a[2] + m < b[0] || b[0] + b[2] + m < a[0] || a[1] + a[3] + m < b[1] || b[1] + b[3] + m < a[1]);
}

function boxAt(car, t) {
  const i = t - car.t0;
  return i >= 0 && i < car.clip.n ? car.clip.boxes[i] : null;
}

// No overlap with any car already in this lane, over the clip's whole life.
function canSpawn(clip, t0, margin) {
  for (let i = 0; i < clip.n; i++) {
    for (const c of cars) {
      if (c.clip.lane !== clip.lane) continue;
      const b = boxAt(c, t0 + i);
      if (b && boxesTouch(clip.boxes[i], b, margin)) return false;
    }
  }
  return true;
}

function step(densities) {
  for (let k = 0; k < 4; k++) {
    const lane = library.byLane[k];
    if (!lane.length) continue;
    if (rng() < (densities[k] * maxRateIn.value) / FPS) {
      const clip = lane[Math.floor(rng() * lane.length)];
      if (canSpawn(clip, frame, gapIn.value)) cars.push({ clip, t0: frame });
    }
  }
  cars = cars.filter((c) => frame - c.t0 < c.clip.n);
}

function draw(plate) {
  ctx.drawImage(plate, 0, 0);
  const active = cars.map((c) => ({ c, b: boxAt(c, frame) })).filter((x) => x.b);
  active.sort((p, q) => p.b[1] + p.b[3] - (q.b[1] + q.b[3])); // far cars first
  for (const { c, b } of active) {
    const i = frame - c.t0;
    const [cw, ch] = c.clip.cell;
    const sx = (i % c.clip.cols) * cw;
    const sy = Math.floor(i / c.clip.cols) * ch;
    ctx.drawImage(c.clip.sheet, sx, sy, b[2], b[3], b[0], b[1], b[2], b[3]);
  }
}

node.onRender = async () => {
  if (!plateIn.value || !manifestIn.value) return;
  if (loadedPlate !== plateIn.value) {
    loadedPlate = plateIn.value;
    plate = await loadBitmap(plateIn.value);
  }
  if (loadedManifest !== manifestIn.value) {
    loadedManifest = manifestIn.value;
    library = null;
    library = await loadLibrary(manifestIn.value);
    cars = [];
  }
  if (!library || !plate) return;
  if (!canvas || canvas.width !== plate.width || canvas.height !== plate.height) {
    canvas = new OffscreenCanvas(plate.width, plate.height);
    ctx = canvas.getContext('2d');
    target.setSize(plate.width, plate.height);
  }
  const densities = [lane1In.value, lane2In.value, lane3In.value, lane4In.value];

  // Real time in the editor, one step per frame when exporting.
  let steps = 1;
  if (window.desktop.getRuntimeMode() !== 'export') {
    const now = performance.now();
    steps = Math.min(4, Math.floor(((now - lastTime) / 1000) * FPS));
    if (steps > 0) lastTime = now;
  }
  for (let s = 0; s < steps; s++) {
    step(densities);
    frame++;
  }
  draw(plate);
  target.uploadExternal(canvas);
  imageOut.set(target);
};

node.onStop = () => {
  target?.destroy();
  if (library) for (const lane of library.byLane) for (const c of lane) c.sheet.close();
};
