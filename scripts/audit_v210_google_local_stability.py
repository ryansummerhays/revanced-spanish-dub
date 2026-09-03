#!/usr/bin/env python3
"""Build-time invariants for Spanish Dub Study v2.10.0 stable baseline."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

files = {
    "controller": study / "SpanishStudyController.java",
    "gemini": study / "GeminiTranslator.java",
    "ground": study / "GeminiVideoGroundingSidecar.java",
    "speaker": study / "GeminiSpeakerDiarizationSidecar.java",
    "translator": votpkg / "TranscriptTranslator.java",
    "tts": votpkg / "TtsEngine.java",
    "prefetcher": votpkg / "TtsPrefetcher.java",
}
text = {k: p.read_text(encoding="utf-8") for k, p in files.items()}

checks = [
    ("v2.10 diagnostics", "Spanish Dub Study v2.10.0 diagnostics" in text["controller"]),
    ("effective Google-only translator", "String service = TRANSLATION_SERVICE_GOOGLE" in text["translator"]),
    ("Gemini text hard disabled", "public static boolean isEnabled()" in text["gemini"] and "return false;" in text["gemini"]),
    ("Gemini grounding hard disabled", "v2.10 stable baseline: media grounding" in text["ground"] and "if (true) return;" in text["ground"]),
    ("Gemini speaker hard disabled", "no remote speaker diarization" in text["speaker"] and "if (true) return;" in text["speaker"]),
    ("diagnostics declare zero Gemini runtime", "geminiRuntime=disabled-in-v2.10" in text["controller"]),
    ("speaker backend future-local", "disabled-pending-local-audio-pipeline" in text["controller"]),
    ("bounded Edge timeout", "READ_TIMEOUT_MS    = 8_000" in text["tts"]),
    ("prefetch failure cooldown", "FAILED_SEGMENT_COOLDOWN_MS = 25_000L" in text["prefetcher"]),
    ("active cooldown skip", "!isPrefetchCoolingDown(i)" in text["prefetcher"]),
    ("prefetch cooldown diagnostics", 'record("TTS-PREFETCH", "cooldown index="' in text["prefetcher"]),
]

failed=[]
for name,ok in checks:
    print(("PASS" if ok else "FAIL")+" | "+name)
    if not ok: failed.append(name)
if failed:
    raise SystemExit("v2.10 audit failed: "+", ".join(failed))
print(f"v2.10 audit passed ({len(checks)} invariants)")
