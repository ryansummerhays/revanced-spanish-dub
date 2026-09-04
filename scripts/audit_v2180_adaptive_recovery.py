#!/usr/bin/env python3
"""Verify v2.18 removes the unbounded OpenRouter recovery loop without replacing Morphe core flow."""
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2180_adaptive_recovery.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")

    # Morphe remains authoritative for the normal path.
    require(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "stock 1500-char batching")
    require(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "stock startup batch")
    require(translator, "pickNextBatch(batches, batchDone, timeMs)", "stock playhead ordering")
    require(translator, "splitBatchAtPlayhead", "stock seek split")

    # The v2.17 deadlock path must be gone.
    forbid(translator, "retry same native Morphe batch failures=", "unbounded integrity retry loop")
    forbid(translator, "Math.min(15_000L, 1_000L <<", "exponential same-batch backoff")

    # Bounded recovery invariants.
    require(translator, "batch.subList(0, 1)", "first-slot isolation")
    require(translator, "batch.subList(1, failedSize)", "contiguous tail preservation")
    require(translator, "consecutiveOpenRouterTransportFailures == 1", "one transport retry")
    require(translator, "fallbackGoogleAfterOpenRouter", "bounded Google fallback")
    require(translator, "lastOpenRouterFailureWasIntegrity = isOpenRouterIntegrityFailure(ex)", "failure classification")
    require(translator, '"action=split-first failedBatchSize="', "split recovery diagnostics")
    require(translator, '"action=retry-transport-once batchSize="', "transport retry diagnostics")
    require(translator, '"action=google-fallback-success reason="', "fallback success diagnostics")

    print("v2.18.0 adaptive recovery audit passed")


if __name__ == "__main__":
    main()
