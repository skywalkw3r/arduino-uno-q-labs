"""Bring-up step 7 — camera and on-device object detection.

This is the first app that uses the QRB2210 for what it's actually for: the
model runs locally on the board, no cloud, no API key.

Everything here happens on the Linux side. There's no sketch — which is the
point. Once you've proved the MCU and the Bridge work, the Linux half of the
board is a normal Debian machine with accelerators attached.

Requires a camera. USB is the zero-friction option; CSI works via the JMEDIA
header. Swap the Camera() line below to match what you have.
"""

import logging
import time
from collections import Counter

from arduino.app_bricks.video_objectdetection import VideoObjectDetection
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Logger

logger = Logger("CameraObjects", level=logging.INFO)

CONFIDENCE_THRESHOLD = 0.5   # raise for fewer, more certain hits
REPORT_INTERVAL_S = 5.0

# Pick the line matching your camera and comment out the rest.
camera = Camera(resolution=(640, 480), fps=30)              # first available
# camera = Camera("usb:0", resolution=(640, 480), fps=30)   # explicit USB
# camera = Camera("csi:0", resolution=(640, 480), fps=30)   # CSI via JMEDIA
# camera = Camera("rtsp://<URL>", username="<USER>", password="<PASS>")

detector = VideoObjectDetection(
    camera=camera,
    confidence=CONFIDENCE_THRESHOLD,
    # debounce_sec collapses repeat detections of the same object. 0.0 reports
    # every frame — useful for measuring throughput, noisy for real use.
    debounce_sec=0.0,
)

seen = Counter()
best_confidence: dict[str, float] = {}
detection_events = 0
_last_report = time.monotonic()


def on_detections(detections: dict) -> None:
    """Called by the brick each time it finds something.

    Shape is {label: [{"confidence": float, ...}, ...]}.
    """
    global detection_events

    detection_events += 1
    for label, instances in detections.items():
        for instance in instances:
            confidence = instance.get("confidence", 0.0)
            seen[label] += 1
            if confidence > best_confidence.get(label, 0.0):
                best_confidence[label] = confidence


detector.on_detect_all(on_detections)


def loop() -> None:
    global _last_report, detection_events

    time.sleep(1.0)

    now = time.monotonic()
    elapsed = now - _last_report
    if elapsed < REPORT_INTERVAL_S:
        return
    _last_report = now

    if not seen:
        logger.info("No objects above %.0f%% confidence in the last %.0fs.",
                    CONFIDENCE_THRESHOLD * 100, elapsed)
        return

    logger.info("─" * 60)
    logger.info("Last %.0fs — %.1f detection events/sec", elapsed, detection_events / elapsed)
    for label, count in seen.most_common(10):
        logger.info("  %-18s x%-4d  best %.0f%%", label, count, best_confidence[label] * 100)
    logger.info("─" * 60)

    seen.clear()
    best_confidence.clear()
    detection_events = 0


logger.info("Starting detection at %.0f%% confidence. Hold something in front of the camera.",
            CONFIDENCE_THRESHOLD * 100)
App.run(user_loop=loop)
