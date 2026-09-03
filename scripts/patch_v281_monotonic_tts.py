#!/usr/bin/env python3
"""v2.8.1: prevent stale subtitle indices from replaying and expose real pacing lateness."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v281_monotonic_tts.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"

    # The normal player loop historically used i != lastSpokenIndex. If a later segment started
    # while the video clock was still inside an overlapping earlier source slot, the next tick could
    # legally walk BACK to that older index and replay it. Diagnostics from v2.7.1 showed exactly
    # that pattern (e.g. 387 -> 388 -> 387 -> 388), wasting seconds and creating a catch-up spiral.
    # Ordinary playback is now strictly monotonic. A real explicit seek resets lastSpokenIndex=-1,
    # so intentional backwards seeking remains fully supported.
    rep(vot,
'''                    if (i != lastSpokenIndex) {''',
'''                    if (wasExplicitSeek || i > lastSpokenIndex) {''',
        "make ordinary TTS dispatch monotonic")

    # v2.7's PACE diagnostic called the remaining time to seg.endMs simply "slot", which made it
    # impossible to distinguish a genuinely tiny source caption from a normal caption whose TTS
    # started late because a prior phrase was still speaking. Record both total source span and
    # lateness so future logs tell us which case is actually dominating.
    rep(vot,
'''            SpanishStudyDiagnostics.record("PACE", "adaptive rate=" + rate + " preferred="
                    + preferredRate + " speech=" + remainingSpeechMs + "ms slot=" + availableMs + "ms");''',
'''            SpanishStudyDiagnostics.record("PACE", "adaptive rate=" + rate + " preferred="
                    + preferredRate + " speech=" + remainingSpeechMs
                    + "ms remaining=" + availableMs
                    + "ms sourceSpan=" + Math.max(1L,seg.endMs-seg.startMs)
                    + "ms lateBy=" + Math.max(0L,nowVideoMs-seg.startMs) + "ms");''',
        "separate source span from late-start remaining time")

    # Label the report so copied diagnostics prove this fix is installed.
    rep(controller,
'''        report.append("Spanish Dub Study v2.8.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.8.1 diagnostics\\n");''',
        "label v2.8.1 diagnostics")

    print("v2.8.1 monotonic TTS integration complete")


if __name__ == "__main__":
    main()
