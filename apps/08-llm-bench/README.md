# 08 — LLM bench

**Proves:** what on-device LLM inference actually costs on the QRB2210 — model
load time, time-to-first-token, and generation rate.
**Wiring:** none. **Storage:** the model is ~0.5–0.8 GB on disk.

This is the tool for answering "is a local-AI app realistic on this board?" with
a number instead of a guess.

## Prerequisite: download a model first (one time, in the GUI)

The `llm` brick runs [llama.cpp](https://github.com/ggerganov/llama.cpp) against
a model that must already be on disk. Your board *lists* models
(`arduino-app-cli model list`) but ships none of the LLMs downloaded:

```
llamacpp:gemma-3-1b-it-Q4_0    Gemma 3 1B      (~0.7 GB)
llamacpp:Qwen3.5-0.8B-Q4_0     Qwen 3.5 0.8B   (~0.5 GB)
```

On App Lab **0.12.1 there is no CLI command to download them** — `arduino-app-cli
model` only has `list` and `delete`. The download is a GUI action:

> App Lab → open this app → the `llm` brick's **AI model** tab → download
> **Gemma 3 1B** (or Qwen 0.8B).

Confirm it landed:

```bash
arduino-app-cli model list --exclude-builtin
```

(If you'd rather stay entirely on the CLI, see *Pure-CLI alternative* below.)

## Run it

Once the model is downloaded:

```bash
./scripts/app.sh start apps/08-llm-bench
./scripts/app.sh logs  apps/08-llm-bench
```

No sketch — it's a pure MPU app.

## What you should see

```
LLM benchmark — model: llamacpp:gemma-3-1b-it-Q4_0
Model ready in 8.3 s (download + load + warm-up)
[short] prompt: 61 chars
  run 2: TTFT 0.41s  gen 1.90s  47 chunks  212 chars  ~27.9 tok/s
[note-summary] prompt: 380 chars
  run 2: TTFT 0.88s  gen 6.10s  120 chunks  520 chars  ~21.3 tok/s
```

If instead you see `The model is listed but NOT downloaded`, do the GUI step
above first.

## Reading the numbers

- **Model ready** — one-time load into RAM (excludes the actual benchmark). The
  first ever run also downloads the weights, which is timed into this line.
- **TTFT** — time to first token. This is the latency a user *feels* before text
  starts appearing.
- **gen** — generation time after the first token.
- **tok/s** — throughput. **Estimated** as `chars / 4`, since a streamed "chunk"
  isn't guaranteed to be exactly one token; the raw chunk and char counts are
  printed so you can see the derivation. Treat it as ±20%.

Two runs per prompt: the first primes any cache, the second is what you'd feel in
an app.

## Switch models

Edit `MODEL` at the top of `python/main.py`, or pin it in `app.yaml`:

```yaml
bricks:
  - arduino:llm:
      model: llamacpp:Qwen3.5-0.8B-Q4_0
```

Qwen 0.8B is smaller and faster; Gemma 3 1B is a bit slower but generally better.

## Pure-CLI alternative: Ollama

If you want a model **and** its download driven entirely from the command line,
Ollama is the cleaner path — and `ollama run --verbose` prints an authoritative
eval rate (no `chars/4` estimate):

```bash
# one-time install needs sudo (Ollama's installer wants root):
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:1b
ollama run gemma3:1b --verbose "Summarise: <paste a note>"
```

The `--verbose` output ends with `eval rate: N tokens/s` — the real number.

Caveat: this is a **separate runtime** from the App Lab `llm` brick, so it
measures the board's raw llama.cpp speed, not the brick's. For "what will my
App Lab app feel like," use the brick benchmark above; for "how fast is this
board at local LLM inference," Ollama is fine and simpler. There's an
[Installing Ollama on UNO Q](https://projecthub.arduino.cc) Project Hub tutorial.

## Why this matters for a note-taking app

A 1B model at ~20–30 tok/s (rough CPU-only ballpark; measure yours) summarises a
short note in a few seconds — fine for "clean up this dictation" or "extract
action items," sluggish for long generation. The board has no NPU device node
exposed for the faster `genie:` runtime by default, so these small models run on
the four Cortex-A53 cores via llama.cpp. Budget disk and RAM per the
[Arduino guide](https://blog.arduino.cc/2026/06/18/running-local-llms-on-the-arduino-uno-q-board-a-practical-guide/):
a 1B Q4 model is ~600–700 MB on disk and ~1 GB RAM at runtime.
