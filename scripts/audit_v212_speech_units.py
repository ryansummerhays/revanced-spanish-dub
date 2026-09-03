#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
planner = (study / "SpeechUnitPlanner.java").read_text(encoding="utf-8")
fetcher = (votpkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
vot = (votpkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")

method_start = vot.index("public static void newVideoLoaded(String videoId)")
method_end = vot.index("public static void videoTimeChanged(long timeMs)", method_start)
new_video = vot[method_start:method_end]

checks = [
    ("v2.12 diagnostics", "Spanish Dub Study v2.12.0 diagnostics" in controller),
    ("speech-unit floor exposed", "speechUnitFloor=" in controller),
    ("2400ms viable floor", "MIN_UNIT_MS = 2_400L" in planner),
    ("planner preserves bounded units", "MAX_UNIT_MS = 9_000L" in planner and "MAX_UNIT_CHARS = 150" in planner),
    ("planner can borrow silence", "borrow that otherwise-unused time" in planner),
    ("planner wired after natural segmentation", "SpeechUnitPlanner.coalesce(rawUnits)" in fetcher),
    ("coalescing diagnostic", 'record("PHRASE", "speech units "' in fetcher),
    ("duplicate guard exists", "duplicate newVideoLoaded ignored" in new_video),
    ("duplicate guard precedes timeline reset", new_video.index("videoId.equals(currentVideoId)") < new_video.index("lastVideoTimeMs = 0")),
    ("duplicate guard precedes overlay clear", new_video.index("videoId.equals(currentVideoId)") < new_video.index("SpanishStudyController.onVideoCleared()")),
    ("Google-only baseline retained", "translationMode=google-only-stable" in controller and "cloudAnalysis=disabled" in controller),
]

failed=[]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + " | " + name)
    if not ok: failed.append(name)
if failed:
    raise SystemExit("v2.12 audit failed: " + ", ".join(failed))
print(f"v2.12 audit passed ({len(checks)} invariants)")
