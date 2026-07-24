/*
 * Bring-up step 3 (MCU side) — drive one digital pin at a time.
 *
 * Python owns the sequencing; the sketch just does what it's told. That split
 * is deliberate: it means you can change the walk order, speed, or pin list by
 * editing Python, with no reflash.
 *
 * ⚠️ THESE PINS ARE 3.3 V. Do not connect a 5 V source to any of them.
 */

#include "Arduino_RouterBridge.h"

// D0/D1 are excluded on purpose: they're the UART TX/RX pair and driving them
// interferes with serial. D2..D13 is the safe, useful range on the header.
const int FIRST_PIN = 2;
const int LAST_PIN = 13;
const int NUM_PINS = LAST_PIN - FIRST_PIN + 1;

volatile bool setPending = false;
volatile int pendingPin = -1;   // -1 means "all off"

// provide_safe -> runs in loop() context. Still does nothing but set a flag,
// because touching digitalWrite or Serial from an RPC handler is how you
// deadlock the Bridge.
void set_active_pin(int pin) {
    pendingPin = pin;
    setPending = true;
}

void allOff() {
    for (int pin = FIRST_PIN; pin <= LAST_PIN; pin++) {
        digitalWrite(pin, LOW);
    }
}

void setup() {
    Serial.begin(115200);

    for (int pin = FIRST_PIN; pin <= LAST_PIN; pin++) {
        pinMode(pin, OUTPUT);
    }
    allOff();

    Bridge.begin();
    Bridge.provide_safe("set_active_pin", set_active_pin);

    // Tell Python the pin range so it doesn't have to hardcode it.
    Bridge.notify("gpio_ready", FIRST_PIN, LAST_PIN);

    Serial.print("GPIO walk ready: D");
    Serial.print(FIRST_PIN);
    Serial.print("..D");
    Serial.println(LAST_PIN);
}

void loop() {
    if (!setPending) {
        return;
    }
    setPending = false;

    int pin = pendingPin;

    allOff();
    if (pin >= FIRST_PIN && pin <= LAST_PIN) {
        digitalWrite(pin, HIGH);
    }

    // Confirm back to Python so it can log what the hardware actually did,
    // rather than what it assumed. Safe here: we're in loop().
    Bridge.notify("gpio_active", pin);
}
