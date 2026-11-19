#pragma once
#include <Arduino.h>
#include "config.h"

enum class SpotState : uint8_t { FREE, OCCUPIED, FAULT };

const char* spotStateName(SpotState s);

// spot: 1..4
typedef void (*SpotChangeCb)(uint8_t spot, SpotState previous, SpotState current);

void sensorsBegin();
void sensorsUpdate(SpotChangeCb cb);   // uma rodada de leitura dos 4 sensores
SpotState sensorsState(uint8_t idx);   // idx 0..3
float sensorsDistance(uint8_t idx);    // última leitura em cm, -1 se inválida
