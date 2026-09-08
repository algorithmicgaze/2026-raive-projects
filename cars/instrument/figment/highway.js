/**
 * @name Highway
 * @description Play a highway: cars per lane, tempo per lane, and a train.
 * @category image
 */

// Composites vehicle clips over a clean plate. Five lanes: lane 0 is the
// train, lanes 1 to 4 are cars. Every lane has a quantity and a tempo,
// and every one of these ports can be driven from another node.
//
//   lane 1..4   0..1  how full the lane is (fraction of what fits)
//   tempo 1..4  -10..10 speed of the cars; negative drives them backwards
//   lane 0      0..1  train length: 0 none, small = one carriage, 1 = endless
//   train tempo 0..10 speed of the train (video cannot run backwards)
//   tempo       -10..10 global: multiplies every lane's tempo
//
// Modes: 'count' (default) keeps the lane at its quantity with quick fades,
// cars entering at the bridge when they fit and further down the road
// otherwise. 'piano roll' treats the quantity as a held note: cars stream
// in at the bridge while it is held and roll out when released.

node.timeDependent = true;
const manifestIn = node.fileIn('manifest', '', { fileType: 'generic' });
const trainsIn = node.fileIn('trains', '', { fileType: 'generic' });
const plateIn = node.fileIn('plate', '', { fileType: 'image' });
const laneIns = [
  node.numberIn('lane 0', 0.5, { min: 0, max: 1, step: 0.01 }),
  node.numberIn('lane 1', 0.5, { min: 0, max: 1, step: 0.01 }),
  node.numberIn('lane 2', 0.4, { min: 0, max: 1, step: 0.01 }),
  node.numberIn('lane 3', 0.4, { min: 0, max: 1, step: 0.01 }),
  node.numberIn('lane 4', 0.4, { min: 0, max: 1, step: 0.01 }),
];
const tempoIns = [
  node.numberIn('train tempo', 1, { min: 0, max: 10, step: 0.1 }),
  node.numberIn('tempo 1', 1, { min: -10, max: 10, step: 0.1 }),
  node.numberIn('tempo 2', 1, { min: -10, max: 10, step: 0.1 }),
  node.numberIn('tempo 3', 1, { min: -10, max: 10, step: 0.1 }),
  node.numberIn('tempo 4', 1, { min: -10, max: 10, step: 0.1 }),
];
// global tempo multiplies every lane's tempo, train included
const globalTempoIn = node.numberIn('tempo', 1, { min: -10, max: 10, step: 0.1 });
// quantity and tempo ports show as plugs too, so other nodes can drive them
for (const p of [...laneIns, ...tempoIns, globalTempoIn]) p.display = 0x03;
const modeIn = node.selectIn('mode', ['count', 'piano roll'], 'count');
const fadeIn = node.numberIn('fade frames', 6, { min: 1, max: 100, step: 1 });
const gapIn = node.numberIn('gap', 24, { min: 0, max: 200, step: 1 });
const sparseGapIn = node.numberIn('sparse gap', 300, { min: 0, max: 800, step: 10 });
const maxLoopsIn = node.numberIn('train max loops', 8, { min: 1, max: 40, step: 1 });
const trainGapIn = node.numberIn('train gap', 0, { min: 0, max: 10, step: 0.1 }); // seconds between trains
const borrowIn = node.toggleIn('borrow', true);
// Soft lane masks: a vehicle is clipped to its own lane, widened by this
// fraction of the lane width on each side and feathered, so nothing spills
// into the neighbouring lane. 0 turns the masks off.
const laneMaskIn = node.numberIn('lane mask widen', 0.35, { min: 0, max: 1, step: 0.05 });
const laneFeatherIn = node.numberIn('lane mask feather', 18, { min: 0, max: 80, step: 1 });
const seedIn = node.numberIn('seed', 1, { min: 1, max: 9999, step: 1 });
const imageOut = node.imageOut('out');

