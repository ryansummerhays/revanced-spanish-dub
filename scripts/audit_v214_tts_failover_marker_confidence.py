#!/usr/bin/env python3
"""Audit v2.14.0 reliability and conservative speaker-marker integration."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v214_tts_failover_marker_confidence.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    files = {
        "vot": (votpkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8"),
        "prefetch": (votpkg / "TtsPrefetcher.java").read_text(encoding="utf-8"),
        "translator": (votpkg / "TranscriptTranslator.java").read_text(encoding="utf-8"),
        "fetcher": (votpkg / "TranscriptFetcher.java").read_text(encoding="utf-8"),
        "controller": (study / "SpanishStudyController.java").read_text(encoding="utf-8"),
        "markers": (study / "CaptionSpeakerTurnStore.java").read_text(encoding="utf-8"),
        "policy": (study / "EdgeReliabilityPolicy.java").read_text(encoding="utf-8"),
    }

    checks = [
        ("v2.14 diagnostics label", "Spanish Dub Study v2.14.0 diagnostics" in files["controller"]),
        ("native failover policy exposed", "ttsFailover=edge-prefetched-native-offline-active-miss" in files["controller"]),
        ("native TTS warmed on session", "SpanishStudyController.onSessionEnabled();\n        ensureTts();" in files["vot"]),
        ("native TTS warmed on active video", "warm the local/native reliability floor" in files["vot"]),
        ("active Edge cache miss fails forward", "useNativeForActiveCacheMiss" in files["vot"]
            and "edge-cache-miss" in files["vot"]),
        ("fallback requires offline Spanish voice", "isNetworkConnectionRequired()" in files["vot"]
            and "no-offline-spanish-voice" in files["vot"]),
        ("Edge failure can fail forward", "edge-failure-" in files["vot"]),
        ("prefetch failures tracked", "failedAttemptsByIndex" in files["prefetch"]),
        ("poisoned prefetch slot suppressed", "suppressed index=" in files["prefetch"]
            and "isPrefetchSuppressed(next.index)" in files["prefetch"]),
        ("first Google slice capped", "GOOGLE_FIRST_BATCH_CHARS = 900" in files["translator"]
            and "isOpenRouter ? OPENROUTER_FIRST_BATCH_CHARS : GOOGLE_FIRST_BATCH_CHARS" in files["translator"]),
        ("raw markers separated from speaker turns", "ALL_MARKERS_MS" in files["markers"]
            and "HARD_TURN_STARTS_MS" in files["markers"]
            and "markerCount()" in files["markers"]),
        ("bare markers no longer hard speaker boundaries", "hasExplicitSpeakerLabel" in files["markers"]
            and "HARD_TURN_STARTS_MS.add" in files["markers"]),
        ("phrase diagnostics separate cue and turn counts", "cueMarkers=" in files["fetcher"]
            and "speakerTurns=" in files["fetcher"]),
        ("speaker boundary mode is confidence-labelled", "explicit-labelled-caption-turns-only" in files["controller"]),
        ("policy helper copied into extension", "PREFETCH_FAILURES_BEFORE_SUPPRESS = 3" in files["policy"]),
    ]

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + name)
    if failed:
        raise SystemExit("v2.14 audit failed: " + ", ".join(failed))
    print(f"v2.14 audit passed: {len(checks)} invariants")


if __name__ == "__main__":
    main()
