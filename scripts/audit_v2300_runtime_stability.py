#!/usr/bin/env python3
"""Static integration audit for Spanish Dub Study v2.30."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2300_runtime_stability.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
files = {
    "translator": pkg / "TranscriptTranslator.java",
    "vot": pkg / "VoiceOverTranslationPatch.java",
    "prefetch": pkg / "TtsPrefetcher.java",
    "cache": pkg / "TtsCache.java",
    "subtitle": study / "SpanishSubtitleOverlay.java",
    "controller": study / "SpanishStudyController.java",
    "speaker": study / "LocalSpeakerDiarizer.java",
    "language": study / "DubLanguageGuard.java",
    "output": study / "OpenRouterOutputGuard.java",
}
for name, path in files.items():
    if not path.is_file():
        raise SystemExit(f"missing {name}: {path}")
texts = {k: p.read_text(encoding="utf-8") for k, p in files.items()}

checks = [
    ("unique-slot parser installed", "boolean[] matchedSlots" in texts["translator"]),
    ("contiguous OpenRouter prefix used", "while (contiguous < segmentSize && matchedSlots[contiguous])" in texts["translator"]),
    ("stream mixed-language guard", "stream guard withheld slot=" in texts["translator"]),
    ("singleton language repair", "action=google-singleton-fallback" in texts["translator"]),
    ("strict output guard installed", "OpenRouterOutputGuard.parseNumberedLine" in texts["translator"]),
    ("prefetch in-flight tracking", "awaitMatchingFetch" in texts["prefetch"]),
    ("on-demand joins progressive prefetch", "on-demand joined prefetch index=" in texts["vot"]),
    ("subtitle audio handoff retained", 'clockSource = "video+audio-hold"' in texts["subtitle"]),
    ("speaker deterministic failure latched", "captureUnavailable" in texts["speaker"]),
    ("test sample cache noise suppressed", "if (segmentIndex >= 0)" in texts["cache"]),
    ("diagnostics version current", "Spanish Dub Study v2.30.0 diagnostics" in texts["controller"]),
    ("mixed-language guard helper installed", "longestSuspiciousSharedRun" in texts["language"]),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise SystemExit("v2.30 audit failed: " + ", ".join(failed))
print("v2.30 runtime stability audit passed")
