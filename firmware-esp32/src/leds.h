#pragma once
#include <Arduino.h>
#include "sensores.h"

void ledsBegin();
void ledsSet(uint8_t idx, SpotState s);   // idx 0..3
void ledsLoop();                          // pisca LEDs de vagas em FAULT
void ledsTest();                          // bloqueante (~2 s)
void ledsRestore();                       // reaplica o estado atual
