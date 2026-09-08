#include <Arduino.h>
#include "Seeed_Arduino_mmWave.h"
#include <Adafruit_NeoPixel.h>
#include <WiFi.h>
#include <MQTT.h>

#ifdef ESP32
#  include <HardwareSerial.h>
HardwareSerial mmWaveSerial(0);
#else
#  define mmWaveSerial Serial1
#endif

// ---------- WiFi + Shiftr credentials ----------
const char* ssid         = "your_ssid";
const char* pass         = "your_password";
const char* mqttServer   = "your_server.cloud.shiftr.io";
const char* mqttClientId = "breath_demo";
const char* mqttUsername = "your_username";
const char* mqttPassword = "your_password";

WiFiClient net;
MQTTClient client;

// ---------- Status NeoPixel ----------
Adafruit_NeoPixel pixels = Adafruit_NeoPixel(1, D1, NEO_GRB + NEO_KHZ800);

typedef enum {
  STATUS_BOOT,
  STATUS_WIFI_CONNECTING,
  STATUS_MQTT_CONNECTING,
  STATUS_CONNECTED,
  STATUS_DISCONNECTED
} Status;

static bool pulseOn = true;

void setStatus(Status s) {
  uint32_t color = 0;
  switch (s) {
    case STATUS_BOOT:             color = pixels.Color( 30,  30,  30); break;
    case STATUS_WIFI_CONNECTING:  color = pulseOn ? pixels.Color(  0,   0, 125) : 0; break;
    case STATUS_MQTT_CONNECTING:  color = pulseOn ? pixels.Color(125, 100,   0) : 0; break;
    case STATUS_CONNECTED:        color = pixels.Color(  0, 125,   0); break;
    case STATUS_DISCONNECTED:     color = pixels.Color(125,   0,   0); break;
  }
  pixels.setPixelColor(0, color);
  pixels.show();
}

// ---------- mmWave ----------
SEEED_MR60BHA2 mmWave;

float total_phase = 0;
float smooth_fast_breath = 0;
bool smooth_fast_seeded = false;

// Tuned from capture sessions. Limit single-frame jumps from total_phase,
// then smooth the bounded motion.
const float SMOOTH_FAST_ALPHA    = 0.15f;
const float SMOOTH_FAST_MAX_STEP = 0.70f;

// Serial Plotter anchors. These are not published to MQTT.
const float PLOTTER_Y_RANGE = 1.0f;
const float PLOTTER_Y_MIN   = -PLOTTER_Y_RANGE;
const float PLOTTER_Y_MAX   =  PLOTTER_Y_RANGE;

void connect() {
  setStatus(STATUS_WIFI_CONNECTING);
  Serial.print("Checking wifi...");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    pulseOn = !pulseOn;
    setStatus(STATUS_WIFI_CONNECTING);
    delay(1000);
  }
  Serial.println(" connected to WiFi.");

  setStatus(STATUS_MQTT_CONNECTING);
  Serial.print("Connecting to Shiftr...");
  while (!client.connect(mqttClientId, mqttUsername, mqttPassword)) {
    Serial.print(".");
    pulseOn = !pulseOn;
    setStatus(STATUS_MQTT_CONNECTING);
    delay(1000);
  }
  Serial.println(" connected!");

  setStatus(STATUS_CONNECTED);
}

void publishFloat(const char* topic, float value) {
  char buf[16];
  dtostrf(value, 0, 2, buf);
  client.publish(topic, buf);
}

void setup() {
  Serial.begin(115200);
  mmWave.begin(&mmWaveSerial);
  Serial.println("Welcome, my heart is beatin'");

  pixels.begin();
  pixels.setBrightness(8);
  setStatus(STATUS_BOOT);

  WiFi.begin(ssid, pass);
  client.begin(mqttServer, net);
  connect();
}

void loop() {
  client.loop();
  if (!client.connected()) {
    setStatus(STATUS_DISCONNECTED);
    connect();
  }

  bool got_frame = mmWave.update(0);
  if (!got_frame) {
    delay(1);
    return;
  }

  float unused_filtered_phase;
  float unused_heart_phase;
  if (!mmWave.getHeartBreathPhases(total_phase, unused_filtered_phase, unused_heart_phase)) {
    return;
  }

  if (!smooth_fast_seeded) {
    smooth_fast_breath = total_phase;
    smooth_fast_seeded = true;
  } else {
    float smooth_target = constrain(total_phase,
                                    smooth_fast_breath - SMOOTH_FAST_MAX_STEP,
                                    smooth_fast_breath + SMOOTH_FAST_MAX_STEP);
    smooth_fast_breath =
        SMOOTH_FAST_ALPHA * smooth_target +
        (1.0f - SMOOTH_FAST_ALPHA) * smooth_fast_breath;
  }

  Serial.printf("smooth_fast:%.2f\taxis_lo:%.2f\taxis_hi:%.2f\n",
                smooth_fast_breath, PLOTTER_Y_MIN, PLOTTER_Y_MAX);

  publishFloat("hands/mmwave/smooth_fast_breath", smooth_fast_breath);
}
