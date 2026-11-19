#include "leds.h"

static SpotState shown[NUM_SPOTS];

static void apply(uint8_t i, bool green, bool red) {
  digitalWrite(PIN_LED_GREEN[i], green ? HIGH : LOW);
  digitalWrite(PIN_LED_RED[i],   red   ? HIGH : LOW);
}

void ledsSet(uint8_t i, SpotState s) {
  shown[i] = s;
  if (s == SpotState::FREE)          apply(i, true, false);
  else if (s == SpotState::OCCUPIED) apply(i, false, true);
  // FAULT: tratado em ledsLoop()
}

void ledsBegin() {
  for (uint8_t i = 0; i < NUM_SPOTS; i++) {
    pinMode(PIN_LED_GREEN[i], OUTPUT);
    pinMode(PIN_LED_RED[i], OUTPUT);
    ledsSet(i, SpotState::FREE);
  }
}

void ledsLoop() {
  bool on = (millis() / 500) % 2;
  for (uint8_t i = 0; i < NUM_SPOTS; i++)
    if (shown[i] == SpotState::FAULT) apply(i, on, on);   // ambos piscando
}

void ledsRestore() {
  for (uint8_t i = 0; i < NUM_SPOTS; i++) {
    if (shown[i] == SpotState::FAULT) apply(i, false, false);
    else ledsSet(i, shown[i]);
  }
}

void ledsTest() {
  for (uint8_t r = 0; r < 3; r++) {
    for (uint8_t i = 0; i < NUM_SPOTS; i++) apply(i, true, true);
    delay(300);
    for (uint8_t i = 0; i < NUM_SPOTS; i++) apply(i, false, false);
    delay(300);
  }
  ledsRestore();
}
