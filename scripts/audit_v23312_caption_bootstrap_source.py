#!/usr/bin/env python3
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23312_caption_bootstrap_source.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    p = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    text = p.read_text()
    if "if (videoId.equals(currentVideoId)) return;" in text:
        raise RuntimeError("old caption-starving same-video return still present")
    for needle in (
        "final boolean sameVideo = videoId.equals(currentVideoId);",
        "if (!sameVideo) {",
        "PlayerVolumePatch.resetSpeakerAnalysisForStudy();",
        "if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) return;",
        "loadTranscript(videoId);",
    ):
        if needle not in text: raise RuntimeError(f"missing bootstrap invariant: {needle}")
    # State reset must occur inside the new-video-only block, before the eligibility gate.
    a = text.index("final boolean sameVideo = videoId.equals(currentVideoId);")
    reset = text.index("PlayerVolumePatch.resetSpeakerAnalysisForStudy();", a)
    gate = text.index("if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;", a)
    if not (a < reset < gate): raise RuntimeError("new-video reset/eligibility order is wrong")
    print("PASS v2.33.12 source caption-bootstrap audit")


if __name__ == "__main__":
    main()
