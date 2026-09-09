#!/usr/bin/env python3
"""Finish v2.33.28 after the stage-1 driver reaches the known chained-diagnostics source shape."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: finish_v23328_render_clock_admission.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    sherpa = base / "SherpaNeuralShadow.java"
    controller = base / "SpanishStudyController.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"

    rep(
        sherpa,
        '.append("\\nspeakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection")',
        '.append("\\nspeakerNeuralGate=v2.33.28-neural-only+render-credit+absolute-video-projection")',
        "update chained neural gate diagnostic",
    )
    rep(
        sherpa,
        '.append("\\nspeakerNeuralPcmFeed=direct-pcm16-fullwindow-stride4-16k-20s")',
        '.append("\\nspeakerNeuralPcmFeed=direct-pcm16-fullwindow-render-credit-gated-16k-20s")',
        "identify chained render-credit PCM feed",
    )
    rep(
        sherpa,
        '.append("\\nspeakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse")',
        '.append("\\nspeakerNeuralAbsoluteTimelineMode=render-credit-projection-from-controller-render-video-anchor")',
        "identify chained render-credit absolute timeline mode",
    )

    rep(
        sherpa,
        '''        int progress = (int) Math.min(1000L,
                ((long) captureSamples * 1000L) / CAPTURE_TARGET_SAMPLES);
        return new StringBuilder()
''',
        '''        int progress = (int) Math.min(1000L,
                ((long) captureSamples * 1000L) / CAPTURE_TARGET_SAMPLES);
        long neuralAcceptedMs = captureSourceRateHz > 0
                ? (captureRenderAcceptedInputFrames * 1000L) / captureSourceRateHz : 0L;
        return new StringBuilder()
''',
        "compute render-credit accepted milliseconds for diagnostics",
    )

    rep(
        sherpa,
        '''                .append("\\nspeakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary)
                .append("\\nspeakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline")
''',
        '''                .append("\\nspeakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary)
                .append("\\nspeakerNeuralRenderBaselineHeadFrames=").append(captureRenderBaselineHeadFrames)
                .append("\\nspeakerNeuralRenderBaselineVideoMs=").append(captureRenderBaselineVideoMs)
                .append("\\nspeakerNeuralRenderSessionId=").append(captureRenderSessionId)
                .append("\\nspeakerNeuralRenderAnchorRateHz=").append(captureRenderAnchorRateHz)
                .append("\\nspeakerNeuralRenderAllowedInputFrames=").append(captureRenderAllowedInputFrames)
                .append("\\nspeakerNeuralRenderAcceptedInputFrames=").append(captureRenderAcceptedInputFrames)
                .append("\\nspeakerNeuralRenderAcceptedAudioMs=").append(neuralAcceptedMs)
                .append("\\nspeakerNeuralRenderGateAcceptedBuffers=").append(captureRenderGateAcceptedBuffers)
                .append("\\nspeakerNeuralRenderGateRejectedBuffers=").append(captureRenderGateRejectedBuffers)
                .append("\\nspeakerNeuralRenderGateNoAnchor=").append(captureRenderGateNoAnchor)
                .append("\\nspeakerNeuralRenderGateOwnerMismatch=").append(captureRenderGateOwnerMismatch)
                .append("\\nspeakerNeuralPcmFingerprintMode=fnv1a-64-over-64-evenly-spaced-bytes-no-copy")
                .append("\\nspeakerNeuralPcmFingerprintCalls=").append(captureFingerprintCalls)
                .append("\\nspeakerNeuralPcmFingerprintSameConsecutive=").append(captureFingerprintSameConsecutive)
                .append("\\nspeakerNeuralPcmFingerprintChanges=").append(captureFingerprintChanges)
                .append("\\nspeakerNeuralPcmFingerprintLast=").append(captureFingerprintLast)
                .append("\\nspeakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline")
''',
        "publish chained render-credit and fingerprint diagnostics",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.33.27 accepted-write PCM clock diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.28 render-clock PCM admission diagnostics\\n");',
        "update v2.33.28 diagnostics header",
    )
    rep(
        controller,
        '        report.append("audioVideoBridge=render-clock+accepted-write-accounting-active;pcm-admission-still-stride4\\n");\n'
        '        report.append("pcmAdmission=unchanged-sherpa-stride4-v23327-diagnostic-only\\n");\n',
        '        report.append("audioVideoBridge=render-clock+accepted-write-accounting+neural-render-credit-active\\n");\n'
        '        report.append("pcmAdmission=sherpa-render-credit-gate-v23328-shadow-no-live-diarizer-yet\\n");\n',
        "declare v2.33.28 render-credit admission active",
    )

    hook_text = hook.read_text(encoding="utf-8")
    player_text = player.read_text(encoding="utf-8")
    for needle in (
        "observeAudioTrackWriteRequestedForStudy(I)V",
        "observeAudioTrackWriteResultForStudy(I)V",
        "resultInstruction.opcode != Opcode.MOVE_RESULT",
    ):
        if needle not in hook_text:
            raise RuntimeError(f"required compiled write hook missing: {needle}")
    for needle in (
        "observeAudioTrackWriteRequestedForStudy(int requestedBytes)",
        "observeAudioTrackWriteResultForStudy(int result)",
    ):
        if needle not in player_text:
            raise RuntimeError(f"required write callback missing: {needle}")

    print("v2.33.28 chained-diagnostics finish complete")


if __name__ == "__main__":
    main()
