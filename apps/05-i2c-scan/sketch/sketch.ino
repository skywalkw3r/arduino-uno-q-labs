/*
 * Bring-up step 5 (MCU side) — scan both I2C buses.
 *
 * The UNO Q has TWO separate I2C buses and confusing them is the single most
 * common reason a Qwiic sensor "doesn't work":
 *
 *   Wire   -> I2C1, D20 (SDA) / D21 (SCL), the UNO-style header
 *   Wire1  -> I2C4, the Qwiic connector — this is where Modulino nodes live
 *
 * So we scan both and report which bus each address was found on.
 *
 * ⚠️ The Qwiic connector is 3.3 V only.
 */

#include "Arduino_RouterBridge.h"
#include <Wire.h>
#include <vector>

// 0x00-0x07 and 0x78-0x7F are reserved by the I2C spec, so a 7-bit scan only
// needs to cover 0x08..0x77.
const uint8_t FIRST_ADDR = 0x08;
const uint8_t LAST_ADDR = 0x77;

volatile bool scanRequested = false;

// provide_safe handler: sets a flag and returns. The scan itself hammers Wire
// and then calls Bridge.notify() — neither is safe from inside an RPC handler,
// so all of it happens in loop() instead.
void request_scan() {
    scanRequested = true;
}

// Returns every responding address on one bus.
std::vector<int> scanBus(TwoWire &bus) {
    std::vector<int> found;
    for (uint8_t addr = FIRST_ADDR; addr <= LAST_ADDR; addr++) {
        bus.beginTransmission(addr);
        // endTransmission() returns 0 only when a device ACKed the address.
        if (bus.endTransmission() == 0) {
            found.push_back(addr);
        }
    }
    return found;
}

void setup() {
    Serial.begin(115200);

    Wire.begin();   // header bus  (D20/D21)
    Wire1.begin();  // Qwiic bus   (I2C4)

    Bridge.begin();
    Bridge.provide_safe("request_scan", request_scan);

    Serial.println("I2C scanner ready — waiting for Python to request a scan.");
}

void loop() {
    if (!scanRequested) {
        return;
    }
    scanRequested = false;

    // Safe here: we're in loop() context, not inside the RPC handler.
    std::vector<int> headerDevices = scanBus(Wire);
    std::vector<int> qwiicDevices = scanBus(Wire1);

    Bridge.notify("scan_result", headerDevices, qwiicDevices);
}
