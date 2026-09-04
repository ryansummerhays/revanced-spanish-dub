#!/usr/bin/env python3
"""Static integration audit for v2.15.0 realtime/context/provenance changes."""
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v215_realtime_context.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    files = {
        "fetcher": (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8"),
        "translator": (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8"),
        "vot": (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8"),
        "controller": (study / "SpanishStudyController.java").read_text(encoding="utf-8"),
        "sheet": (study / "SpanishStudySheet.java").read_text(encoding="utf-8"),
    }
    need(files["fetcher"], "VideoTranslationContext.addRawCue", "raw cue preservation")
    need(files["fetcher"], "CaptionTextRepair.RepairResult", "local boundary repair")
    need(files["translator"], "RealtimeTranslationPlanner.MAX_BATCH_CHARS", "hard realtime char cap")
    need(files["translator"], "capRealtimeBatch", "hard realtime event cap")
    need(files["translator"], "Executors.newFixedThreadPool(2)", "two-way OpenRouter concurrency")
    need(files["translator"], "VideoTranslationContext.contextFor", "video-specific provider context")
    need(files["translator"], "Silently repair only obvious English ASR/punctuation mistakes", "implicit ASR repair")
    need(files["translator"], "slot=", "duration-aware translation")
    need(files["translator"], "OPENROUTER-REQ", "subrequest telemetry")
    need(files["translator"], "TRANSLATION-READY", "streamed translation provenance")
    need(files["translator"], "Never run applyBatch() across the", "translated-slots-only streaming publication")
    need(files["controller"], "TTS-SOURCE", "TTS provenance telemetry")
    need(files["controller"], "backgroundTranslationActive=", "truthful loading diagnostics")
    need(files["controller"], "Spanish Dub Study v2.15.0 diagnostics", "diagnostic version")
    need(files["controller"], "rawCaptionCues=", "raw cue count diagnostics")
    need(files["vot"], "SCHEDULER", "scheduler stall telemetry")
    need(files["sheet"], "Translation provider", "authoritative provider UI")
    need(files["sheet"], "No separate full-video AI analysis", "context cost explanation")
    if "Gemini settings" in files["sheet"]:
        raise RuntimeError("obsolete Gemini-specific translation row remains in study sheet")
    print("v2.15.0 realtime/context/provenance audit OK")


if __name__ == "__main__":
    main()
