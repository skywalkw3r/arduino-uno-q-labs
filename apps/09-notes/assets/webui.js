// Minimal WebUI client wrapper — same API as the brick's arduino.js
// (on_connect / on_disconnect / on_message / send_message), but it connects to
// the page's own origin instead of a hardcoded http:// URL.
//
// That one change is what makes HTTPS work: over an https page socket.io
// upgrades to wss:// automatically, with no mixed-content block. The vendored
// arduino.js hardcodes http://, so it can't be used under TLS.
//
// socket.io itself still comes from libs/socket.io.min.js.

class WebUI {
  #socket;

  constructor(options = {}) {
    // No URL argument → socket.io uses the serving origin and matching
    // protocol (ws for http, wss for https).
    this.#socket = io(window.location.origin, options);
  }

  on_connect(callback) {
    this.#socket.on('connect', callback);
  }

  on_disconnect(callback) {
    this.#socket.on('disconnect', callback);
  }

  on_message(eventName, callback) {
    this.#socket.on(eventName, callback);
  }

  send_message(eventName, data) {
    this.#socket.emit(eventName, data ?? {});
  }
}
