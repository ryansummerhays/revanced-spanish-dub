#!/usr/bin/env python3
"""Source audit for v2.33.36 streaming speaker cache/change-point revision."""
from pathlib import Path
import sys


def must(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def absent(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"unexpected {label}: {needle}")
    print("ok absent:", label)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "upstream").resolve()
    live = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java").read_text(encoding="utf-8")
    ctl = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java").read_text(encoding="utf-8")
    must(live, "WINDOW_SAMPLES = 32_000", "2.0 s identity context")
    must(live, "HOP_SAMPLES = 9_600", "600 ms update cadence")
    must(live, "ADJACENT_CHANGE_POINT = 0.44f", "sequential change detector")
    must(live, "THIRD_SPEAKER_MIN_SUPPORT = 7", "third speaker penalty")
    must(live, "LATER_SPEAKER_MIN_SUPPORT = 9", "later speaker penalty")
    must(live, "speakerLiveArchitecture=sequential-change-point+multi-prototype-speaker-cache+provisional-retrofill", "architecture diagnostics")
    must(live, "speakerLiveBadgeCommittedHolds=", "badge hold diagnostics")
    must(live, "return labelFor(TL_SPEAKER[i]);", "confirmed lag-hold label")
    must(ctl, "Spanish Dub Study v2.33.36 streaming speaker-cache + change-point diagnostics", "controller version")
    must(ctl, "pcmAdmission=exact-android-accepted-postwrite-slice-v23330-threadlocal-bridge", "accepted PCM bridge")
    must(ctl, "videoMasterClock=video-ms-authority", "video master clock")
    absent(live, "speakerLiveMode=eres2net-short-window-online-human-identity-v23335", "stale v35 live mode")
    print("v2.33.36 source audit passed")


if __name__ == "__main__":
    main()
