/**
 * @name Hand Keys
 * @description Fingers over five areas of the frame become five lane values.
 * @category ml
 */

// The frame is a keyboard with five keys side by side. Every fingertip in
// a key presses it. The value of a key is how many fingertips press it,
// divided by 'fingers for full', clamped to 1, then smoothed. Feed the
// five outputs into the Highway node's lane 0 to lane 4.
//
// The image output draws the keys: a coloured band per key whose fill
// rises with its value, the fingertips that press it, and the numbers.
// Lay it over the webcam with a Composite node to see what you play.

const landmarksIn = node.objectIn('landmarks');
const imageIn = node.imageIn('in');
const widthIn = node.numberIn('width', 1280, { min: 64, max: 4096, step: 1 });
const heightIn = node.numberIn('height', 720, { min: 64, max: 4096, step: 1 });
const keysIn = node.numberIn('keys', 5, { min: 1, max: 12, step: 1 });
const leftIn = node.numberIn('left', 0, { min: 0, max: 1, step: 0.01 });
const rightIn = node.numberIn('right', 1, { min: 0, max: 1, step: 0.01 });
const fullIn = node.numberIn('fingers for full', 1, { min: 1, max: 10, step: 1 });
const smoothingIn = node.numberIn('smoothing', 0.5, { min: 0, max: 0.98, step: 0.01 });
const mirrorIn = node.toggleIn('mirror', true);
const tipsOnlyIn = node.toggleIn('fingertips only', true);
const outs = [
  node.numberOut('lane 0', 0),
  node.numberOut('lane 1', 0),
  node.numberOut('lane 2', 0),
  node.numberOut('lane 3', 0),
  node.numberOut('lane 4', 0),
  node.numberOut('key 5', 0),
  node.numberOut('key 6', 0),
  node.numberOut('key 7', 0),
  node.numberOut('key 8', 0),
  node.numberOut('key 9', 0),
  node.numberOut('key 10', 0),
  node.numberOut('key 11', 0),
];
const levelsOut = node.objectOut('levels');
const imageOut = node.imageOut('out');

const COLORS = ['#f2a33a', '#5ec26a', '#d05ad8', '#3aa6e8', '#ef5a5a', '#e8d23a', '#3ad8c8', '#a06ae8', '#e88a3a', '#6ae8a0', '#e83a9a', '#9ae83a'];
let target, canvas, ctx;

// The Composite node ignores alpha, so the overlay is opaque: colours are
// scaled by the value on black. Lay it over the webcam with 'lighten'.
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) * f, g = ((n >> 8) & 255) * f, b = (n & 255) * f;
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}

const TIPS = [4, 8, 12, 16, 20]; // thumb, index, middle, ring, pinky
let levels = new Array(12).fill(0);
let tips = []; // [x, y] in 0..1, mirrored, for drawing

node.onStart = () => {
  levels = new Array(12).fill(0);
  tips = [];
  target = new figment.RenderTarget({ label: 'handKeys' });
};

function drawKeys(keys, left, right) {
  const img = imageIn.value;
  const w = img && img.width ? img.width : Math.round(widthIn.value);
  const h = img && img.height ? img.height : Math.round(heightIn.value);
  if (!canvas || canvas.width !== w || canvas.height !== h) {
    canvas = new OffscreenCanvas(w, h);
    ctx = canvas.getContext('2d');
    target.setSize(w, h);
  }
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);
  const x0 = left * w;
  const kw = ((right - left) * w) / keys;
  ctx.font = `${Math.round(h / 18)}px sans-serif`;
  ctx.textAlign = 'center';
  for (let k = 0; k < keys; k++) {
    const x = x0 + k * kw;
    const v = levels[k];
    const color = COLORS[k % COLORS.length];
    ctx.fillStyle = shade(color, 0.15 + 0.4 * v); // the whole key tints with its value
    ctx.fillRect(x, 0, kw, h);
    ctx.fillStyle = shade(color, 0.9); // and fills from the bottom like a meter
    ctx.fillRect(x, h * (1 - v), kw, h * v);
    ctx.strokeStyle = '#999';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, 0, kw, h);
    ctx.fillStyle = '#fff';
    ctx.fillText(`${k}`, x + kw / 2, h / 12);
    ctx.fillText(v.toFixed(2), x + kw / 2, h - h / 30);
  }
  for (const [tx, ty] of tips) {
    ctx.beginPath();
    ctx.arc(tx * w, ty * h, Math.max(4, h / 60), 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  target.uploadExternal(canvas);
  imageOut.set(target);
}

node.onRender = () => {
  const keys = Math.round(keysIn.value);
  const counts = new Array(12).fill(0);
  const data = landmarksIn.value;
  const hands = data && Array.isArray(data.landmarks) ? data.landmarks : [];
  const left = Math.min(leftIn.value, rightIn.value);
  const right = Math.max(rightIn.value, left + 0.01);
  tips = [];
  for (const hand of hands) {
    const points = tipsOnlyIn.value ? TIPS.map((i) => hand[i]).filter(Boolean) : hand;
    for (const p of points) {
      const mx = mirrorIn.value ? 1 - p.x : p.x;
      tips.push([mx, p.y]);
      const x = (mx - left) / (right - left);
      if (x < 0 || x >= 1) continue;
      counts[Math.floor(x * keys)]++;
    }
  }
  const a = smoothingIn.value;
  for (let k = 0; k < 12; k++) {
    const v = k < keys ? Math.min(1, counts[k] / fullIn.value) : 0;
    levels[k] = a * levels[k] + (1 - a) * v;
    outs[k].set(levels[k]);
  }
  levelsOut.set(levels.slice(0, keys));
  drawKeys(keys, left, right);
};

node.onStop = () => {
  target?.destroy();
};
