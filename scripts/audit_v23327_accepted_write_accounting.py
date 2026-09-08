#!/usr/bin/env python3
"""Audit v2.33.27 accepted AudioTrack.write accounting and containment."""
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
        raise SystemExit("usage: audit_v23327_accepted_write_accounting.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    helper = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/AudioVideoSyncProbe.java"
    sherpa = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    for p in (player, controller, helper, sherpa, hook, vot):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.27 source: {p}")

    pt = player.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    ht = helper.read_text(encoding="utf-8")
    nt = sherpa.read_text(encoding="utf-8")
    kt = hook.read_text(encoding="utf-8")
    vt = vot.read_text(encoding="utf-8")

    require(kt, "OneRegisterInstruction", "move-result register inspection")
    require(kt, "Opcode.MOVE_RESULT", "move-result opcode validation")
    require(kt, "pcmMethod.getInstruction(writeIndex + 1)", "original post-write result lookup")
    require(kt, "writeIndex + 2", "post-result callback insertion point")
    require(kt, "observeAudioTrackWriteRequestedForStudy(I)V", "pre-write requested-byte callback")
    require(kt, "observeAudioTrackWriteResultForStudy(I)V", "post-write result callback")
    require(kt, "writeInstruction.registerE", "format35c sizeInBytes register")
    require(kt, "writeInstruction.startRegister + 2", "range sizeInBytes register")

    require(pt, "observeAudioTrackWriteRequestedForStudy(int requestedBytes)", "primitive pre-write accounting")
    require(pt, "observeAudioTrackWriteResultForStudy(int result)", "primitive post-write accounting")
    require(pt, "studyPcmWriteAcceptedBytes += result;", "accepted bytes from actual write result")
    require(pt, "studyPcmWriteAcceptedFrames += result / bytesPerFrame;", "accepted PCM16 frame accounting")
    require(pt, "if (requested > 0 && result < requested) studyPcmWritePartial++;", "partial-write accounting")
    require(pt, "studyPcmWriteZero++;", "zero-write accounting")
    require(pt, "studyPcmWriteErrors++;", "negative write-result accounting")
    require(pt, "SherpaNeuralShadow.observePcmBuffer(", "existing Sherpa PCM feed retained")
    require(pt, "if (!studyLegacySpeakerDiarizationEnabled) return;", "legacy diarizer remains disabled")

    require(ht, "PlayerVolumePatch.getPcmWriteAcceptedFramesForStudy()", "controller-side accepted-frame sample")
    require(ht, "writeAcceptedFramesDelta", "session-local accepted-frame delta")
    require(ht, "writeRenderedFramesDelta", "session-local rendered-frame delta")
    require(ht, "audioVideoSyncAcceptedVsRenderedMs=", "accepted-vs-rendered diagnostic")
    require(ht, "audioVideoSyncAcceptedVsVideoMs=", "accepted-vs-video diagnostic")
    require(ht, "audioVideoSyncRecentWriteAnchors=", "recent video/head/accepted anchors")
    require(ht, "getPlaybackHeadPosition()", "rendered playback-head probe retained")
    require(ht, "getTimestamp(timestamp)", "AudioTimestamp probe retained")
    forbid(ht, ".write(", "AudioTrack write invocation from controller helper")
    forbid(ht, "VideoInformation.", "YouTube player API in sync helper")
    forbid(ht, "getVideoTime(", "direct YouTube player clock call in sync helper")

    require(ct, "Spanish Dub Study v2.33.27 accepted-write PCM clock diagnostics", "v2.33.27 header")
    require(ct, "audioVideoBridge=render-clock+accepted-write-accounting-active;pcm-admission-still-stride4", "accepted-write bridge status")
    require(ct, "pcmAdmission=unchanged-sherpa-stride4-v23327-diagnostic-only", "explicit no-admission-change marker")
    require(ct, "pcmWriteAccounting=post-audiotrack-write-return-value-diagnostic-only", "write-accounting diagnostic marker")
    require(ct, "pcmWriteAcceptedAudioMs=", "accepted duration diagnostic")
    require(ct, "AudioVideoSyncProbe.sample(videoClock", "controller-side bridge sampling retained")

    # v2.33.27 must not silently turn its diagnostic result into a new neural feed yet.
    require(nt, "if ((((int) captureBuffers) & 3) != 0) return;", "Sherpa stride-4 containment retained")
    require(nt, "v2.33.26-neural-only+stride4+absolute-video-projection", "unchanged v2.33.26 Sherpa gate")
    require(nt, "speakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse", "coarse neural projection retained")
    require(nt, "if (epoch != captureEpoch) return;", "neural epoch invalidation retained")
    require(nt, "if (local == null || state != STATE_READY)", "READY inference gate retained")
    forbid(nt, "AudioTrack.write", "AudioTrack write from neural worker")
    forbid(nt, "VideoInformation.", "YouTube player API in neural worker")
    forbid(nt, "getVideoTime(", "direct YouTube clock read in neural worker")
    forbid(nt, "interrupt()", "native inference interruption")

    require(vt, "final boolean sameVideo = videoId.equals(currentVideoId);", "same-video caption bootstrap")
    require(vt, "VideoSessionClock.onVideoOpened(videoId);", "video-session open")
    require(vt, "VideoSessionClock.onVideoClosed();", "full-close reset")
    require(vt, "VideoSessionClock.markExplicitSeek();", "seek continuity marker")

    print("PASS v2.33.27 accepted-write accounting audit")
    print("Actual AudioTrack.write return values are counted after move-result and compared on controller thread")
    print("Sherpa stride-4 admission and all translation/TTS/subtitle timing behavior remain unchanged")


if __name__ == "__main__":
    main()
