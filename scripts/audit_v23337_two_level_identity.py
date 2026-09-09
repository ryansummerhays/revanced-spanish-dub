#!/usr/bin/env python3
"""Source audit for v2.33.37 raw-acoustic-profile -> persistent-human identity layer."""
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
    must(live, "return labelFor(TL_SPEAKER[i]);", "timeline resolves through labelFor")

    must(live, "private static final int[] PROFILE_HUMAN", "raw profile human map")
    must(live, "speakerLiveMode=eres2net-two-level-acoustic-human-identity-v23337", "v37 live mode")
    must(live, "speakerLiveArchitecture=raw-acoustic-profile-cache->persistent-human-map", "two-level architecture")
    must(live, "speakerLiveProfileFormat=raw->human[~style]:prototypes/support", "raw-human diagnostic format")
    must(live, "speakerLiveHumans=", "human count diagnostics")
    must(live, "speakerLiveAcousticProfilesLinkedToExistingHuman=", "style-link diagnostics")
    must(live, "assignHumanForPromotedProfileLocked", "promotion ownership resolver")
    must(live, "originParentSpeaker", "persistent same-run origin evidence")
    must(live, "int dynamicMinSupport = humanCount <= 1", "human-count complexity gate")
    must(live, "boolean boundaryEvidence = humanCount <= 1", "human-count boundary gate")
    must(live, "new-acoustic-style-cluster-linked-human", "same-human raw-state decision")
    must(live, "new-human-coherent-cluster", "new-human decision")
    must(live, "acousticProfileSwitches", "raw switch accounting")
    must(live, "sameHumanRawTransitions", "same-human raw transition accounting")

    must(ctl, "Spanish Dub Study v2.33.37 two-level acoustic-profile + human-identity diagnostics", "controller version")
    must(ctl, "speakerLiveGoal=two-level-streaming-identity;acoustic-states-under-persistent-humans", "controller goal")
    must(ctl, "pcmAdmission=exact-android-accepted-postwrite-slice-v23330-threadlocal-bridge", "accepted PCM bridge")
    must(ctl, "videoMasterClock=video-ms-authority", "video master clock")

    absent(live, "speakerLiveMode=eres2net-contextual-streaming-human-identity-v23336", "stale v36 live mode")
    print("v2.33.37 source audit passed")


if __name__ == "__main__":
    main()
