/*
 * Bring-up step 6 (MCU side) — stream A0, accept LED commands.
 *
 * Two-way traffic in one sketch:
 *   MCU  -> Python:  analog readings, pushed on a timer
 *   MCU <-  Python:  LED on/off, driven by a button in the browser
 *
 * Same discipline as always: the RPC handler sets a flag, loop() does the work.
 */

#include "Arduino_RouterBridge.h"

const int ADC_BITS = 14;
const int ADC_MAX = (1 << ADC_BITS) - 1;
const float VREF = 3.3f;

const unsigned long SAMPLE_INTERVAL_MS = 100;  // 10 Hz to the browser

volatile bool ledPending = false;
volatile bool ledDesired = false;

unsigned long previousMillis = 0;

// Registered with provide_safe, but still kept to a flag write — digitalWrite
// belongs in loop(), not in an RPC callback.
void set_led(bool on) {
    ledDesired = on;
    ledPending = true;
}

void setup() {
    Serial.begin(115200);

    analogReadResolution(ADC_BITS);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // active low: off

    Bridge.begin();
    Bridge.provide_safe("set_led", set_led);

    Bridge.notify("adc_config", ADC_MAX, VREF);

    Serial.println("Dashboard sketch ready.");
}

void loop() {
    if (ledPending) {
        ledPending = false;
        digitalWrite(LED_BUILTIN, ledDesired ? LOW : HIGH);  // active low
    }

    unsigned long now = millis();
    if (now - previousMillis < SAMPLE_INTERVAL_MS) {
        return;
    }
    previousMillis = now;

    Bridge.notify("adc_sample", analogRead(A0));
}
