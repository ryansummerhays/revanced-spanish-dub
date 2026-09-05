#!/usr/bin/env python3
"""Static integration audit for Spanish Dub Study v2.29 stability fixes."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2290_stability.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

files = {
    "translator": pkg / "TranscriptTranslator.java",
    "vot": pkg / "VoiceOverTranslationPatch.java",
    "prefetch": pkg / "TtsPrefetcher.java",
    "engine": pkg / "TtsEngine.java",
    "subtitle": study / "SpanishSubtitleOverlay.java",
    "budget": study / "OpenRouterBudget.java",
}
for name, path in files.items():
    if not path.is_file():
        raise SystemExit(f"missing {name}: {path}")

texts = {name: path.read_text(encoding="utf-8") for name, path in files.items()}

checks = [
    ("char-aware OpenRouter budget helper", "OpenRouterBudget.maxOutputTokens(joined.length(), segments.size())" in texts["translator"]),
    ("stock 30-token regression removed", '.put("max_tokens", segments.size() * 30)' not in texts["translator"]),
    ("actual max-token diagnostics", 'maxTokens=" + maxOutputTokens' in texts["translator"]),
    ("stream snapshots do not mark untouched tail translated", "!streamed.equals(orig.text)" in texts["translator"]),
    ("progressive snapshots feed TTS prefetch", "TtsPrefetcher.updateVideo(videoId, updated);" in texts["vot"]),
    ("same-video prefetch keeps playhead", "if (videoChanged) currentVideoTimeMs = 0;" in texts["prefetch"]),
    ("MediaPlayer position getter", "getCurrentPlaybackPositionMsForStudy" in texts["engine"]),
    ("MediaPlayer duration getter", "getCurrentPlaybackDurationMsForStudy" in texts["engine"]),
    ("VOT exposes Edge media progress", "getEdgePlaybackProgressForStudy" in texts["vot"]),
    ("subtitle uses Edge media clock", 'clockSource = "tts-media"' in texts["subtitle"]),
    ("subtitle holds during Edge synthesis", 'clockSource = "tts-wait"' in texts["subtitle"]),
    ("subtitle retains video fallback", 'clockSource = "video"' in texts["subtitle"]),
    ("speaker experiment still diagnostic-only", "speakerVoiceRouting=disabled-diagnostic-labels-only" in (study / "LocalSpeakerDiarizer.java").read_text(encoding="utf-8")),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise SystemExit("v2.29 audit failed: " + ", ".join(failed))
print("v2.29 stability audit passed")
