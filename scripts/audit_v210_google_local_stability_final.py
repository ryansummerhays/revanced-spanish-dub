#!/usr/bin/env python3
"""Behavioral build-time invariants for Spanish Dub Study v2.10.0."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
p = {
    "controller": study / "SpanishStudyController.java",
    "gemini": study / "GeminiTranslator.java",
    "ground": study / "GeminiVideoGroundingSidecar.java",
    "speaker": study / "GeminiSpeakerDiarizationSidecar.java",
    "translator": votpkg / "TranscriptTranslator.java",
    "tts": votpkg / "TtsEngine.java",
    "prefetcher": votpkg / "TtsPrefetcher.java",
}
t = {k: v.read_text(encoding="utf-8") for k, v in p.items()}

g=t["gemini"]
g_start=g.find("public static boolean isEnabled()")
g_end=g.find("\n    /**",g_start)
g_enabled=g[g_start:g_end] if g_start>=0 and g_end>g_start else ""

gr=t["ground"]
gr_start=gr.find("static void schedule(")
gr_end=gr.find("\n    static",gr_start+1)
gr_method=gr[gr_start:gr_end] if gr_start>=0 and gr_end>gr_start else ""

# Speaker class has no reliable Javadoc boundary after maybeSchedule. Verify the unique runtime entry
# point exists and the finalizer inserted the unconditional no-op anywhere in that class.
s=t["speaker"]
speaker_noop=("static void maybeSchedule(" in s and "if (true) return;" in s)

checks=[
    ("v2.10 diagnostics", "Spanish Dub Study v2.10.0 diagnostics" in t["controller"]),
    ("stable mode diagnostic", "translationMode=google-only-stable" in t["controller"]),
    ("zero Gemini runtime diagnostic", "geminiRuntime=disabled-in-v2.10" in t["controller"]),
    ("effective Google-only translator", "String service = TRANSLATION_SERVICE_GOOGLE;" in t["translator"]),
    ("Gemini translator hard false", bool(g_enabled) and "return false;" in g_enabled),
    ("grounding real entry point gated by hard-false Gemini", bool(gr_method) and "if (!GeminiTranslator.isEnabled()) return;" in gr_method),
    ("speaker remote entry point unconditional no-op", speaker_noop),
    ("speaker diagnostic says future local", "speakerBackend=disabled-pending-local-audio-pipeline" in t["controller"]),
    ("Edge synthesis timeout bounded", "READ_TIMEOUT_MS    = 8_000" in t["tts"]),
    ("prefetch failure cooldown state", "FAILED_SEGMENT_COOLDOWN_MS = 25_000L" in t["prefetcher"]),
    ("prefetch skips cooled indices", t["prefetcher"].count("!isPrefetchCoolingDown(i)") >= 3),
    ("prefetch failure marks cooldown", "markPrefetchFailure(index);" in t["prefetcher"]),
    ("prefetch cooldown diagnostic", 'SpanishStudyDiagnostics.record("TTS-PREFETCH", "cooldown index="' in t["prefetcher"]),
]
failed=[]
for name,ok in checks:
    print(("PASS" if ok else "FAIL")+" | "+name)
    if not ok: failed.append(name)
if failed:
    raise SystemExit("v2.10 behavioral audit failed: "+", ".join(failed))
print(f"v2.10 behavioral audit passed ({len(checks)} invariants)")
