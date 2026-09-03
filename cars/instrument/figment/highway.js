/**
 * @name Highway
 * @description Play a highway with a traffic density per lane.
 * @category image
 */

// Composites vehicle clips over a clean plate. Each lane input is the
// number of cars wanted in that lane. Cars enter under the bridge and
// roll down; a new one only starts when it can drive the whole way
// without touching another car in its lane. When a lane holds more cars
// than wanted, the farthest ones fade out. Clips: instrument/pack_clips.py.

node.timeDependent = true;
const manifestIn = node.fileIn('manifest', '', { fileType: 'generic' });
const plateIn = node.fileIn('plate', '', { fileType: 'image' });
// Lane inputs are a fill fraction: 0 is empty, 1 is a full lane, as many
// cars as fit nose to tail (measured per lane when the clips load).
const lane1In = node.numberIn('lane 1', 0.3, { min: 0, max: 1, step: 0.01 });
const lane2In = node.numberIn('lane 2', 0.3, { min: 0, max: 1, step: 0.01 });
const lane3In = node.numberIn('lane 3', 0.3, { min: 0, max: 1, step: 0.01 });
const lane4In = node.numberIn('lane 4', 0.3, { min: 0, max: 1, step: 0.01 });
const fadeIn = node.numberIn('fade frames', 20, { min: 1, max: 100, step: 1 });
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
const lastClip = [null, null, null, null];
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
  return { byLane, fps: manifest.fps || FPS, capacity: byLane.map(measureCapacity) };
}

// How many cars fit at once: pack the lane's clips nose to tail for 30 s.
function measureCapacity(lane) {
  if (!lane.length) return 0;
  let sim = [];
  let best = 0;
  for (let t = 0; t < 750; t++) {
    const clip = lane[t % lane.length];
    if (canSpawn(clip, t, gapIn.value, sim)) sim.push({ clip, t0: t });
    sim = sim.filter((c) => t - c.t0 < c.clip.n);
    best = Math.max(best, sim.length);
  }
  return Math.max(1, best);
}

function boxesTouch(a, b, m) {
  return !(a[0] + a[2] + m < b[0] || b[0] + b[2] + m < a[0] || a[1] + a[3] + m < b[1] || b[1] + b[3] + m < a[1]);
}

function boxAt(car, t) {
  const i = t - car.t0;
  return i >= 0 && i < car.clip.n ? car.clip.boxes[i] : null;
}

// No overlap with any car already in this lane, over the clip's whole life.
function canSpawn(clip, t0, margin, pool = cars) {
  for (let i = 0; i < clip.n; i++) {
    for (const c of pool) {
      if (c.clip.lane !== clip.lane) continue;
      const b = boxAt(c, t0 + i);
      if (b && boxesTouch(clip.boxes[i], b, margin)) return false;
    }
  }
  return true;
}

function bottom(c) {
  const b = boxAt(c, frame);
  return b ? b[1] + b[3] : 0;
}

function step(wanted) {
  for (let k = 0; k < 4; k++) {
    const lane = library.byLane[k];
    if (!lane.length) continue;
    const mine = cars.filter((c) => c.clip.lane - 1 === k && c.fade === undefined);
    if (mine.length < wanted[k]) {
      if (rng() < 0.35) {
        // a little jitter so cars do not enter in lock-step
        let clip = lane[Math.floor(rng() * lane.length)];
        if (lane.length > 1 && clip === lastClip[k]) clip = lane[(lane.indexOf(clip) + 1) % lane.length];
        if (canSpawn(clip, frame, gapIn.value)) {
          cars.push({ clip, t0: frame });
          lastClip[k] = clip;
        }
      }
    } else if (mine.length > wanted[k]) {
      // too many: the farthest car (highest on the road) fades out
      mine.sort((p, q) => bottom(p) - bottom(q));
      mine[0].fade = frame;
    }
  }
  const fade = fadeIn.value;
  cars = cars.filter((c) => frame - c.t0 < c.clip.n && (c.fade === undefined || frame - c.fade < fade));
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
    ctx.globalAlpha = c.fade === undefined ? 1 : Math.max(0, 1 - (frame - c.fade) / fadeIn.value);
    ctx.drawImage(c.clip.sheet, sx, sy, b[2], b[3], b[0], b[1], b[2], b[3]);
  }
  ctx.globalAlpha = 1;
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
  const wanted = [lane1In.value, lane2In.value, lane3In.value, lane4In.value].map((v, k) => Math.round(v * library.capacity[k]));

  // Real time in the editor, one step per frame when exporting.
  let steps = 1;
  if (window.desktop.getRuntimeMode() !== 'export') {
    const now = performance.now();
    steps = Math.min(4, Math.floor(((now - lastTime) / 1000) * FPS));
    if (steps > 0) lastTime = now;
  }
  for (let s = 0; s < steps; s++) {
    step(wanted);
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
