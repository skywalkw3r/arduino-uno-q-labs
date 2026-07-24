# 07 — Camera objects

**Proves:** the camera pipeline and on-device inference work.
**Wiring:** a camera. USB is easiest; CSI goes on the JMEDIA header.

This is the first app that uses the QRB2210 for what you actually bought it for.
The model runs **locally** — no cloud, no API key, no network needed.

## Run it

Paste `python/main.py` into a new App Lab app, and add the brick in app settings:

```yaml
bricks:
  - arduino:video_object_detection
```

There's no sketch, and that's the point: once the MCU and Bridge are proven, the
Linux side is just Debian with accelerators bolted on.

First run downloads the model, so give it a minute.

## Pick your camera

Edit the `Camera(...)` line:

```python
camera = Camera(resolution=(640, 480), fps=30)            # first available
camera = Camera("usb:0", resolution=(640, 480), fps=30)   # explicit USB
camera = Camera("csi:0", resolution=(640, 480), fps=30)   # CSI via JMEDIA
camera = Camera("rtsp://<URL>", username="...", password="...")
```

## What you should see

```
────────────────────────────────────────────────────────────
Last 5s — 12.4 detection events/sec
  person             x62    best 94%
  cup                x18    best 71%
  keyboard           x9     best 58%
────────────────────────────────────────────────────────────
```

Hold a few objects in front of the camera. The detection rate is a rough proxy
for inference throughput — **note it, and note the board's temperature.** This
is the workload that will make the SoC hot; compare against your app 00 thermal
baseline and see [docs/hardware.md](../../docs/hardware.md#cooling).

## Tuning

- **`CONFIDENCE_THRESHOLD`** — 0.5 is a reasonable default. Raise to ~0.7 for
  fewer false positives.
- **`debounce_sec`** — 0.0 reports every frame, which is what you want for
  measuring throughput and wrong for real use. Set 1.0+ to collapse repeats of
  the same object into one event.
- **Resolution** — dropping to 320×240 buys frame rate.

## Other bricks worth trying next

Same shape, different brick — swap the import and the constructor:

| Brick | Does |
|---|---|
| `arduino:image_classification` | classify a whole frame instead of locating objects |
| `arduino:keyword_spotting` | wake words from the microphone |
| `arduino:asr` / `arduino:tts` | speech to text, text to speech |
| `arduino:llm` | a local language model |
| `arduino:motion_detection` | IMU gestures (pairs with Modulino Movement) |
| `arduino:dbstorage_tsstore` | time-series storage for logging apps |
| `arduino:telegram_bot` | push alerts off the board |

The full set with worked examples is in
[arduino/app-bricks-examples](https://github.com/arduino/app-bricks-examples).

## If it fails

- **No camera found** — check `ls /dev/video*` over SSH. USB cameras should
  enumerate immediately; try a different port or a powered hub.
- **First run seems hung** — it's downloading the model. Give it a minute and
  watch the console.
- **Very low detection rate** — check thermals; a hot SoC throttles hard. Lower
  the resolution.
- **Import error on the brick** — the brick isn't declared in `app.yaml`, or
  App Lab hasn't installed it yet.
