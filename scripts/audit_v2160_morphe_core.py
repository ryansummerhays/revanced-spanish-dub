#!/usr/bin/env python3
"""Fail if v2.16 stops piggybacking on Morphe's native VOT architecture."""
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
        raise SystemExit("usage: audit_v2160_morphe_core.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    tts = (pkg / "TtsEngine.java").read_text(encoding="utf-8")
    prefetch = (pkg / "TtsPrefetcher.java").read_text(encoding="utf-8")
    cache = (pkg / "TtsCache.java").read_text(encoding="utf-8")
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")

    # Morphe translation architecture must remain native.
    require(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "stock 1500-char OpenRouter batches")
    require(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "stock small first batch")
    require(translator, "splitByCharBudget(segments, maxBatchChars)", "stock character-budget batching")
    require(translator, "pickNextBatch(batches, batchDone, timeMs)", "stock playhead-driven request ordering")
    require(translator, "splitBatchAtPlayhead", "stock seek/playhead splitting")
    require(translator, "capFirstBatch", "stock startup batch cap")
    forbid(translator, "OPENROUTER-PARALLEL", "no custom parallel OpenRouter splitter")
    forbid(translator, "openRouterParallelism", "no custom OpenRouter parallelism")
    forbid(translator, "VIDEO-SPECIFIC CONTEXT", "no repeated custom video-context prompt")
    forbid(translator, "[slot=", "no slot-duration prompt metadata")

    # Morphe segmentation constants must remain untouched.
    require(fetcher, "MAX_SENTENCE_CHARS = 300", "stock punctuated sentence cap")
    require(fetcher, "MIN_SEGMENT_DURATION_MS = 2_000", "stock minimum segment duration")
    require(fetcher, "MAX_UNPUNCTUATED_CHARS = 200", "stock unpunctuated sentence cap")
    require(fetcher, "return mergeIntoSentences(lines);", "stock sentence segmenter output")
    forbid(fetcher, "SemanticClauseSplitter", "no custom semantic re-segmentation")
    forbid(fetcher, "splitIntoStudyClauses", "no subtitle-driven source splitting")

    # Morphe TTS/cache/prefetch architecture must remain native.
    require(tts, "private SSLSocket persistentSocket", "stock persistent Edge WebSocket")
    require(tts, "SEGMENT_START_END_MAX_MOVEMENT_FROM_ORIGINAL_MS = 4000", "stock playback-window adjustment")
    require(tts, "adjustPlaybackTimes", "stock duration-aware timing adjustment")
    require(prefetch, "DISTANCE_IMMEDIATE_MS = 30_000", "stock near-playhead TTS prefetch tier")
    require(prefetch, "DISTANCE_NEAR_MS      = 60_000", "stock 60-second TTS prefetch tier")
    require(prefetch, "BACKOFF_MAX_MS      = 60_000", "stock Edge error backoff")
    require(prefetch, "!Settings.VOT_SESSION_ENABLED.get()", "stock TTS prefetch session gate")
    require(cache, "Utils.createSizeRestrictedMap(1000)", "stock bounded TTS cache")
    forbid(vot, "TTS-FALLBACK", "no automatic Edge-to-system fallback state machine")

    # Our additions must be present and isolated.
    require(vot, "TranscriptTranslator.requestAbort();", "hard provider stop on VOT off")
    require(vot, "SpanishStudyController.onVideoTimeChanged", "subtitle observer hook")
    require(translator, "OpenRouterOutputGuard", "strict OpenRouter parser")
    require(translator, "OpenRouterBudget.maxOutputTokens", "safe output allowance")
    require(translator, "OpenRouterTelemetry", "actual OpenRouter usage telemetry")
    require(translator, "DubTextSanitizer", "provider-independent protocol sanitizer")

    print("v2.16.0 Morphe-core audit passed")


if __name__ == "__main__":
    main()
