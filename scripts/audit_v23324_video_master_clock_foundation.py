#!/usr/bin/env python3
"""Audit v2.33.24 source-level video-master foundation."""
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23324_video_master_clock_foundation.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    controller = base / "SpanishStudyController.java"
    for p in (vot, controller, base / "VideoSessionClock.java", base / "AudioVideoTimeBridge.java", base / "SpeakerTimeline.java"):
        if not p.is_file(): raise RuntimeError(f"missing source: {p}")

    vt = vot.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    clock = (base / "VideoSessionClock.java").read_text(encoding="utf-8")
    bridge = (base / "AudioVideoTimeBridge.java").read_text(encoding="utf-8")
    timeline = (base / "SpeakerTimeline.java").read_text(encoding="utf-8")

    require(vt, "final boolean sameVideo = videoId.equals(currentVideoId);", "same-video bootstrap branch")
    require(vt, "if (!sameVideo) {", "new-video-only mutation block")
    if "if (videoId.equals(currentVideoId)) return;" in vt:
        raise RuntimeError("caption-starving same-video hard return reintroduced")
    require(vt, "VideoSessionClock.onVideoOpened(videoId);", "new-video clock open")
    require(vt, "PlayerVolumePatch.resetSpeakerAnalysisForStudy();", "Stage-J reset retained")
    if vt.index("VideoSessionClock.onVideoOpened(videoId);") > vt.index("PlayerVolumePatch.resetSpeakerAnalysisForStudy();"):
        raise RuntimeError("clock open must occur before Stage-J new-video reset")
    require(vt, "VideoSessionClock.onVideoClosed();", "full-close clock reset")
    require(vt, "VideoSessionClock.markExplicitSeek();", "explicit seek marker")
    require(ct, "VideoSessionClock.publishVideoTime(timeMs);", "master clock publication")
    require(ct, "videoMasterClock=video-ms-authority", "clock diagnostics")
    require(ct, "raw-audiotrack-callback-count-not-a-clock", "audio clock policy diagnostic")

    require(clock, "continuityEpoch", "continuity epoch state")
    require(clock, "AUTO_DISCONTINUITY_MS", "automatic discontinuity detector")
    require(bridge, "allowedTotalSamples = (elapsedVideoMs * sampleRateHz) / 1000L", "video-bounded sample admission")
    require(bridge, "clock.videoEpoch != videoEpoch || clock.continuityEpoch != continuityEpoch", "capture invalidation")
    require(timeline, "startVideoMs", "absolute speaker start")
    require(timeline, "endVideoMs", "absolute speaker end")
    require(timeline, "segmentVideoEpoch != videoEpoch", "old-video rejection")

    # Foundation classes must not themselves touch YouTube/player APIs or the hot AudioTrack hook.
    for src_name, src in (("clock", clock), ("bridge", bridge), ("timeline", timeline)):
        for forbidden in ("VideoInformation.", "AudioTrack.write", "PlayerVolumePatch"):
            if forbidden in src:
                raise RuntimeError(f"{src_name} unexpectedly references hot/player path: {forbidden}")

    print("PASS v2.33.24 video-master foundation audit")
    print("same-video bootstrap preserved; new-id/full-close reset; seek continuity boundary present")
    print("audio/video bridge and absolute speaker timeline compiled but not yet active in PCM path")


if __name__ == "__main__":
    main()
