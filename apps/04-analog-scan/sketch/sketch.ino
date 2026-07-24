/*
 * Bring-up step 4 (MCU side) — sample A0..A5 and stream them to Python.
 *
 * The UNO Q's ADC does 14 bits, which is unusual for an Arduino and easy to
 * get wrong: full scale is 16383, not 1023. Set the resolution explicitly so
 * the value you get is the value you expect.
 *
 * Reference is 3.3 V by default. Anything above 3.3 V reads as full scale and
 * stresses the pin — don't.
 *
 * This sketch pushes data on its own timer rather than waiting to be asked.
 * Bridge.notify() is fire-and-forget, so streaming costs less than a
 * request/response round trip per sample.
 */

#include "Arduino_RouterBridge.h"
#include <vector>

const int ADC_BITS = 14;
const int ADC_MAX = (1 << ADC_BITS) - 1;  // 16383
const float VREF = 3.3f;

const int NUM_CHANNELS = 6;
const int CHANNELS[NUM_CHANNELS] = {A0, A1, A2, A3, A4, A5};

const unsigned long SAMPLE_INTERVAL_MS = 100;  // 10 Hz

unsigned long previousMillis = 0;

void setup() {
    Serial.begin(115200);

    analogReadResolution(ADC_BITS);  // must be explicit — default is not 14

    Bridge.begin();

    // Tell Python how to interpret the raw counts, so the scaling constants
    // live in exactly one place: here.
    Bridge.notify("adc_config", ADC_MAX, VREF, NUM_CHANNELS);

    Serial.print("ADC ready: ");
    Serial.print(ADC_BITS);
    Serial.print("-bit, full scale ");
    Serial.println(ADC_MAX);
}

void loop() {
    unsigned long now = millis();
    if (now - previousMillis < SAMPLE_INTERVAL_MS) {
        return;
    }
    previousMillis = now;

    // A std::vector maps to a Python list across the Bridge, so all six
    // channels travel as one message instead of six.
    std::vector<int> samples;
    samples.reserve(NUM_CHANNELS);
    for (int i = 0; i < NUM_CHANNELS; i++) {
        samples.push_back(analogRead(CHANNELS[i]));
    }

    Bridge.notify("adc_samples", samples);
}
