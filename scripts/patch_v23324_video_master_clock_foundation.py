#!/usr/bin/env python3
"""v2.33.24 foundation: make YouTube video milliseconds the authoritative content clock.

This is intentionally a lifecycle/diagnostic foundation only. It does NOT alter the AudioTrack
hook, Stage-J feature math/clustering, Sherpa capture/inference, translation packetization,
subtitles, or TTS scheduling. The adaptive AudioVideoTimeBridge and SpeakerTimeline classes are
compiled into the extension but remain inert until a later gate.

Reset semantics:
- same video lifecycle callback: keep state
- pause/minimize/PiP/maximize: keep state
- explicit seek or large clock jump: new continuity epoch, same video epoch
- different video id: new video epoch
- PlayerType.NONE/full close: close current session; reopening is fresh
"""
from pathlib import Path
import shutil
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v23324_video_master_clock_foundation.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    target.mkdir(parents=True, exist_ok=True)

    for name in ("VideoSessionClock.java", "AudioVideoTimeBridge.java", "SpeakerTimeline.java"):
        src = repo / "overlay/v2331/app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing video-master source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)

    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    controller = target / "SpanishStudyController.java"
    if not vot.is_file() or not controller.is_file():
        raise RuntimeError("missing Stage-J VOT/controller source")

    rep(
        vot,
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n"
        "import app.spanishstudy.vot.VideoSessionClock;\n",
        "import video master clock",
    )

    # Stage J already leaves this guard before its per-video speaker reset. Keep it sacred: a
    # duplicate callback for the same open video must not create a new video epoch.
    rep(
        vot,
        "        if (videoId.equals(currentVideoId)) return;\n\n"
        "        PlayerVolumePatch.resetSpeakerAnalysisForStudy();\n",
        "        if (videoId.equals(currentVideoId)) return;\n\n"
        "        VideoSessionClock.onVideoOpened(videoId);\n"
        "        PlayerVolumePatch.resetSpeakerAnalysisForStudy();\n",
        "open clock session only for genuinely new video",
    )

    # Full player close is distinct from SpanishStudyController.onVideoCleared(), which is also
    # used while switching to a new id. Only PlayerType.NONE closes the master-clock session.
    rep(
        vot,
        "                    TtsPrefetcher.clear();\n"
        "                    SpanishStudyController.onVideoCleared();\n",
        "                    TtsPrefetcher.clear();\n"
        "                    SpanishStudyController.onVideoCleared();\n"
        "                    VideoSessionClock.onVideoClosed();\n",
        "close video session only on PlayerType.NONE",
    )

    rep(
        controller,
        "    public static void onVideoTimeChanged(long timeMs) {\n"
        "        SpanishStudyDiagnostics.samplePlayhead(timeMs);\n",
        "    public static void onVideoTimeChanged(long timeMs) {\n"
        "        VideoSessionClock.publishVideoTime(timeMs);\n"
        "        SpanishStudyDiagnostics.samplePlayhead(timeMs);\n",
        "publish YouTube milliseconds as master clock",
    )

    # Programmatic seeks may be shorter than the automatic discontinuity threshold. Mark them
    # before the next video-time callback so the next clock publication creates one boundary.
    rep(
        vot,
        "    public static void onVideoSeeked() {\n"
        "        Logger.printDebug(() -> \"onVideoSeeked\");\n",
        "    public static void onVideoSeeked() {\n"
        "        Logger.printDebug(() -> \"onVideoSeeked\");\n"
        "        VideoSessionClock.markExplicitSeek();\n",
        "mark explicit seek continuity boundary",
    )

    diag_anchor = (
        '        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append(\'\\n\');\n'
    )
    diag_insert = diag_anchor + (
        '        VideoSessionClock.Snapshot videoClock = VideoSessionClock.snapshot();\n'
        '        report.append("videoMasterClock=video-ms-authority\\n");\n'
        '        report.append("videoSessionOpen=").append(videoClock.open).append(\'\\n\');\n'
        '        report.append("videoEpoch=").append(videoClock.videoEpoch).append(\'\\n\');\n'
        '        report.append("videoContinuityEpoch=").append(videoClock.continuityEpoch).append(\'\\n\');\n'
        '        report.append("videoMasterMs=").append(videoClock.videoMs).append(\'\\n\');\n'
        '        report.append("videoClockUpdates=").append(videoClock.updates).append(\'\\n\');\n'
        '        report.append("videoExplicitSeeks=").append(videoClock.explicitSeeks).append(\'\\n\');\n'
        '        report.append("videoDetectedDiscontinuities=").append(videoClock.detectedDiscontinuities).append(\'\\n\');\n'
        '        report.append("videoResetPolicy=new-id-or-full-close;pause-minimize-pip-keep;seek-continuity-only\\n");\n'
        '        report.append("audioClockAuthority=video-ms;raw-audiotrack-callback-count-not-a-clock\\n");\n'
        '        report.append("audioVideoBridge=compiled-inert-until-next-gate\\n");\n'
        '        report.append("speakerTimeline=compiled-absolute-video-ms-inert-until-next-gate\\n");\n'
    )
    rep(controller, diag_anchor, diag_insert, "publish video-master diagnostics")

    print("v2.33.24 video-master-clock foundation patch complete")
    print("UNCHANGED: AudioTrack hook, Stage-J PCM/VAD/features/clustering, Sherpa capture/inference")
    print("UNCHANGED: translation segmentation/packetization/recovery, subtitle timing, TTS")
    print("ADDED: source-compiled video epoch + continuity epoch + master videoMs + reset policy")
    print("COMPILED BUT INERT: adaptive AudioVideoTimeBridge and absolute SpeakerTimeline")


if __name__ == "__main__":
    main()
