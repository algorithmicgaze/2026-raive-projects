// Minimal MQTT 3.1.1 client over WebSocket. No dependencies: Node 22+ has a global WebSocket.
const enc = new TextEncoder();
const dec = new TextDecoder();

function mqttString(s) {
  const b = enc.encode(s);
  const out = new Uint8Array(2 + b.length);
  out[0] = b.length >> 8;
  out[1] = b.length & 255;
  out.set(b, 2);
  return out;
}

function concat(parts) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Uint8Array(n);
  let i = 0;
  for (const p of parts) { out.set(p, i); i += p.length; }
  return out;
}

function packet(type, flags, body) {
  const len = [];
  let n = body.length;
  do {
    let d = n % 128;
    n = Math.floor(n / 128);
    if (n > 0) d |= 128;
    len.push(d);
  } while (n > 0);
  return concat([new Uint8Array([(type << 4) | flags, ...len]), body]);
}

const CONNECT = 1, CONNACK = 2, PUBLISH = 3, PUBACK = 4,
      SUBSCRIBE = 8, SUBACK = 9, PINGREQ = 12, PINGRESP = 13, DISCONNECT = 14;

const CONNACK_TEXT = {
  0: "accepted",
  1: "unacceptable protocol version",
  2: "identifier rejected",
  3: "server unavailable",
  4: "bad username or password",
  5: "not authorized",
};

class MqttMini {
  constructor(opts) {
    this.url = opts.url;
    this.username = opts.username;
    this.password = opts.password;
    this.clientId = opts.clientId || "mqtt-mini-" + Math.random().toString(36).slice(2, 8);
    this.keepalive = opts.keepalive || 30;
    this.onConnect = opts.onConnect || (() => {});
    this.onMessage = opts.onMessage || (() => {});
    this.onClose = opts.onClose || (() => {});
    this.onError = opts.onError || (() => {});
    this.ws = null;
    this.buf = new Uint8Array(0);
    this.packetId = 0;
    this.pingTimer = null;
    this.connected = false;
  }

  connect() {
    this.close();
    const ws = new WebSocket(this.url, "mqtt");
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      let flags = 0x02; // clean session
      const payload = [mqttString(this.clientId)];
      if (this.username != null) { flags |= 0x80; payload.push(mqttString(this.username)); }
      if (this.password != null) { flags |= 0x40; payload.push(mqttString(this.password)); }
      const body = concat([
        mqttString("MQTT"),
        new Uint8Array([4, flags, this.keepalive >> 8, this.keepalive & 255]),
        ...payload,
      ]);
      this.send(packet(CONNECT, 0, body));
    };
    ws.onmessage = (e) => this.feed(new Uint8Array(e.data));
    ws.onerror = () => this.onError(new Error("websocket error"));
    ws.onclose = (e) => {
      const was = this.connected;
      this.connected = false;
      this.stopPing();
      if (this.ws === ws) this.ws = null;
      this.onClose(e.code, was);
    };
  }

  close() {
    this.stopPing();
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      try { if (ws.readyState === 1 && this.connected) ws.send(packet(DISCONNECT, 0, new Uint8Array(0))); } catch (_) {}
      try { ws.close(); } catch (_) {}
    }
    this.connected = false;
    this.buf = new Uint8Array(0);
  }

  subscribe(topic, qos) {
    const id = this.nextId();
    const body = concat([new Uint8Array([id >> 8, id & 255]), mqttString(topic), new Uint8Array([qos || 0])]);
    this.send(packet(SUBSCRIBE, 2, body));
  }

  publish(topic, payload) {
    const data = typeof payload === "string" ? enc.encode(payload) : payload;
    this.send(packet(PUBLISH, 0, concat([mqttString(topic), data])));
  }

  send(bytes) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(bytes);
  }

  nextId() {
    this.packetId = (this.packetId % 65535) + 1;
    return this.packetId;
  }

  startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => this.send(packet(PINGREQ, 0, new Uint8Array(0))), this.keepalive * 500);
  }

  stopPing() {
    if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = null; }
  }

  // Accumulate bytes; a WebSocket frame may hold several or partial MQTT packets.
  feed(bytes) {
    this.buf = this.buf.length ? concat([this.buf, bytes]) : bytes;
    for (;;) {
      const b = this.buf;
      if (b.length < 2) return;
      let mul = 1, len = 0, i = 1, d;
      do {
        if (i >= b.length) return;
        d = b[i++];
        len += (d & 127) * mul;
        mul *= 128;
      } while (d & 128);
      if (b.length < i + len) return;
      this.handle(b[0] >> 4, b[0] & 15, b.subarray(i, i + len));
      this.buf = b.subarray(i + len);
    }
  }

  handle(type, flags, body) {
    if (type === CONNACK) {
      const rc = body[1];
      if (rc === 0) {
        this.connected = true;
        this.startPing();
        this.onConnect();
      } else {
        this.onError(new Error("connect refused: " + (CONNACK_TEXT[rc] || rc)));
        this.close();
      }
    } else if (type === PUBLISH) {
      const qos = (flags >> 1) & 3;
      const tl = (body[0] << 8) | body[1];
      const topic = dec.decode(body.subarray(2, 2 + tl));
      let p = 2 + tl;
      if (qos > 0) {
        const id = body.subarray(p, p + 2);
        p += 2;
        if (qos === 1) this.send(packet(PUBACK, 0, id));
      }
      this.onMessage(topic, dec.decode(body.subarray(p)), body.subarray(p));
    }
    // SUBACK, PINGRESP: nothing to do.
  }
}

module.exports = MqttMini;
