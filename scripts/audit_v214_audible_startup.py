#!/usr/bin/env python3
from pathlib import Path
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    text = {
        "translator": (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8"),
        "vot": (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8"),
        "tts": (pkg / "TtsEngine.java").read_text(encoding="utf-8"),
        "prefetch": (pkg / "TtsPrefetcher.java").read_text(encoding="utf-8"),
        "controller": (study / "SpanishStudyController.java").read_text(encoding="utf-8"),
        "named": (study / "CaptionNamedSpeakerStore.java").read_text(encoding="utf-8"),
    }
    checks = [
        ("v2.14 diagnostics", "Spanish Dub Study v2.14.0 diagnostics" in text["controller"]),
        ("shared startup translation planner", "StartupTranslationPlanner.initialSegmentCount" in text["translator"]),
        ("Google gets first microbatch", "if (firstBatchAfterReposition)" in text["translator"] and "isOpenRouter && firstBatchAfterReposition" not in text["translator"]),
        ("late session primes speech", "primeSpeechBackends();" in text["vot"] and "SpanishStudyController.onSessionEnabled();" in text["vot"]),
        ("offline voice is genuinely local", "isNetworkConnectionRequired()" in text["vot"] and "TTS-FALLBACK" in text["vot"]),
        ("Edge stop invalidates generation", "playbackId++;" in text["tts"]),
        ("doomed uncached network synthesis skipped", "StartupSpeechPolicy.shouldStartNetwork" in text["vot"] and "network-skip index=" in text["vot"]),
        ("on-demand stale video guard", "stale-video audio discarded index=" in text["vot"]),
        ("prefetch stale video guard", "isCurrentVideo(videoId)" in text["prefetch"] and "stale-video audio discarded index=" in text["prefetch"]),
        ("shared Edge fallback circuit", "public static synchronized void noteEdgeSynthesisFailure" in text["vot"] and "VoiceOverTranslationPatch.noteEdgeSynthesisFailure" in text["prefetch"]),
        ("prefetch pauses during fallback", "VoiceOverTranslationPatch.isEdgeFallbackActive()" in text["prefetch"]),
        ("caption-named identity precedes acoustic identity", "CaptionNamedSpeakerStore.speakerIndexAt" in text["controller"]),
        ("named speakers remain conservative", "Bare >> markers remain boundary-only" in text["named"] or "Bare >> markers remain boundary-only".lower() in text["named"].lower()),
        ("diagnostics distinguish markers from identities", "captionSpeakerMarkers=" in text["controller"] and "captionNamedSpeakers=" in text["controller"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + name)
    if failed:
        raise SystemExit("v2.14 audit failed: " + ", ".join(failed))
    print(f"v2.14 audit passed: {len(checks)} invariants")


if __name__ == "__main__":
    main()
