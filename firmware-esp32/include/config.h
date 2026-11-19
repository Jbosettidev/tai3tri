#pragma once
#include <stdint.h>
#include "secrets.h"

constexpr uint8_t NUM_SPOTS = 4;

// XMPP: mesma conta do backend, resources diferentes (esp32 <-> backend)
#define XMPP_RESOURCE  "esp32"
#define BACKEND_JID    XMPP_USER "@" XMPP_DOMAIN "/backend"
#define DEVICE_ID      "esp32-01"

// Sensores HC-SR04 (ECHO é 5 V! use divisor de tensão 1k/2k ou level shifter)
constexpr uint8_t PIN_TRIG[NUM_SPOTS] = {13, 14, 25, 26};
constexpr uint8_t PIN_ECHO[NUM_SPOTS] = {34, 35, 32, 33};   // GPIOs só-entrada, ok p/ ECHO

// LEDs (cada um com resistor de ~220-330 ohm)
constexpr uint8_t PIN_LED_GREEN[NUM_SPOTS] = {16, 17, 18, 19};
constexpr uint8_t PIN_LED_RED[NUM_SPOTS]   = {21, 22, 23, 27};

// Filtragem / leitura
constexpr float    OCCUPIED_MAX_CM = 25.0f;  // <= isso = ocupada
constexpr float    VALID_MIN_CM    = 2.0f;
constexpr float    VALID_MAX_CM    = 200.0f; // fora disso (ou sem eco) = leitura inválida
constexpr uint8_t  CONFIRM_READS   = 3;      // leituras iguais p/ confirmar FREE/OCCUPIED
constexpr uint8_t  FAULT_READS     = 5;      // leituras inválidas p/ declarar FAULT

constexpr uint32_t SENSOR_INTERVAL_MS = 250;
constexpr uint32_t HEARTBEAT_MS       = 10000;  // device.status periódico (backend marca OFFLINE após 30 s)
