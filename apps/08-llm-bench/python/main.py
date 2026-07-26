"""Benchmark a local LLM on the UNO Q.

Answers the only question you can't answer without running it: how fast is
on-device inference on this board, really? Reports model load time, time to
first token (TTFT), and generation rate for a few prompt sizes — including a
realistic note-summarisation task, since that's what prompted this.

Everything runs on the Qualcomm MPU via the `llm` brick (llama.cpp under the
hood). No sketch, no network, no cloud.

Pick the model with the MODEL env var, or edit MODEL below. Your board's
registered models come from `arduino-app-cli model list`; the two small local
ones are:

    llamacpp:gemma-3-1b-it-Q4_0    (~0.8 GB)   <- default here
    llamacpp:Qwen3.5-0.8B-Q4_0     (~0.5 GB)

The first run downloads the model if it isn't on disk yet — that download is
timed separately and excluded from the inference numbers.

Token counts from a streaming API are approximate: the brick yields text
chunks, not guaranteed one-token-each. We report the raw chunk count, the
character count, and a tokens estimate (chars / 4, the usual rule of thumb) so
the numbers stay honest and you can see how they were derived.
"""

import logging
import os
import time

from arduino.app_utils import App, Logger
from arduino.app_bricks.llm import LargeLanguageModel

logger = Logger("LLMBench", level=logging.INFO)

MODEL = os.environ.get("MODEL", "llamacpp:gemma-3-1b-it-Q4_0")

# Prompts chosen to sweep from "quick reply" to "real note-taking workload".
PROMPTS = [
    ("short", "Reply with exactly one short sentence: what is edge AI?"),
    (
        "note-summary",
        "Summarise the following note in two bullet points and list any action "
        "items:\n\n"
        "Met with Sam about the Q3 rollout. We agreed to push the beta to the "
        "14th because the auth migration slipped. I need to email the support "
        "team about the new timeline, and Sam will update the status page. Also "
        "we should revisit the rate-limiting config before launch — it bit us "
        "last time.",
    ),
]

CHARS_PER_TOKEN = 4  # rough industry heuristic, only for the estimate column


def est_tokens(chars: int) -> float:
    return chars / CHARS_PER_TOKEN


def run_once(llm: LargeLanguageModel, prompt: str) -> dict:
    """Stream one completion, timing first-token and total generation."""
    start = time.monotonic()
    first_token_at = None
    chunks = 0
    chars = 0

    for chunk in llm.chat_stream(prompt):
        if first_token_at is None:
            first_token_at = time.monotonic()
        chunks += 1
        chars += len(chunk)

    end = time.monotonic()
    if first_token_at is None:
        # Model produced nothing — surface it rather than dividing by zero.
        return {"empty": True, "total_s": end - start}

    gen_s = end - first_token_at
    return {
        "empty": False,
        "ttft_s": first_token_at - start,
        "gen_s": gen_s,
        "total_s": end - start,
        "chunks": chunks,
        "chars": chars,
        "chunks_per_s": chunks / gen_s if gen_s > 0 else 0.0,
        "est_tok_per_s": est_tokens(chars) / gen_s if gen_s > 0 else 0.0,
    }


def bench() -> None:
    logger.info("=" * 64)
    logger.info("LLM benchmark — model: %s", MODEL)
    logger.info("=" * 64)

    # Construction may kick off a model download on first use. Time it, but keep
    # it out of the inference numbers.
    logger.info("Loading model (first run downloads it — can take minutes)...")
    load_start = time.monotonic()
    try:
        llm = LargeLanguageModel(model=MODEL)
        # A tiny warm-up call forces weights into RAM so the real runs measure
        # steady-state inference, not one-time load cost.
        for _ in llm.chat_stream("Say OK."):
            pass
    except Exception as exc:
        logger.error("Could not load model %s: %s", MODEL, exc)
        if "not found" in str(exc).lower():
            # The model is registered but its weights aren't on disk yet. On
            # App Lab 0.12.1 there is no CLI to fetch them — the download is a
            # GUI action. Say so plainly instead of looping on a 400.
            logger.error("")
            logger.error("The model is listed but NOT downloaded. Download it once via the")
            logger.error("App Lab GUI: open this app's `llm` brick -> 'AI model' tab -> download")
            logger.error("'%s'. Then rerun this benchmark from the CLI.", MODEL)
            logger.error("Confirm it's present with:  arduino-app-cli model list")
        raise StopIteration
    load_s = time.monotonic() - load_start
    logger.info("Model ready in %.1f s (download + load + warm-up)", load_s)
    logger.info("-" * 64)

    for name, prompt in PROMPTS:
        logger.info("[%s] prompt: %d chars", name, len(prompt))
        # Two runs: the first primes any prompt cache, the second is the number
        # you'd actually feel in an app.
        result = {}
        for i in range(2):
            result = run_once(llm, prompt)
            if result["empty"]:
                logger.warning("  run %d produced no output (%.1fs)", i + 1, result["total_s"])
                continue
            logger.info(
                "  run %d: TTFT %.2fs  gen %.2fs  %d chunks  %d chars  ~%.1f tok/s",
                i + 1,
                result["ttft_s"],
                result["gen_s"],
                result["chunks"],
                result["chars"],
                result["est_tok_per_s"],
            )
        logger.info("-" * 64)

    logger.info("Done. 'tok/s' is estimated from chars/%d — see the header note.", CHARS_PER_TOKEN)
    logger.info("Rerun with a different model:  MODEL=llamacpp:Qwen3.5-0.8B-Q4_0")
    raise StopIteration  # one-shot: stop the user loop after the benchmark


App.run(user_loop=bench)
