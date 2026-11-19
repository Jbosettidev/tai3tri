#include "sensores.h"

static SpotState confirmed[NUM_SPOTS];
static SpotState candidate[NUM_SPOTS];
static uint8_t   streak[NUM_SPOTS];
static float     lastDist[NUM_SPOTS];

const char* spotStateName(SpotState s) {
  switch (s) {
    case SpotState::FREE:     return "FREE";
    case SpotState::OCCUPIED: return "OCCUPIED";
    default:                  return "FAULT";
  }
}

static float readDistanceCm(uint8_t i) {
  digitalWrite(PIN_TRIG[i], LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG[i], HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG[i], LOW);
  unsigned long us = pulseIn(PIN_ECHO[i], HIGH, 25000UL);  // ~4 m
  if (us == 0) return -1.0f;
  float cm = us / 58.0f;
  if (cm < VALID_MIN_CM || cm > VALID_MAX_CM) return -1.0f;
  return cm;
}

static SpotState classify(float cm) {
  if (cm < 0) return SpotState::FAULT;
  return cm <= OCCUPIED_MAX_CM ? SpotState::OCCUPIED : SpotState::FREE;
}

void sensorsBegin() {
  for (uint8_t i = 0; i < NUM_SPOTS; i++) {
    pinMode(PIN_TRIG[i], OUTPUT);
    digitalWrite(PIN_TRIG[i], LOW);
    pinMode(PIN_ECHO[i], INPUT);
    confirmed[i] = candidate[i] = SpotState::FREE;  // estado inicial assumido
    streak[i] = 0;
    lastDist[i] = -1.0f;
  }
}

void sensorsUpdate(SpotChangeCb cb) {
  for (uint8_t i = 0; i < NUM_SPOTS; i++) {
    float d = readDistanceCm(i);
    lastDist[i] = d;
    SpotState s = classify(d);

    if (s == candidate[i]) {
      if (streak[i] < 255) streak[i]++;
    } else {
      candidate[i] = s;
      streak[i] = 1;
    }

    uint8_t need = (s == SpotState::FAULT) ? FAULT_READS : CONFIRM_READS;
    if (candidate[i] != confirmed[i] && streak[i] >= need) {
      SpotState prev = confirmed[i];
      confirmed[i] = candidate[i];
      if (cb) cb(i + 1, prev, confirmed[i]);
    }
    delay(30);  // evita interferência entre sensores
  }
}

SpotState sensorsState(uint8_t idx)  { return confirmed[idx]; }
float     sensorsDistance(uint8_t idx) { return lastDist[idx]; }
