/*
 * Bring-up step 1 — is the MCU side healthy?
 *
 * Runs entirely on the STM32U585 under Zephyr. No Bridge, no Python. If this
 * works, the sketch toolchain compiles, flashes, and runs, and you can trust
 * the MCU half of the board.
 *
 * Every LED on this board is ACTIVE LOW: writing LOW turns a segment ON.
 * That trips people up constantly, so this sketch is explicit about it.
 */

// Named for readability — the inversion lives in one place.
const int ON = LOW;
const int OFF = HIGH;

// LED 3 is one of the two RGB LEDs wired to the MCU.
// (LED 1 and LED 2 belong to Linux — see app 00.)
const int LED3[] = {LED3_R, LED3_G, LED3_B};
const char *LED3_NAMES[] = {"red", "green", "blue"};
const int NUM_SEGMENTS = 3;

const unsigned long STEP_MS = 500;

int segment = 0;
unsigned long previousMillis = 0;
bool builtinOn = false;

void setLed3(int activeSegment) {
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        digitalWrite(LED3[i], i == activeSegment ? ON : OFF);
    }
}

void setup() {
    Serial.begin(115200);  // shows up in the App Lab console (core 0.55.0+)

    pinMode(LED_BUILTIN, OUTPUT);
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        pinMode(LED3[i], OUTPUT);
    }

    digitalWrite(LED_BUILTIN, OFF);
    setLed3(-1);  // -1 matches no segment, so all off

    Serial.println("MCU alive. LED_BUILTIN toggles, LED 3 cycles R/G/B.");
}

void loop() {
    // Non-blocking timing rather than delay(): the Bridge's background thread
    // shares this core, and getting into the habit early avoids stalls in the
    // later apps where it actually matters.
    unsigned long now = millis();
    if (now - previousMillis < STEP_MS) {
        return;
    }
    previousMillis = now;

    builtinOn = !builtinOn;
    digitalWrite(LED_BUILTIN, builtinOn ? ON : OFF);

    setLed3(segment);
    Serial.print("LED 3 -> ");
    Serial.println(LED3_NAMES[segment]);

    segment = (segment + 1) % NUM_SEGMENTS;
}
