#!/usr/bin/env python3
"""Audit v2.33.26 neural-only absolute video-time speaker instrumentation."""
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23326_neural_absolute_timeline.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = base / "SpanishStudyController.java"
    subtitle = base / "SpanishSubtitleOverlay.java"
    sheet = base / "SpanishStudySheet.java"
    sherpa = base / "SherpaNeuralShadow.java"
    helper = base / "AudioVideoSyncProbe.java"
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    for p in (player, controller, subtitle, sheet, sherpa, helper, vot):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.26 source: {p}")

    pt = player.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    st = subtitle.read_text(encoding="utf-8")
    sht = sheet.read_text(encoding="utf-8")
    nt = sherpa.read_text(encoding="utf-8")
    ht = helper.read_text(encoding="utf-8")
    vt = vot.read_text(encoding="utf-8")

    # Render-clock probe is controller driven and cannot invoke YouTube/player APIs or AudioTrack.write.
    require(ht, "getPlaybackHeadPosition()", "AudioTrack playback-head sampling")
    require(ht, "getTimestamp(timestamp)", "AudioTimestamp sampling")
    require(ht, "clockAnchor videoMs=", "optional runtime anchor trace")
    require(ht, "audioVideoSyncRecentAnchors=", "recent anchor diagnostics")
    forbid(ht, "AudioTrack.write", "hot write invocation in sync helper")
    forbid(ht, "VideoInformation.", "YouTube player API in sync helper")
    forbid(ht, "getVideoTime(", "direct YouTube clock read in sync helper")

    require(pt, "getActiveAudioTrackForStudy()", "read-only active AudioTrack accessor")
    require(pt, "SherpaNeuralShadow.observePcmBuffer(", "Sherpa PCM feed retained")
    require(pt, "legacy Stage-E/F/G/J", "legacy diarizer retired marker")

    require(ct, "VideoSessionClock.publishVideoTime(timeMs);", "video master publication")
    require(ct, "AudioVideoSyncProbe.sample(videoClock", "controller-side audio/video sampling")
    require(ct, "SherpaNeuralShadow.observeVideoClock(videoClock);", "neural continuity ownership")
    require(ct, "LocalSpeakerDiarizer.setEnabled(activity, false);", "legacy Visualizer disabled")
    require(ct, "Spanish Dub Study v2.33.26 neural absolute-timeline + audio-render-clock diagnostics", "v2.33.26 header")
    require(ct, "audioVideoBridge=render-clock-anchor-probe-active;pcm-admission-still-stride4", "render-clock status")
    require(ct, "speakerTimeline=neural-relative-to-video-span-projection-active-coarse", "coarse timeline status")
    require(ct, "speakerPcmDiarizationStatus=legacy-stage-e-f-g-j-disabled-v23326", "legacy Stage-J disabled diagnostic")
    require(ct, "speakerLabelClock=neural-absolute-video-ms-projection", "neural label clock diagnostic")

    require(st, "SherpaNeuralShadow.labelAtVideoMs(timeMs)", "neural subtitle speaker badge")
    require(st, "SherpaNeuralShadow.labelDetailsAtVideoMs(timeMs)", "neural badge timing diagnostics")
    forbid(st, "getSpeakerClusterCommittedForStudy()", "legacy Stage-J badge authority")

    require(sht, '"Neural speaker timing"', "neural speaker UI section")
    require(sht, '"Show neural speaker labels"', "neural label visibility option")
    require(sht, '"Audio / video clock"', "audio/video log option")
    require(sht, '"Neural speaker timeline"', "neural timeline log option")
    forbid(sht, "LocalSpeakerDiarizer.setEnabled(activity, value)", "legacy Visualizer toggle")

    # Sherpa remains bounded/safe while gaining video ownership and absolute projection.
    require(nt, "CAPTURE_TARGET_SAMPLES = TARGET_SAMPLE_RATE * CAPTURE_SECONDS", "bounded neural capture")
    require(nt, "if ((((int) captureBuffers) & 3) != 0) return;", "temporary stride-4 containment")
    require(nt, "captureVideoEpoch", "capture video ownership")
    require(nt, "captureContinuityEpoch", "capture continuity ownership")
    require(nt, "captureStartVideoMs", "capture start video time")
    require(nt, "captureEndVideoMs", "capture end video time")
    require(nt, "speakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse", "explicit coarse alignment mode")
    require(nt, "speakerNeuralAbsoluteSummary=", "absolute timeline diagnostics")
    require(nt, "labelAtVideoMs(long videoMs)", "absolute speaker lookup")
    require(nt, "speakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline", "neural badge authority")
    require(nt, "v2.33.26-neural-only+stride4+absolute-video-projection", "v2.33.26 neural gate")
    require(nt, "if (epoch != captureEpoch) return;", "native result epoch invalidation")
    require(nt, "if (local == null || state != STATE_READY)", "READY inference gate")
    require(nt, "worker.setPriority(Thread.MIN_PRIORITY)", "low-priority inference worker")
    forbid(nt, "VideoInformation.", "YouTube player API in neural worker")
    forbid(nt, "getVideoTime(", "direct player-time call in neural worker")
    forbid(nt, "interrupt()", "native inference interruption")

    # Caption bootstrap/reset semantics from v12/v24 must still be preserved.
    require(vt, "final boolean sameVideo = videoId.equals(currentVideoId);", "same-video bootstrap branch")
    forbid(vt, "if (videoId.equals(currentVideoId)) return;", "caption-starving same-video return")
    require(vt, "VideoSessionClock.onVideoOpened(videoId);", "new-video epoch open")
    require(vt, "VideoSessionClock.onVideoClosed();", "full-close reset")
    require(vt, "VideoSessionClock.markExplicitSeek();", "seek continuity marker")

    print("PASS v2.33.26 neural absolute-timeline audit")
    print("Sherpa-only authority, controller-side render-clock anchors, coarse absolute video-ms projection")
    print("Legacy Visualizer/Stage-E-F-G-J authority disabled; translation/TTS/subtitle timing architecture untouched")


if __name__ == "__main__":
    main()