const FPS = 25;
const MIN_OWN = 8;
// lane boundaries in plate coordinates: x at the bottom row and at the bridge
const YB = 1080,
  YT = 430;
const BOUNDS = [
  [615, 884],
  [942, 950],
  [1285, 1005],
  [1622, 1060],
  [1960, 1115],
];
const boundX = (i, y, s) => (BOUNDS[i][1] + ((y / s - YT) / (YB - YT)) * (BOUNDS[i][0] - BOUNDS[i][1])) * s;
const laneCenter = (k, y, s) => 0.5 * (boundX(k, y, s) + boundX(k + 1, y, s));

let target, canvas, ctx;
let laneMasks = null; // [canvas per lane] at plate size
let laneMaskKey = '';
let scratch = null; // canvas for masking one sprite

function buildLaneMasks(w, h, scale, widen, feather) {
  const masks = [];
  for (let k = 0; k < 4; k++) {
    const c = new OffscreenCanvas(w, h);
    const g = c.getContext('2d');
    const pts = [];
    // lane polygon from the bridge to the bottom, widened, and pulled up
    // above the bridge line so tall vehicles keep their tops
    for (const y of [-h, YT * scale, YB * scale]) {
      const yy = Math.max(y, YT * scale);
      const lw = boundX(k + 1, yy, scale) - boundX(k, yy, scale);
      pts.push([boundX(k, yy, scale) - widen * lw, y], [boundX(k + 1, yy, scale) + widen * lw, y]);
    }
    g.filter = feather > 0 ? `blur(${feather * scale}px)` : 'none';
    g.fillStyle = '#fff';
    g.beginPath();
    g.moveTo(pts[0][0], pts[0][1]);
    g.lineTo(pts[1][0], pts[1][1]);
    g.lineTo(pts[3][0], pts[3][1]);
    g.lineTo(pts[5][0], pts[5][1]);
    g.lineTo(pts[4][0], pts[4][1]);
    g.lineTo(pts[2][0], pts[2][1]);
    g.closePath();
    g.fill();
    masks.push(c);
  }
  return masks;
}

// Draw one sprite clipped to its lane's soft mask.
function drawMasked(sheet, sx, sy, b, k, alpha) {
  const [x, y, w, h] = b;
  if (!scratch) scratch = new OffscreenCanvas(w, h);
  if (scratch.width < w || scratch.height < h) {
    scratch.width = Math.max(scratch.width, w);
    scratch.height = Math.max(scratch.height, h);
  }
  const g = scratch.getContext('2d');
  g.globalCompositeOperation = 'source-over';
  g.clearRect(0, 0, w, h);
  g.drawImage(sheet, sx, sy, w, h, 0, 0, w, h);
  g.globalCompositeOperation = 'destination-in';
  g.drawImage(laneMasks[k], x, y, w, h, 0, 0, w, h);
  ctx.globalAlpha = alpha;
  ctx.drawImage(scratch, 0, 0, w, h, x, y, w, h);
}

// Repaired atlases store a few complete views. Motion comes exclusively
// from the source track, including fractional positions and perspective size.
function repairedBox(clip, pos) {
  const i = Math.max(0, Math.min(clip.n - 1, pos));
  const lo = Math.floor(i), hi = Math.min(lo + 1, clip.n - 1), t = i - lo;
  return clip.boxes[lo].map((v, k) => v + (clip.boxes[hi][k] - v) * t);
}

