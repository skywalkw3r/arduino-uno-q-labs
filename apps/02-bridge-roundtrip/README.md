# 02 — Bridge roundtrip

**Proves:** the MPU↔MCU RPC link works in both directions, and gives you a
latency baseline.
**Wiring:** none.

## Run it

Paste both files into a new App Lab app and Run.

## What you should see

`LED_BUILTIN` flickering, and a summary line every 20 replies:

```
n=  20  min 1.42 ms  mean 2.06 ms  p95 3.10 ms  max 4.88 ms  lost 0
n=  40  min 1.39 ms  mean 1.98 ms  p95 2.87 ms  max 5.02 ms  lost 0
```

**Record your numbers.** Single-digit milliseconds with `lost 0` is a healthy
link. What matters is that you know your own board's figure — later, when
something feels slow, you can tell whether the Bridge is the cause instead of
guessing.

## The pattern to steal

This is the smallest app that shows the shape every later app uses:

```cpp
void ping(unsigned long seq) {   // provide_safe handler
    pendingSeq = seq;            // set a flag
    pingPending = true;          // and return immediately
}

void loop() {
    if (!pingPending) return;
    pingPending = false;
    Bridge.notify("pong", pendingSeq);   // real work happens here
}
```

You **cannot** call `Bridge.notify()`, `Bridge.call()`, or `Serial.print()`
inside an RPC handler — starting a new RPC while answering one deadlocks the
link, and it presents as a total board hang. The handler sets a flag; `loop()`
does the work. See [docs/anatomy.md](../../docs/anatomy.md#the-two-rules).

## If it fails

**No pongs at all, `ping N timed out` repeating** — the Bridge isn't up:

```bash
systemctl status arduino-router
sudo systemctl restart arduino-router
journalctl -u arduino-router -f
```

Also confirm `Bridge.begin()` is in `setup()`. It's mandatory and fails
silently when missing.

**Latency in the hundreds of ms** — something else is saturating the link or the
CPU. Check `top`, and check thermals against your app 00 baseline.

**Occasional losses under load** — expected at high ping rates. Raise
`PING_INTERVAL_S` and see whether they disappear.
