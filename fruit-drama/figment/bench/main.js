// Minimal Electron harness: same Chromium and onnxruntime-web as Figment,
// but Chromium switches are set here instead of on the command line.
//   cd ~/Projects/figment && npx electron ~/…/fruit-drama/figment/bench/main.js MODEL.onnx [frames] [switch=value ...]
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

const [modelPath, framesArg, ...switches] = process.argv.slice(2);
const frames = Number(framesArg) || 30;
app.commandLine.appendSwitch('enable-unsafe-webgpu');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
for (const s of switches) {
  const [k, v] = s.split('=');
  if (v === undefined) app.commandLine.appendSwitch(k);
  else app.commandLine.appendSwitch(k, v);
}

ipcMain.on('bench-result', (_e, result) => {
  process.stdout.write(JSON.stringify(result) + '\n');
  app.exit(result.error ? 1 : 0);
});

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 800, height: 600, show: false,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), webSecurity: false },
  });
  const ortDir = path.join(process.cwd(), 'node_modules', 'onnxruntime-web', 'dist');
  const query = new URLSearchParams({ model: path.resolve(modelPath), frames: String(frames), ortDir }).toString();
  win.loadFile(path.join(__dirname, 'bench.html'), { search: '?' + query });
});