function drawRepaired(clip, pos, b, alpha) {
  const [x, y, w, h] = b;
  if (!(w > 0 && h > 0)) return;
  const rw = Math.ceil(w), rh = Math.ceil(h);
  if (!scratch) scratch = new OffscreenCanvas(rw, rh);
  if (scratch.width < rw || scratch.height < rh) {
    scratch.width = Math.max(scratch.width, rw);
    scratch.height = Math.max(scratch.height, rh);
  }
  const g = scratch.getContext('2d');
  g.globalAlpha = 1;
  g.globalCompositeOperation = 'source-over';
  g.clearRect(0, 0, scratch.width, scratch.height);
  const poses = clip.poses;
  let hi = poses.findIndex((p) => p.frame >= pos);
  if (hi < 0) hi = poses.length - 1;
  const lo = Math.max(0, hi - 1), a = poses[lo], z = poses[hi];
  const t = lo === hi ? 0 : Math.max(0, Math.min(1, (pos - a.frame) / (z.frame - a.frame)));
  // Add weighted premultiplied colors and alpha; source-over would make
  // opaque bodywork translucent in the middle of each transition.
  g.globalCompositeOperation = 'lighter';
  g.globalAlpha = 1 - t;
  g.drawImage(clip.sheet, a.x, a.y, a.w, a.h, 0, 0, w, h);
  if (t > 0) {
    g.globalAlpha = t;
    g.drawImage(clip.sheet, z.x, z.y, z.w, z.h, 0, 0, w, h);
  }
  g.globalAlpha = 1;
  if (laneMasks) {
    g.globalCompositeOperation = 'destination-in';
    g.drawImage(laneMasks[clip.lane - 1], x, y, w, h, 0, 0, w, h);
  }
  ctx.save();
  // The bridge is foreground. Reconstructed roofs must emerge beneath it.
  ctx.beginPath();
  ctx.rect(0, 418, ctx.canvas.width, ctx.canvas.height - 418);
  ctx.clip();
  ctx.globalAlpha = alpha;
  ctx.drawImage(scratch, 0, 0, w, h, x, y, w, h);
  ctx.restore();
}
let library = null; // { own, byLane, capacity, borrow }
let loadedManifest = '';
let plate = null;
let loadedPlate = '';
let cars = [];
const lastClip = [null, null, null, null];
let trains = null; // { list: [{video, x, y, w, h, loop_in, loop_out}], mask, canvas }
let loadedTrains = '';
let train = null;
let trainNextAt = 0;
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
  train = null;
  frame = 0;
  lastTime = performance.now();
  rng = mulberry32(seedIn.value);
  library = null;
  loadedManifest = '';
  plate = null;
  loadedPlate = '';
  trains = null;
  loadedTrains = '';
};

// ─── loading ────────────────────────────────────────────────────────────────

async function loadBitmap(path) {
  const blob = await (await fetch(figment.urlForAsset(path).toString())).blob();
  return createImageBitmap(blob);
}

async function loadLibrary(path) {
  const base = figment.urlForAsset(path).toString();
  const dir = base.slice(0, base.lastIndexOf('/') + 1);
  const manifest = await (await fetch(base)).json();
  const own = [[], [], [], []];
  for (const c of manifest.clips) {
    const blob = await (await fetch(dir + c.sheet)).blob();
    const sheet = await createImageBitmap(blob);
    own[c.lane - 1].push({ ...c, sheet, n: c.boxes.length });
  }
  return { own, byLane: [], capacity: [], borrow: null };
}

// A clip moved into lane k: same rows, x shifted to that lane's centre.
function shifted(clip, k, s) {
  const boxes = clip.boxes.map((b) => {
    const yb = b[1] + b[3];
    const dx = laneCenter(k, yb, s) - laneCenter(clip.lane - 1, yb, s);
    return [clip.poses ? b[0] + dx : Math.round(b[0] + dx), b[1], b[2], b[3]];
  });
  return { ...clip, boxes, lane: k + 1, borrowed: true };
}

function assignLanes(lib, borrow, scale) {
  lib.byLane = lib.own.map((lane, k) => {
    const out = lane.slice();
    if (borrow && lane.length < MIN_OWN) {
      for (let j = 0; j < 4; j++) if (j !== k) for (const c of lib.own[j]) out.push(shifted(c, k, scale));
    }
    return out;
  });
  lib.capacity = lib.byLane.map(measureCapacity);
  lib.borrow = borrow;
}

