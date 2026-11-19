#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include "config.h"
#include "sensores.h"
#include "leds.h"
#include "xmpp_client.h"

static XmppClient xmpp;
static uint32_t lastSensor = 0, lastHeartbeat = 0, lastWifiTry = 0;

static void sendJson(const JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  xmpp.sendMessage(BACKEND_JID, out);
}

static void sendStatus(const char* commandId) {
  JsonDocument doc;
  doc["type"] = "device.status";
  doc["device"] = DEVICE_ID;
  if (commandId && commandId[0]) doc["commandId"] = commandId;
  JsonArray arr = doc["spots"].to<JsonArray>();
  for (uint8_t i = 0; i < NUM_SPOTS; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["spot"] = i + 1;
    o["status"] = spotStateName(sensorsState(i));
    float d = sensorsDistance(i);
    if (d >= 0) o["distanceCm"] = roundf(d * 10) / 10;
  }
  sendJson(doc);
}

static void sendAck(const char* commandId, const char* command, bool ok, const char* detail) {
  JsonDocument doc;
  doc["type"] = "command.ack";
  doc["device"] = DEVICE_ID;
  doc["commandId"] = commandId;
  doc["command"] = command;
  doc["ok"] = ok;
  if (detail) doc["detail"] = detail;
  sendJson(doc);
}

static void onSpotChange(uint8_t spot, SpotState prev, SpotState cur) {
  Serial.printf("[vaga %u] %s -> %s\n", spot, spotStateName(prev), spotStateName(cur));
  ledsSet(spot - 1, cur);
  JsonDocument doc;
  doc["device"] = DEVICE_ID;
  doc["spot"] = spot;
  doc["status"] = spotStateName(cur);
  if (cur == SpotState::FAULT) {
    doc["type"] = "sensor.error";
  } else {
    doc["type"] = "parking.update";
    float d = sensorsDistance(spot - 1);
    if (d >= 0) doc["distanceCm"] = roundf(d * 10) / 10;
  }
  doc["uptimeMs"] = millis();   // sem RTC/NTP: o backend carimba o horário real
  sendJson(doc);
}

static void onXmppMessage(const String& from, const String& body) {
  if (!from.startsWith(BACKEND_JID)) return;   // só aceita comandos do backend
  JsonDocument doc;
  if (deserializeJson(doc, body)) return;
  const char* type = doc["type"] | "";
  const char* cid  = doc["commandId"] | "";
  Serial.printf("[cmd] %s (%s)\n", type, cid);

  if (!strcmp(type, "status.request")) {
    sendStatus(cid);
  } else if (!strcmp(type, "sensor.read")) {
    sensorsUpdate(onSpotChange);
    sendStatus(cid);
  } else if (!strcmp(type, "led.test")) {
    ledsTest();
    sendAck(cid, "led.test", true, nullptr);
  } else {
    sendAck(cid, type, false, "comando desconhecido");
  }
}

void setup() {
  Serial.begin(115200);
  sensorsBegin();
  ledsBegin();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  xmpp.begin(XMPP_HOST, XMPP_PORT, XMPP_DOMAIN, XMPP_USER, XMPP_PASS, XMPP_RESOURCE);
  xmpp.onMessage(onXmppMessage);
}

void loop() {
  uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED && now - lastWifiTry > 10000) {
    lastWifiTry = now;
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASS);
  }

  xmpp.loop();
  if (xmpp.justConnected()) {
    JsonDocument doc;
    doc["type"] = "device.online";
    doc["device"] = DEVICE_ID;
    sendJson(doc);
    sendStatus(nullptr);
    lastHeartbeat = now;
  }

  if (now - lastSensor >= SENSOR_INTERVAL_MS) {
    lastSensor = now;
    sensorsUpdate(onSpotChange);
  }

  if (xmpp.connected() && now - lastHeartbeat >= HEARTBEAT_MS) {
    lastHeartbeat = now;
    sendStatus(nullptr);
  }

  ledsLoop();
}
