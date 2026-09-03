#!/usr/bin/env python3
"""Build-time invariants for v2.13 English-source and speaker-turn safety."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

paths = {
    "fetcher": votpkg / "TranscriptFetcher.java",
    "controller": study / "SpanishStudyController.java",
    "timing": study / "SourceCaptionTimingStore.java",
    "planner": study / "SpeechUnitPlanner.java",
    "track": study / "CaptionTrackPreference.java",
    "turns": study / "CaptionSpeakerTurnStore.java",
}
text = {k: p.read_text(encoding="utf-8") for k, p in paths.items()}

checks = [
    ("v2.13 diagnostics", "Spanish Dub Study v2.13.0 diagnostics" in text["controller"]),
    ("English-first policy exposed", "sourceTrackPolicy=english-first" in text["controller"]),
    ("English source ranked before target", "CaptionTrackPreference.rank" in text["fetcher"]
        and 'if ("en".equals(lang)) return nonGemini ? 0 : 10;' in text["track"]),
    ("fallback source diagnosed", "English source unavailable; fallback caption lang=" in text["fetcher"]),
    ("speaker turn store reset", "CaptionSpeakerTurnStore.beginTranscript()" in text["fetcher"]),
    ("speaker turn marker retained", "CaptionSpeakerTurnStore.markFromChunk" in text["fetcher"]),
    ("marker removal preserves word gap", '.replace(\">>\", \" \")' in text["fetcher"]),
    ("sentence merge respects speaker turns",
        text["fetcher"].count("CaptionSpeakerTurnStore.isTurnStartNear(lines.get(i + 1).startMs)") == 2),
    ("timing turns become hard pauses", "EXPLICIT_SPEAKER_PAUSE_MS" in text["timing"]
        and "CaptionSpeakerTurnStore.hasBoundaryBetween" in text["timing"]),
    ("speech units carry speaker boundary", "CaptionSpeakerTurnStore.isTurnStartNear(segment.startMs)" in text["fetcher"]),
    ("planner never crosses speaker boundary", "if (b.hardBoundaryBefore()) return false;" in text["planner"]),
    ("speaker identity remains honest", "speakerIdentityMode=pending-local-audio-clustering" in text["controller"]),
    ("cloud analysis remains disabled", "cloudAnalysis=disabled" in text["controller"]),
]

failed = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + " | " + name)
    if not ok:
        failed.append(name)

if failed:
    raise SystemExit("v2.13.0 audit failed: " + ", ".join(failed))
print(f"v2.13.0 audit passed ({len(checks)} invariants)")