async function loadTrains(path) {
  const base = figment.urlForAsset(path).toString();
  const dir = base.slice(0, base.lastIndexOf('/') + 1);
  const list = await (await fetch(base)).json();
  const mask = await createImageBitmap(await (await fetch(dir + 'mask.png')).blob());
  const out = [];
  for (const t of list) {
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.preload = 'auto';
    video.src = dir + t.file;
    await new Promise((r) => {
      video.onloadeddata = r;
      video.onerror = r;
    });
    out.push({ ...t, video });
  }
  return { list: out, mask, canvas: null };
}

// ─── cars ───────────────────────────────────────────────────────────────────
// A car has a fractional playhead `pos` into its clip. Each step it moves by
// the lane's tempo; negative tempo drives it backwards up the road.

function frameOf(car, pos = car.pos) {
  const i = Math.round(pos);
  return i >= 0 && i < car.clip.n ? i : -1;
}

// Boxes hold shadow and padding too, so cars may sit closer than the boxes: test their cores.
function core(b) {
  return [b[0] + 0.2 * b[2], b[1] + 0.2 * b[3], 0.6 * b[2], 0.6 * b[3]];
}

function boxesTouch(p, q, m) {
  const a = core(p);
  const b = core(q);
  return !(a[0] + a[2] + m < b[0] || b[0] + b[2] + m < a[0] || a[1] + a[3] + m < b[1] || b[1] + b[3] + m < a[1]);
}

// Would a car starting at `start` in `clip`, moving at `tempo`, touch any car
// of the pool in the same lane during the rest of its run? The pool moves at
// the same tempo, so relative timing holds.
function canSpawn(clip, start, tempo, margin, pool = cars) {
  const others = pool.filter((c) => c.clip.lane === clip.lane);
  if (!others.length) return true;
  const step = Math.abs(tempo) < 0.05 ? 1 : tempo;
  for (let s = 0; s < 2000; s++) {
    const i = Math.round(start + s * step);
    if (i < 0 || i >= clip.n) break;
    for (const c of others) {
      const j = Math.round(c.pos + s * step);
      if (j < 0 || j >= c.clip.n) continue;
      if (boxesTouch(clip.boxes[i], c.clip.boxes[j], margin)) return false;
    }
  }
  return true;
}

// Where to start: at the entrance (the bridge, or the bottom edge when
// driving backwards) if it fits, otherwise somewhere along the road.
function findStart(clip, tempo, margin, pool, midRoad) {
  const entrance = tempo < 0 ? clip.n - 1 : 0;
  if (canSpawn(clip, entrance, tempo, margin, pool)) return entrance;
  if (!midRoad) return -1;
  for (let tries = 0; tries < 12; tries++) {
    const j = 10 + Math.floor(rng() * Math.max(1, clip.n - 50));
    if (canSpawn(clip, j, tempo, margin, pool)) return j;
  }
  return -1;
}

// How many cars fit at once: pack the lane for 30 s, mid-road entries allowed.
function measureCapacity(lane) {
  if (!lane.length) return 0;
  let sim = [];
  let best = 0;
  for (let t = 0; t < 750; t++) {
    const clip = lane[t % lane.length];
    const j = findStart(clip, 1, gapIn.value, sim, true);
    if (j >= 0) sim.push({ clip, pos: j });
    for (const c of sim) c.pos += 1;
    sim = sim.filter((c) => c.pos < c.clip.n);
    best = Math.max(best, sim.reduce((n, c) => n + (c.clip.cars || 1), 0));
  }
  return Math.max(1, best);
}

function pick(lane, k, level) {
  // a strong value prefers the big vehicles when the lane has them
  const big = lane.filter((c) => (c.cars || 1) > 1);
  let clip = level > 0.7 && big.length && rng() < 0.5 ? big[Math.floor(rng() * big.length)] : lane[Math.floor(rng() * lane.length)];
  if (lane.length > 1 && clip === lastClip[k]) clip = lane[(lane.indexOf(clip) + 1) % lane.length];
  return clip;
}

function bottom(c) {
  const i = frameOf(c);
  return i < 0 ? 0 : c.clip.boxes[i][1] + c.clip.boxes[i][3];
}

