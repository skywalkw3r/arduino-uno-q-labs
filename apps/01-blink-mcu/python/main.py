"""Bring-up step 1 — Python side is intentionally empty.

All the logic for this app lives in sketch/sketch.ino and runs on the STM32.
App.run() exists only so App Lab has something to start and stop, which is what
keeps the sketch loaded and running.
"""

from arduino.app_utils import App

App.run()
