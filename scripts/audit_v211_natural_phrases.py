#!/usr/bin/env python3
"""Build-time invariants for Spanish Dub Study v2.11.0 pause-aware local phrasing."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

files = {
    "controller": study / "SpanishStudyController.java",
    "splitter": study / "SemanticClauseSplitter.java",
    "timing": study / "SourceCaptionTimingStore.java",
    "fetcher": votpkg / "TranscriptFetcher.java",
    "vot": votpkg / "VoiceOverTranslationPatch.java",
    "button": root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/videoplayer/VoiceOverTranslationButton.java",
}
text = {k: p.read_text(encoding="utf-8") for k, p in files.items()}

checks = [
    ("v2.11 diagnostics", "Spanish Dub Study v2.11.0 diagnostics" in text["controller"]),
    ("pause-aware diagnostics", "phraseParsing=pause-aware-local" in text["controller"]),
    ("cloud analysis remains disabled", "cloudAnalysis=disabled" in text["controller"]),
    ("old active-looking Gemini diagnostics removed", all(k not in text["controller"] for k in [
        "geminiConfigured=", "geminiModel=", "geminiMediaState=", "videoGroundingActive=",
        "speakerRecognition=", "translationMemory="])),
    ("speech rate diagnostics distinguish preferred and catchup",
        "preferredSpeechRate=" in text["controller"] and "catchupCeiling=" in text["controller"]),
    ("timing exposes inter-word gaps", "long[] interWordGaps(" in text["timing"]),
    ("semantic splitter accepts timing", "split(String raw, long[] interWordGapsMs)" in text["splitter"]),
    ("semantic splitter restores punctuation", "restorePunctuation(String raw, long[] interWordGapsMs)" in text["splitter"]),
    ("transcript pipeline feeds timing to parser", "SourceCaptionTimingStore.interWordGaps(" in text["fetcher"]
        and "SemanticClauseSplitter.split(sentence.text, interWordGaps)" in text["fetcher"]),
    ("loading-safe player toggle exists", "toggleTranslationFromPlayerButton()" in text["vot"]
        and "player tap while loading; kept enabled" in text["vot"]),
    ("both player buttons use safe toggle", text["button"].count("toggleTranslationFromPlayerButton();") == 2),
    ("player buttons no longer directly toggle", "VoiceOverTranslationPatch.toggleTranslation();" not in text["button"]),
]

failed = []
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + " | " + name)
    if not ok:
        failed.append(name)
if failed:
    raise SystemExit("v2.11 audit failed: " + ", ".join(failed))
print(f"v2.11 audit passed ({len(checks)} invariants)")
