# UNO Q hardware reference

Condensed from the [UNO Q user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/).
Everything on this page refers to the **4 GB** variant.

## ⚠️ The headers are 3.3 V

This is the single most important fact about the board and the easiest way to
destroy it. The UNO Q has the UNO footprint and UNO shields will seat perfectly,
but the STM32U585 runs at **3.3 V logic**. Feeding a 5 V signal into a header pin
can damage the MCU.

Before plugging in any classic UNO shield:

- Check whether it drives signals *into* the UNO Q at 5 V. Output-only shields
  (relay boards, LED drivers) are usually fine; anything with buttons, sensors,
  or level-shifted outputs is not.
- Prefer the **Qwiic connector** for I²C peripherals. It is also 3.3 V only —
  do not attach 5 V Qwiic devices.
Community testing of common shields found: **prototyping shields** need their
power rail rewired to 3.3 V; **joystick shields** need their slide switch moved
to 3.3 V (and their 5 V I²C header avoided — use Qwiic); **LCD1602 keypad
shields** work for the display but need a ~3.9 kΩ resistor to clamp the button
ladder on A0. Rule of thumb: shields that only *receive* signals are usually
safe, shields that *drive* signals into the UNO Q need checking.

## Cooling

The QRB2210 is a phone-class SoC and gets warm under sustained load — vision
bricks, LLMs, or long compiles will heat-soak it. A bare board is fine for the
apps here; for anything running continuously, a stick-on aluminium heatsink (the
Raspberry Pi 4 kits fit) is the cheap fix, and any enclosure should be vented.

Establish your idle baseline early with `tests/run_checks.py` so you can tell
throttling from a software bug later. Idle sits in the high 30s °C.

## Qwiic and Modulino

The Qwiic connector (`Wire1`, 3.3 V only) is the least error-prone way to attach
sensors — no soldering, no level shifting. Arduino's **Modulino** nodes are
Qwiic-native with a first-party library:

```yaml
libraries:
  - Arduino_Modulino (0.7.0)
```

```cpp
Modulino.begin(Wire1);   // note Wire1, the Qwiic bus
```

SparkFun's Qwiic catalogue works too — same connector, same 3.3 V assumption.

## Power

| Input | Rating |
|---|---|
| USB-C | 5 VDC @ 3 A (15 W) — **use a real 3 A supply**, not a laptop port |
| `5V` pin | external +5 VDC |
| `VIN` pin | external +7–24 VDC |

Underpowering is the most common cause of "the board randomly reboots" and
"the Linux side is very slow". A quad-A53 with Wi-Fi up draws real current.

## Digital pins (STM32-controlled)

47 digital pins total; 22 on the UNO-style header, 25 on the JMISC connector.

| MCU pin | Arduino name | Function |
|---|---|---|
| PB7 | D0 / RX | GPIO / UART RX |
| PB6 | D1 / TX | GPIO / UART TX |
| PB3 | D2 | GPIO |
| PB0 | D3 | GPIO / OPAMP OUT / **PWM** |
| PA12 | D4 / FDCAN1_TX | GPIO / CAN TX |
| PA11 | D5 / FDCAN1_RX | GPIO / CAN RX / **PWM** |
| PB1 | D6 | GPIO / **PWM** |
| PB2 | D7 | GPIO |
| PB4 | D8 | GPIO |
| PB8 | D9 | GPIO / **PWM** |
| PB9 | D10 / SS | GPIO / SPI SS / **PWM** |
| PB15 | D11 / MOSI | GPIO / SPI MOSI / **PWM** |
| PB14 | D12 / MISO | GPIO / SPI MISO |
| PB13 | D13 / SCK | GPIO / SPI SCK |
| PA4 | D14 / DAC0 | GPIO / ADC / DAC |
| PA5 | D15 / DAC1 | GPIO / ADC / DAC |
| PA6 | D16 | GPIO / ADC / OPAMP IN+ |
| PA7 | D17 | GPIO / ADC / OPAMP IN− |
| PC1 | D18 / SDA2 (= A4) | GPIO / ADC / I²C SDA |
| PC0 | D19 / SCL2 (= A5) | GPIO / ADC / I²C SCL |
| PB11 | D20 / SDA | GPIO / I²C SDA (`Wire`) |
| PB10 | D21 / SCL | GPIO / I²C SCL (`Wire`) |

