/**
 * @name Piano Roll
 * @description Draw five keyboard sections as falling bars, one per input.
 * @category image
 */

// Each section input is a level from 0 to 1. Every step the current levels
// are painted as a row at the "now" edge and the history scrolls away from
// it, so a held level becomes a long bar. At 0 nothing is drawn. Height and
// brightness of a bar follow the level.

node.timeDependent = true;
const s1In = node.numberIn('section 1', 0, { min: 0, max: 1, step: 0.01 });
const s2In = node.numberIn('section 2', 0, { min: 0, max: 1, step: 0.01 });
const s3In = node.numberIn('section 3', 0, { min: 0, max: 1, step: 0.01 });
const s4In = node.numberIn('section 4', 0, { min: 0, max: 1, step: 0.01 });
const s5In = node.numberIn('section 5', 0, { min: 0, max: 1, step: 0.01 });
const widthIn = node.numberIn('width', 1280, { min: 64, max: 4096, step: 1 });
const heightIn = node.numberIn('height', 720, { min: 64, max: 4096, step: 1 });
// Pixels the roll moves per second. Export runs at 25 frames per second.
const speedIn = node.numberIn('speed', 240, { min: 1, max: 2000, step: 1 });
// 'down': now is at the top, bars fall like the inspiration. 'up': now is at the bottom.
const directionIn = node.selectIn('direction', ['down', 'up'], 'down');
// Bar width as a fraction of the section width.
const barIn = node.numberIn('bar width', 0.5, { min: 0.05, max: 1, step: 0.01 });
// Below this level a section draws nothing, so noise does not leave a trail.
const gateIn = node.numberIn('gate', 0.02, { min: 0, max: 1, step: 0.01 });
const colorIn = node.colorIn('color', [140, 220, 90, 1]);
const backgroundIn = node.colorIn('background', [30, 30, 30, 1]);
const dividersIn = node.toggleIn('dividers', true);
// Key strip at the "now" edge that lights up with the level.
const keysIn = node.numberIn('keys height', 60, { min: 0, max: 400, step: 1 });
const imageOut = node.imageOut('out');

const FPS = 25;
const N = 5;
let target, canvas, ctx, roll, rctx;
let lastTime = 0;
let carry = 0; // sub-pixel scroll left over from the last step

const rgba = (c, a = c[3]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;

node.onStart = () => {
  target = new figment.RenderTarget({ label: 'piano roll' });
  lastTime = performance.now();
};

function ensureSize(w, h) {
  if (canvas && canvas.width === w && canvas.height === h) return;
  canvas = new OffscreenCanvas(w, h);
  ctx = canvas.getContext('2d');
  roll = new OffscreenCanvas(w, h);
  rctx = roll.getContext('2d');
  rctx.fillStyle = rgba(backgroundIn.value);
  rctx.fillRect(0, 0, w, h);
  target.setSize(w, h);
}

// Scroll the roll by dy pixels and paint the fresh rows at the now edge.
function advance(levels, dy) {
  const w = roll.width, h = roll.height;
  const down = directionIn.value === 'down';
  rctx.globalCompositeOperation = 'copy';
  rctx.drawImage(roll, 0, down ? dy : -dy);
  rctx.globalCompositeOperation = 'source-over';
  const y0 = down ? 0 : h - dy;
  rctx.fillStyle = rgba(backgroundIn.value);
  rctx.fillRect(0, y0, w, dy);
  const section = w / N;
  for (let i = 0; i < N; i++) {
    const v = levels[i];
    if (v < gateIn.value) continue;
    const bw = section * barIn.value * (0.6 + 0.4 * v);
    const x = section * (i + 0.5) - bw / 2;
    rctx.fillStyle = rgba(colorIn.value, colorIn.value[3] * (0.35 + 0.65 * v));
    rctx.fillRect(x, y0, bw, dy);
  }
}

function draw(levels) {
  const w = canvas.width, h = canvas.height;
  ctx.drawImage(roll, 0, 0);
  const section = w / N;
  if (dividersIn.value) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
    for (let i = 1; i < N; i++) ctx.fillRect(Math.round(section * i), 0, 1, h);
  }
  const kh = keysIn.value;
  if (kh > 0) {
    const down = directionIn.value === 'down';
    const y = down ? 0 : h - kh;
    ctx.fillStyle = '#f4f4f0';
    ctx.fillRect(0, y, w, kh);
    for (let i = 0; i < N; i++) {
      const v = levels[i];
      if (v >= gateIn.value) {
        ctx.fillStyle = rgba(colorIn.value, colorIn.value[3] * (0.35 + 0.65 * v));
        ctx.fillRect(section * i, y, section, kh);
      }
      ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
      ctx.fillRect(Math.round(section * i), y, 1, kh);
    }
    ctx.fillStyle = 'rgba(200, 40, 40, 1)';
    ctx.fillRect(0, down ? kh : y - 2, w, 2);
  }
}

node.onRender = () => {
  ensureSize(Math.round(widthIn.value), Math.round(heightIn.value));
  const levels = [s1In.value, s2In.value, s3In.value, s4In.value, s5In.value];

  // Real time in the editor, one frame per render when exporting.
  let dt = 1 / FPS;
  if (window.desktop.getRuntimeMode() !== 'export') {
    const now = performance.now();
    dt = Math.min(0.25, (now - lastTime) / 1000);
    lastTime = now;
  }
  carry += speedIn.value * dt;
  const dy = Math.floor(carry);
  carry -= dy;
  if (dy > 0) advance(levels, dy);
  draw(levels);
  target.uploadExternal(canvas);
  imageOut.set(target);
};

node.onStop = () => {
  target?.destroy();
};
