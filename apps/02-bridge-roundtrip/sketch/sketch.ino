/*
 * Bring-up step 2 (MCU side) — echo a sequence number back to Python.
 *
 * Python calls ping(seq); we notify pong(seq) straight back. Python times the
 * gap. That gives you a real number for Bridge round-trip latency on your
 * board, which is the baseline you need before you can call anything "slow".
 *
 * NOTE THE SHAPE OF THIS CODE. It's the pattern every later app uses:
 *
 *   provide_safe handler  ->  sets a flag, returns immediately
 *   loop()                ->  does the work, sends the reply
 *
 * You cannot call Bridge.notify() (or Serial.print()) from inside an RPC
 * handler — starting a new RPC while answering one deadlocks the link. So the
 * handler does the absolute minimum and loop() does everything else.
 */

#include "Arduino_RouterBridge.h"

volatile bool pingPending = false;
volatile int pendingSeq = 0;

/* Runs in loop() context because it's registered with provide_safe().
   Still kept trivial: no printing, no Bridge calls, no Arduino API.

   The parameter MUST be `int`. An inbound RPC parameter typed `unsigned long`
   is rejected by the Bridge's type binding with

       Request 'ping' failed: Wrong type parameter in position: 0 (253)

   even though `unsigned long` is fine for values you send *out* via notify().
   Stick to int / bool / String / std::vector<int> for provide() parameters. */
void ping(int seq) {
    pendingSeq = seq;
    pingPending = true;
}

void setup() {
    Serial.begin(115200);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);  // active low: start off

    Bridge.begin();                  // mandatory
    Bridge.provide_safe("ping", ping);

    Serial.println("Bridge up, waiting for pings from Python.");
}

void loop() {
    if (!pingPending) {
        return;
    }
    pingPending = false;

    int seq = pendingSeq;

    // Blink so there's a physical sign the MCU is being reached, even if the
    // console is scrolling too fast to read.
    digitalWrite(LED_BUILTIN, seq % 2 == 0 ? LOW : HIGH);

    // Safe here: we're in loop(), not inside the RPC handler.
    Bridge.notify("pong", seq);
}
