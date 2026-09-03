#!/usr/bin/env python3
"""Build-time invariants for Spanish Dub Study v2.9.0."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

files = {
    "controller": study / "SpanishStudyController.java",
    "speaker": study / "GeminiSpeakerDiarizationSidecar.java",
    "ground": study / "GeminiVideoGroundingSidecar.java",
    "gemini": study / "GeminiTranslator.java",
    "sheet": study / "SpanishStudySheet.java",
    "picker": votpkg / "VotBottomSheet.java",
    "translator": votpkg / "TranscriptTranslator.java",
    "vot": votpkg / "VoiceOverTranslationPatch.java",
}
text = {k: p.read_text(encoding="utf-8") for k, p in files.items()}

checks = [
    ("diagnostics version", "Spanish Dub Study v2.9.0 diagnostics" in text["controller"]),
    ("live subtitle refresh", "onVisualSettingChanged" in text["controller"]),
    ("live speaker toggle", "onSpeakerRecognitionSettingChanged" in text["controller"]),
    ("provider-safe Gemini setup", "configureGeminiForTranslation" in text["controller"] and "configureGeminiForTranslation" in text["picker"]),
    ("actual provider telemetry", 'record("PROVIDER","text=' in text["translator"]),
    ("speaker key gate", "geminiApiKey(context).trim().isEmpty()" in text["speaker"]),
    ("speaker independent from text provider", "SpanishStudyPrefs.geminiEnabled(context)" not in text["speaker"]),
    ("grounding remains Gemini-translation scoped", "SpanishStudyPrefs.geminiEnabled(context)" in text["ground"]),
    ("external provider reconciliation", "external provider change detected" in text["gemini"]),
    ("TTS late-fragment recovery", "audibleFraction<0.45f" in text["vot"] and "late-skip index=" in text["vot"]),
    ("subtitle switches refresh immediately", "setShowSubtitles(activity,checked);SpanishStudyController.onVisualSettingChanged()" in text["sheet"]),
    ("speaker switch schedules immediately", "onSpeakerRecognitionSettingChanged(checked)" in text["sheet"]),
    ("provider scope is explained", "normal Translation provider setting is authoritative" in text["sheet"]),
]

failed = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + " | " + name)
    if not ok:
        failed.append(name)

if failed:
    raise SystemExit("v2.9.0 pipeline audit failed: " + ", ".join(failed))
print(f"v2.9.0 pipeline audit passed ({len(checks)} invariants)")
