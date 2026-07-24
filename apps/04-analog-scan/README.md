# 04 — Analog scan

**Proves:** the 14-bit ADC works on all six analog inputs, and that structured
data (a list) crosses the Bridge correctly.
**Wiring:** 10 kΩ potentiometer (optional).

## ⚠️ Use the 3.3V pin

The ADC reference is 3.3 V and the pins are not 5 V tolerant. Wiring a pot to
the 5V pin will read full scale and stress the input.

## Wiring

```
3.3V ──┬── pot leg 1
       │
A0  ───┴── pot wiper
GND ────── pot leg 3
```

Unconnected channels will show noise. That's correct behaviour for a floating
input — worth seeing once so you recognise it later.

## Run it

Paste both files into a new App Lab app and Run.

## What you should see

```
ADC: 6 channels, full scale 16383 counts, Vref 3.30 V (0.201 mV/count)
────────────────────────────────────────────────────────────────────────
A0   8192 cnt  1.650 V   min  8180  max  8203  spread   23
A1   4021 cnt  0.810 V   min  3902  max  4150  spread  248
...
A0 |████████████████████·····················| 1.650 V
```

Turn the pot: A0 should sweep smoothly from ~0.000 V to ~3.300 V and the bar
should track it.

## The 14-bit trap

Every other Arduino gives you 0–1023. This board defaults differently and can do
14 bits, so the sketch sets it explicitly:

```cpp
analogReadResolution(14);   // full scale is now 16383, not 1023
```

If your readings look 16× too small, that's the bug. Resolution is selectable at
14 / 12 / 10 / 8 bits.

## Structured data across the Bridge

All six channels travel as one message:

```cpp
std::vector<int> samples;      // sketch side
Bridge.notify("adc_samples", samples);
```

```python
def adc_samples(samples: list[int]):   # Python side
    ...
```

`std::vector<int>` ↔ `list[int]` is the mapping to remember. Six values in one
notify beats six separate calls.

## If it fails

- **Everything reads full scale** — you wired the pot to 5V, or the input is
  floating high.
- **Values look ~16× too small** — `analogReadResolution(14)` didn't take
  effect; check it's in `setup()`.
- **`No samples from the sketch yet`** — the Bridge isn't up. Run app 02.
- **A4/A5 behave oddly** — they're shared with I²C (D18/D19, SDA2/SCL2). If
  something is on that bus it will fight the ADC.
