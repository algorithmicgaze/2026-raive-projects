// Run against the actual Highway code with @napi-rs/canvas installed outside source.
// node verify-renderer.cjs CARS_ROOT CANVAS_RUNTIME_NODE_MODULES
const fs = require("node:fs"),
  path = require("node:path"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const root = path.resolve(process.argv[2]),
  out = path.join(root, "output-figment");
const { createCanvas, loadImage } = require(
  path.join(path.resolve(process.argv[3]), "@napi-rs/canvas"),
);
const source = fs.readFileSync(
  process.argv[4] || path.join(__dirname, "../figment/highway.js"),
  "utf8",
);
const ports = {};
const node = new Proxy(
  {},
  {
    get: (o, k) =>
      o[k] || ((name, value) => (ports[name] = { value, set() {} })),
  },
);
const sandbox = {
  node,
  OffscreenCanvas: function (w, h) {
    return createCanvas(w, h);
  },
  performance,
  console,
};
vm.createContext(sandbox);
vm.runInContext(
  source +
    "\nthis.api={draw,buildLaneMasks,shifted,setContext(c){ctx=c;},setMasks(m){laneMasks=m;},setCars(v){cars=v;},setFrame(v){frame=v;}};",
  sandbox,
);
const api = sandbox.api;
async function main() {
  const manifest = fs.existsSync(path.join(out, "manifest-masked.json"))
    ? JSON.parse(fs.readFileSync(path.join(out, "manifest-masked.json")))
    : {
        clips: fs
          .readdirSync(path.join(out, "masked/jobs"))
          .map(
            (f) =>
              JSON.parse(fs.readFileSync(path.join(out, "masked/jobs", f)))
                .clip,
          ),
      };
  const clips = [...new Map(manifest.clips.map((c) => [c.sheet, c])).values()];
  const canvas = createCanvas(1920, 1080),
    ctx = canvas.getContext("2d");
  api.setContext(ctx);
  const plate = await loadImage(path.join(out, "plate.png"));
  const masks = api.buildLaneMasks(1920, 1080, 1, 0.35, 18);
  const report = {
    clips: [],
    gridCompatibility: false,
    shelfCompatibility: false,
    sourceSha256: require("node:crypto")
      .createHash("sha256")
      .update(source)
      .digest("hex"),
  };
  // Both atlas layouts must draw the same source pixels at the same position.
  const grid = createCanvas(12, 6),
    g = grid.getContext("2d");
  g.fillStyle = "#ff0000";
  g.fillRect(0, 0, 6, 6);
  g.fillStyle = "#00ff00";
  g.fillRect(6, 0, 6, 6);
  const base = {
    sheet: grid,
    boxes: [
      [800, 700, 6, 6],
      [802, 702, 6, 6],
    ],
    n: 2,
    lane: 1,
    sub: 1,
    cell: [6, 6],
    cols: 2,
  };
  const draw = (c, pos) => {
    api.setCars([{ clip: c, pos }]);
    api.setFrame(20);
    api.draw(plate);
  };
  api.setMasks(null);
  draw(base, 1);
  const old = ctx.getImageData(802, 702, 6, 6).data;
  draw(
    {
      ...base,
      cell: [1, 1],
      cols: 1,
      frameRects: [
        [0, 0, 6, 6],
        [6, 0, 6, 6],
      ],
    },
    1,
  );
  assert.deepEqual(ctx.getImageData(802, 702, 6, 6).data, old);
  assert.equal(old[1], 255);
  report.gridCompatibility = true;
  report.shelfCompatibility = true;
  for (const c of clips) {
    const filename = c.sheet;
    c.sheet = await loadImage(path.join(out, filename));
    c.n = c.boxes.length;
    assert(c.sheet.width <= 16384 && c.sheet.height <= 16384);
    assert.equal(c.frameRects.length, Math.ceil(c.n / c.sub));
    for (let i = 0; i < c.n; i++) {
      const b = c.boxes[i],
        r = c.frameRects[Math.floor(i / c.sub)];
      assert(b.every(Number.isFinite));
      assert(b[2] > 0 && b[3] > 0);
      assert.equal(b[2], r[2]);
      assert.equal(b[3], r[3]);
      assert(
        r[0] >= 0 &&
          r[1] >= 0 &&
          r[0] + r[2] <= c.sheet.width &&
          r[1] + r[3] <= c.sheet.height,
      );
    }
    api.setMasks(masks);
    for (const pos of [
      0,
      1,
      c.n * 0.25,
      c.n * 0.5,
      c.n * 0.75,
      c.n - 1,
    ].reverse())
      draw(c, Math.floor(pos));
    const shifted = api.shifted(c, c.lane % 4, 1);
    assert.equal(shifted.frameRects, c.frameRects);
    assert.equal(shifted.n, c.n);
    report.clips.push({
      id: c.id,
      lane: c.lane,
      frames: c.n,
      width: c.sheet.width,
      height: c.sheet.height,
    });
  }
  // Retain only four loaded atlases for the multi-lane preview.
  const ids = ["f0_0048", "f1753_0003", "w107_0103", "w107_0342"];
  const preview = ids.map((id, i) =>
    clips.find((c) => c.id === id && c.lane === i + 1),
  );
  assert(preview.every(Boolean));
  const video = path.join(out, "masked/review/masked-library.mp4");
  const ff = spawn(
    "ffmpeg",
    [
      "-y",
      "-loglevel",
      "error",
      "-f",
      "rawvideo",
      "-pixel_format",
      "rgba",
      "-video_size",
      "1920x1080",
      "-framerate",
      "25",
      "-i",
      "pipe:0",
      "-an",
      "-c:v",
      "libx264",
      "-crf",
      "18",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      video,
    ],
    { stdio: ["pipe", "inherit", "inherit"] },
  );
  const completion = once(ff, "close");
  for (let i = 0; i < 250; i++) {
    api.setCars(
      preview.map((c) => ({ clip: c, pos: Math.floor((i / 249) * (c.n - 1)) })),
    );
    api.setFrame(20);
    api.draw(plate);
    if (!ff.stdin.write(Buffer.from(ctx.getImageData(0, 0, 1920, 1080).data)))
      await once(ff.stdin, "drain");
  }
  ff.stdin.end();
  assert.equal((await completion)[0], 0);
  fs.writeFileSync(
    path.join(out, "masked/review/renderer-verification.json"),
    JSON.stringify(report, null, 2),
  );
  console.log(
    JSON.stringify({
      verified: report.clips.length,
      gridCompatibility: true,
      shelfCompatibility: true,
    }),
  );
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
