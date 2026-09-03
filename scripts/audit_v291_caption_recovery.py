#!/usr/bin/env python3
"""Build-time invariants for v2.9.1 caption recovery."""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
study=root/"extensions/youtube/src/main/java/app/spanishstudy/vot"
votpkg=root/"extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
fetcher=(votpkg/"TranscriptFetcher.java").read_text(encoding="utf-8")
controller=(study/"SpanishStudyController.java").read_text(encoding="utf-8")
vot=(votpkg/"VoiceOverTranslationPatch.java").read_text(encoding="utf-8")

checks=[
    ("v2.9.1 label", "Spanish Dub Study v2.9.1 diagnostics" in controller),
    ("Innertube cookie context", 'playerCookies = CaptionCookiesPatch.getCookies()' in fetcher),
    ("Innertube auth context", 'playerAuthHeaders = AuthUtils.getRequestHeader()' in fetcher),
    ("Innertube timing diagnostics", 'CAPTION-NET' in fetcher and 'innertube response=' in fetcher),
    ("manual timedtext recovery", 'asr ? "&kind=asr" : ""' in fetcher),
    ("manual and ASR modes", 'asr ? "asr" : "manual"' in fetcher),
    ("caption exhaustion diagnostic", 'all caption recovery paths exhausted' in fetcher),
    ("signed URL error sanitization", 'safeCaptionError' in fetcher and '<url>' in fetcher),
    ("session enable diagnostic", 'onSessionEnabled()' in controller and 'SpanishStudyController.onSessionEnabled();' in vot),
    ("session caller diagnostic", 'disabled caller=' in controller and 'deactivateTranslation' in controller),
]
failed=[]
for name,ok in checks:
    print(("PASS" if ok else "FAIL")+" | "+name)
    if not ok: failed.append(name)
if failed:
    raise SystemExit("v2.9.1 audit failed: "+", ".join(failed))
print(f"v2.9.1 caption recovery audit passed ({len(checks)} invariants)")