function advance(tempos) {
  const fade = fadeIn.value;
  for (const c of cars) c.pos += tempos[c.clip.lane - 1];
  cars = cars.filter((c) => c.pos >= 0 && c.pos < c.clip.n && (c.fade === undefined || frame - c.fade < fade));
}

// count mode: keep every lane at its quantity
function stepCount(levels, tempos) {
  for (let k = 0; k < 4; k++) {
    const lane = library.byLane[k];
    if (!lane.length) continue;
    const wanted = Math.round(levels[k] * library.capacity[k]);
    const mine = cars.filter((c) => c.clip.lane - 1 === k && c.fade === undefined);
    const have = mine.reduce((n, c) => n + (c.clip.cars || 1), 0);
    if (have < wanted) {
      for (let tries = 0; tries < 3 && have + tries < wanted; tries++) {
        const clip = pick(lane, k, levels[k]);
        const entrance = tempos[k] < 0 ? clip.n - 1 : 0;
        const j = findStart(clip, tempos[k], gapIn.value, cars, true);
        if (j < 0) break;
        cars.push({ clip, pos: j, fadeIn: j !== entrance ? frame : undefined });
        lastClip[k] = clip;
      }
    } else if (have > wanted) {
      // too many: the farthest car (highest on the road) fades out
      mine.sort((p, q) => bottom(p) - bottom(q));
      mine[0].fade = frame;
    }
  }
  advance(tempos);
}

// piano roll mode: the quantity is a held note
function stepRoll(levels, tempos, scale) {
  for (let k = 0; k < 4; k++) {
    const lane = library.byLane[k];
    if (!lane.length || levels[k] <= 0.02) continue;
    const margin = Math.round((gapIn.value + (1 - levels[k]) * sparseGapIn.value) * scale);
    const clip = pick(lane, k, levels[k]);
    const entrance = tempos[k] < 0 ? clip.n - 1 : 0;
    if (canSpawn(clip, entrance, tempos[k], margin)) {
      cars.push({ clip, pos: entrance });
      lastClip[k] = clip;
    }
  }
  advance(tempos);
}

// ─── train ──────────────────────────────────────────────────────────────────
// Lane 0 is the train's length: 0 none; between, the loop of carriages is
// repeated a number of times; at 1 it never ends. Its tempo is the playback
// rate of the passage.

function loopsAllowed(level) {
  if (level >= 0.99) return Infinity;
  return Math.round(level * maxLoopsIn.value);
}

function stepTrain(level, tempo) {
  if (!trains) return;
  if (train && train.video.ended) {
    train = null;
    trainNextAt = frame + FPS * trainGapIn.value;
  }
  if (!train && level > 0.01 && trains.list.length && frame >= trainNextAt) {
    const t = trains.list[Math.floor(rng() * trains.list.length)];
    t.video.currentTime = 0;
    t.video.play();
    train = { ...t, loops: 0 };
  }
  if (!train) return;
  // Asked for more while the tail has only just begun: step back onto the
  // loop at the same offset. The frames match there, so the train simply
  // keeps coming instead of ending.
  if (train.loop_out) {
    const past = train.video.currentTime - train.loop_out / train.fps;
    if (past > 0 && past < 1 && loopsAllowed(level) > train.loops) {
      train.video.currentTime = train.loop_in / train.fps + past;
      train.loops++;
    }
  }
  const rate = Math.max(0, Math.min(16, tempo));
  if (rate < 0.05) train.video.pause();
  else {
    train.video.playbackRate = Math.max(0.0625, rate);
    if (train.video.paused) train.video.play();
  }
  if (train.loop_out && train.video.currentTime >= train.loop_out / train.fps && train.loops < loopsAllowed(level)) {
    train.video.currentTime = train.loop_in / train.fps;
    train.loops++;
  }
}

