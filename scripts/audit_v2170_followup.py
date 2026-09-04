#!/usr/bin/env python3
"""Verify v2.17 adds only guard/presentation hooks on top of the audited v2.16 Morphe core."""
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
        raise SystemExit("usage: audit_v2170_followup.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    overlay = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")

    # Native Morphe architecture remains authoritative.
    require(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "stock 1500-char batching")
    require(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "stock startup batch")
    require(translator, "pickNextBatch(batches, batchDone, timeMs)", "stock playhead ordering")
    require(translator, "splitBatchAtPlayhead", "stock seek split")
    require(fetcher, "return mergeIntoSentences(lines);", "stock source segmentation")
    forbid(translator, "openRouterParallelism", "no parallel OpenRouter replacement")
    forbid(fetcher, "SemanticClauseSplitter", "no custom source segmenter")

    # v2.17 additions.
    require(translator, "DubLanguageGuard.reason", "post-parse English leak guard")
    require(translator, "recordContentReject", "semantic failure telemetry")
    require(translator, "OPENROUTER-CARDINALITY", "exact cardinality diagnostics")
    require(vot, "SpanishStudyController.allowTts", "pre-TTS language guard")
    require(vot, "SpanishStudyController.onTtsWindow", "Morphe timing bridge")
    require(vot, "ttsEndVideoTimeMs = speakFromMs", "native effective TTS end remains timing source")
    require(controller, "translatedSnapshotsSuppressed", "snapshot dedupe diagnostics")
    require(controller, "sessionEpoch", "session epoch diagnostics")
    require(overlay, "findTranslatedIndex", "independent Spanish presentation timing")
    require(overlay, "setMaxLines(4)", "longer subtitle display capacity")

    print("v2.17.0 follow-up audit passed")


if __name__ == "__main__":
    main()
