// Node for Max adapter. Zero npm dependencies: max-api ships with Node for Max.
// Usage in a patch:  [node.script shiftr-mqtt.js algorithmicgaze SECRET hands/mmwave/smooth_fast_breath @autostart 1]
// SECRET is the part after the colon in the instance URI mqtt://algorithmicgaze:SECRET@algorithmicgaze.cloud.shiftr.io
// Outlet messages:
//   status connected | status closed | status error <text>
//   <topic> <value>          value is a float when the payload parses as a number
const MqttMini = require("./mqtt-mini.js");

let max;
try { max = require("max-api"); }
catch (_) { max = { post: console.log, outlet: (...a) => console.log("outlet:", ...a), addHandler: () => {} }; }

const state = { client: null, topics: new Set(), cfg: null, retryTimer: null, wanted: false };

function status(...args) { max.outlet("status", ...args); }

function connect(instance, secret) {
  state.cfg = { instance, secret };
  state.wanted = true;
  clearTimeout(state.retryTimer);
  if (state.client) state.client.close();
  state.client = new MqttMini({
    url: `wss://${instance}.cloud.shiftr.io/broker`,
    username: instance,
    password: secret,
    clientId: "max-" + Math.random().toString(36).slice(2, 8),
    onConnect: () => {
      status("connected");
      for (const t of state.topics) state.client.subscribe(t, 0);
    },
    onMessage: (topic, text) => {
      const n = Number(text);
      max.outlet(topic, text.trim() !== "" && Number.isFinite(n) ? n : text);
    },
    onError: (err) => status("error", err.message),
    onClose: () => {
      status("closed");
      if (state.wanted) state.retryTimer = setTimeout(() => connect(instance, secret), 3000);
    },
  });
  state.client.connect();
}

max.addHandler("connect", (instance, secret) => {
  if (!instance || !secret) return status("error", "connect needs: instance secret");
  connect(String(instance), String(secret));
});
max.addHandler("subscribe", (topic) => {
  state.topics.add(String(topic));
  if (state.client && state.client.connected) state.client.subscribe(String(topic), 0);
});
max.addHandler("publish", (topic, ...rest) => {
  if (state.client && state.client.connected) state.client.publish(String(topic), rest.join(" "));
});
max.addHandler("disconnect", () => {
  state.wanted = false;
  clearTimeout(state.retryTimer);
  if (state.client) state.client.close();
});

// Optional startup from object-box arguments: instance secret [topic ...]
const [instance, secret, ...topics] = process.argv.slice(2);
for (const t of topics) state.topics.add(t);
if (instance && secret) connect(instance, secret);