function drawTrain(scale) {
  if (!train) return;
  const w = Math.round(train.w * scale);
  const h = Math.round(train.h * scale);
  if (!trains.canvas) trains.canvas = new OffscreenCanvas(w, h);
  const tc = trains.canvas.getContext('2d');
  tc.globalCompositeOperation = 'source-over';
  tc.drawImage(train.video, 0, 0, w, h);
  tc.globalCompositeOperation = 'destination-in';
  tc.drawImage(trains.mask, 0, 0, w, h);
  ctx.drawImage(trains.canvas, Math.round(train.x * scale), Math.round(train.y * scale));
}

// ─── drawing ────────────────────────────────────────────────────────────────

function draw(plate) {
  ctx.drawImage(plate, 0, 0);
  drawTrain(plate.height / 1080);
  const active = cars.map((c) => ({ c, i: frameOf(c) })).filter((x) => x.i >= 0);
  active.sort((p, q) => bottom(p.c) - bottom(q.c)); // far cars first
  const fade = fadeIn.value;
  for (const { c, i } of active) {
    let a = c.fade === undefined ? 1 : Math.max(0, 1 - (frame - c.fade) / fade);
    if (c.fadeIn !== undefined) a = Math.min(a, (frame - c.fadeIn + 1) / fade);
    if (c.clip.poses) {
      drawRepaired(c.clip, c.pos, repairedBox(c.clip, c.pos), a);
      continue;
    }
    const b = c.clip.boxes[i];
    const j = Math.floor(i / (c.clip.sub || 1)); // stored frame
    const [cw, ch] = c.clip.cell;
    const sx = (j % c.clip.cols) * cw;
    const sy = Math.floor(j / c.clip.cols) * ch;
    if (laneMasks) drawMasked(c.clip.sheet, sx, sy, b, c.clip.lane - 1, a);
    else {
      ctx.globalAlpha = a;
      ctx.drawImage(c.clip.sheet, sx, sy, b[2], b[3], b[0], b[1], b[2], b[3]);
    }
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
  if (trainsIn.value && loadedTrains !== trainsIn.value) {
    loadedTrains = trainsIn.value;
    trains = await loadTrains(trainsIn.value);
    train = null;
  }
  if (!library || !plate) return;
  const scale = plate.height / 1080;
  if (library.borrow !== borrowIn.value) {
    assignLanes(library, borrowIn.value, scale);
    cars = [];
  }
  if (!canvas || canvas.width !== plate.width || canvas.height !== plate.height) {
    canvas = new OffscreenCanvas(plate.width, plate.height);
    ctx = canvas.getContext('2d');
    target.setSize(plate.width, plate.height);
  }
  const maskKey = `${plate.width}x${plate.height}:${laneMaskIn.value}:${laneFeatherIn.value}`;
  if (laneMaskKey !== maskKey) {
    laneMaskKey = maskKey;
    laneMasks = laneMaskIn.value > 0 ? buildLaneMasks(plate.width, plate.height, scale, laneMaskIn.value, laneFeatherIn.value) : null;
  }
  const levels = laneIns.slice(1).map((p) => p.value);
  const tempos = tempoIns.slice(1).map((p) => p.value * globalTempoIn.value);
  const roll = modeIn.value === 'piano roll';

  // Real time in the editor, one step per frame when exporting.
  let steps = 1;
  if (window.desktop.getRuntimeMode() !== 'export') {
    const now = performance.now();
    steps = Math.min(4, Math.floor(((now - lastTime) / 1000) * FPS));
    if (steps > 0) lastTime = now;
  }
  for (let s = 0; s < steps; s++) {
    if (roll) stepRoll(levels, tempos, scale);
    else stepCount(levels, tempos);
    stepTrain(laneIns[0].value, tempoIns[0].value * globalTempoIn.value);
    frame++;
  }
  draw(plate);
  target.uploadExternal(canvas);
  imageOut.set(target);
};

node.onStop = () => {
  target?.destroy();
  if (library) for (const lane of library.own) for (const c of lane) c.sheet.close();
  if (trains) for (const t of trains.list) t.video.pause();
};