PWM is available on **D3, D5, D6, D9, D10, D11** only.

## Analog pins

A0–A5, 6 channels, ADC resolution selectable at **14 / 12 / 10 / 8 bits**:

```cpp
analogReadResolution(14);   // 0 – 16383
int v = analogRead(A0);
```

Default reference is 3.3 V; `analogReference()` also accepts `AR_INTERNAL1V5`
and `AR_INTERNAL2V5` among others. DAC output is available on D14/D15
(`DAC0`/`DAC1`).

## I²C — two separate buses

| Bus | Object | Pins | Notes |
|---|---|---|---|
| I²C1 | `Wire` | D20 (SDA) / D21 (SCL) | UNO-style header |
| I²C4 | `Wire1` | Qwiic connector | **3.3 V only**, Modulino nodes live here |

```cpp
Wire.begin();    // header bus
Wire1.begin();   // Qwiic bus
```

[`apps/05-i2c-scan`](../apps/05-i2c-scan) scans both and reports what it finds.

## LEDs

Four RGB LEDs. Two belong to Linux, two belong to the MCU. **All are active
low** — logic `0` turns a segment on.

### MPU-controlled (LED 1 and 2) — from Python or the shell

```python
from arduino.app_utils import Leds
Leds.set_led1_color(1, 0, 0)   # R, G, B — LED 1 red
Leds.set_led2_color(0, 0, 0)   # LED 2 off
```

Or straight through sysfs:

```bash
echo 1 | tee /sys/class/leds/red:user/brightness
```

| LED | Red | Green | Blue |
|---|---|---|---|
| 1 | `red:user` | `green:user` | `blue:user` |
| 2 | `red:panic` | `green:wlan` | `blue:bt` |

LED 2 doubles as a system-status indicator (kernel panic / WLAN / BT). You can
drive it, but it will fight the system for control.

### MCU-controlled (LED 3 and 4) — from a sketch

```cpp
pinMode(LED3_R, OUTPUT);
digitalWrite(LED3_R, LOW);   // ON  (active low)
digitalWrite(LED3_R, HIGH);  // OFF
```

Names: `LED3_R`, `LED3_G`, `LED3_B`, `LED4_R`, `LED4_G`, `LED4_B`.
`LED_BUILTIN` is also active low.

## Reserved resources — do not touch

The `arduino-router` service owns the physical link between the two processors:

- **Linux side:** `/dev/ttyHS1`
- **MCU side:** `Serial1`

Opening either in your own code breaks the Bridge. If you need the hardware
UART on the JDIGITAL connector, that is also `Serial1` — so on this board you
effectively choose between the Bridge and that UART, not both.

## Serial vs Monitor

Since UNO Q core **0.55.0**, plain `Serial.print()` works and shows up in the
App Lab console. The older `Monitor` object still works and is what the official
examples mostly use. New code should use `Serial`.

## Debug UART (JCTL connector)

Direct console to the SoC — bootloader and kernel logs, before SSH exists.
**1.8 V logic**; you need a 1.8 V USB-TTL adapter or you will damage the pin.

## Networking

```bash
sudo nmcli d wifi connect <SSID> password <PASSWORD>
nmcli device                 # find your interface name
sudo nmcli d disconnect wlan0
```

App Lab's Network Mode finds boards over **mDNS (UDP 5353)**. Corporate, guest,
and VPN networks routinely block it — the board can be fully online and still
not appear in the App Lab board list. SSH by IP still works.
