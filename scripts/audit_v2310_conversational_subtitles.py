#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2310_conversational_subtitles.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
subtitle = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
paging = (study / "SubtitlePagePolicy.java").read_text(encoding="utf-8")
pairing = (study / "BilingualCardPolicy.java").read_text(encoding="utf-8")

checks = [
    ("native OpenRouter 1500-char packet budget preserved", "OPENROUTER_MAX_BATCH_CHARS = 1_500" in translator),
    ("native first packet 350-char budget preserved", "OPENROUTER_FIRST_BATCH_CHARS = 350" in translator),
    ("stock mergeIntoSentences preserved", "return mergeIntoSentences(lines);" in fetcher or "List<TranscriptSegment> merged = mergeIntoSentences(lines);" in fetcher),
    ("conversational translation wording guidance", "natural conversational spoken Spanish suitable for dubbing and subtitles" in translator),
    ("prompt still requires one line per native segment", "One line per number. Do not merge or skip." in translator),
    ("display-only conversational scoring installed", "Build readable cards by scoring nearby break points" in paging),
    ("bilingual Spanish-audio master alignment installed", "Spanish is the audible master" in pairing),
    ("overlay uses pair-specific shared progress", "pageIndex = pair.index(progress);" in subtitle),
    ("diagnostics expose packet hard rule", "translationPacketization=stock-morphe-1500char+350char-first-UNCHANGED" in controller),
    ("diagnostics identify v2.31", "Spanish Dub Study v2.31.0 diagnostics" in controller),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise SystemExit("v2.31 audit failed: " + ", ".join(failed))
print("v2.31 conversational subtitle audit passed")
