#!/usr/bin/env python3
"""Prepare the v2.33.26 patch driver for generated v19 source shape."""
from pathlib import Path
import re
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_v23326_driver.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    driver = repo / "scripts/patch_v23326_neural_absolute_timeline.py"

    # Runtime-disable the legacy Stage-E/F/G/J body without making Java reject the source as
    # compile-time unreachable. This field is intentionally private and never written true.
    pt = player.read_text(encoding="utf-8")
    field_anchor = "    private static final AtomicReference<AudioTrack> lastAudioTrackRef = new AtomicReference<>(null);\n"
    if pt.count(field_anchor) != 1:
        raise RuntimeError("could not locate lastAudioTrackRef field")
    pt = pt.replace(
        field_anchor,
        field_anchor + "    private static volatile boolean studyLegacySpeakerDiarizationEnabled = false;\n",
        1,
    )
    player.write_text(pt, encoding="utf-8")
    print("prepared: volatile legacy speaker gate")

    text = driver.read_text(encoding="utf-8")

    old_retire = """        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        return;
        /* legacy Stage-E/F/G/J retained below for source history but unreachable */
        /*
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
"""
    new_retire = """        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        if (!studyLegacySpeakerDiarizationEnabled) return;
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
"""
    if text.count(old_retire) != 1:
        raise RuntimeError("could not locate v2.33.26 retirement injection")
    text = text.replace(old_retire, new_retire, 1)

    # Remove the now-obsolete block-comment closing patch from the checked-in driver.
    block_start = text.find("    # Close the comment just before the method's final catch.")
    block_end_marker = '    rep(player, legacy_end, legacy_end_new, "close retired legacy PCM diarization source block")\n'
    if block_start < 0:
        raise RuntimeError("could not locate obsolete block-comment patch start")
    block_end = text.find(block_end_marker, block_start)
    if block_end < 0:
        raise RuntimeError("could not locate obsolete block-comment patch end")
    block_end += len(block_end_marker)
    text = text[:block_start] + text[block_end:]

    # The v19 Sherpa diagnostics are one chained StringBuilder expression. Replace the driver's
    # separate out.append() patch with an exact chained-expression patch.
    diag_start = text.find("    diag_anchor = '''")
    diag_end_marker = '    rep(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics")\n'
    if diag_start < 0:
        raise RuntimeError("could not locate diagnostic patch start")
    diag_end = text.find(diag_end_marker, diag_start)
    if diag_end < 0:
        raise RuntimeError("could not locate diagnostic patch end")
    diag_end += len(diag_end_marker)
    diag_replacement = """    diag_anchor = '''                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)
                .append("\\nspeakerNeuralLiveBadgeAuthority=false-stage-j-remains-control")
'''
    diag_insert = '''                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)
                .append("\\nspeakerNeuralCaptureVideoEpoch=").append(captureVideoEpoch)
                .append("\\nspeakerNeuralCaptureContinuityEpoch=").append(captureContinuityEpoch)
                .append("\\nspeakerNeuralCaptureStartVideoMs=").append(captureStartVideoMs)
                .append("\\nspeakerNeuralCaptureEndVideoMs=").append(captureEndVideoMs)
                .append("\\nspeakerNeuralAbsoluteTimelineValid=").append(absoluteTimelineValid)
                .append("\\nspeakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse")
                .append("\\nspeakerNeuralAbsoluteScalePermille=").append(absoluteTimelineScalePermille)
                .append("\\nspeakerNeuralAbsoluteSegments=").append(absoluteSegmentCount)
                .append("\\nspeakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary)
                .append("\\nspeakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline")
'''
    rep(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics")
"""
    text = text[:diag_start] + diag_replacement + text[diag_end:]

    gate_start_marker = "    # The v19 gate string should no longer imply Stage-J is the intended next authority.\n"
    gate_start = text.find(gate_start_marker)
    gate_end_marker = '        "update neural gate diagnostic")\n'
    if gate_start < 0:
        raise RuntimeError("could not locate gate patch start")
    gate_end = text.find(gate_end_marker, gate_start)
    if gate_end < 0:
        raise RuntimeError("could not locate gate patch end")
    gate_end += len(gate_end_marker)
    gate_replacement = """    # The v19 diagnostics are a chained StringBuilder expression.
    rep(sherpa,
        '.append("\\\\nspeakerNeuralGate=v2.33.19-source-parity+stride4-only")',
        '.append("\\\\nspeakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection")',
        "update neural gate diagnostic")
"""
    text = text[:gate_start] + gate_replacement + text[gate_end:]

    driver.write_text(text, encoding="utf-8")
    print("prepared: compile-safe v2.33.26 patch driver")
    print("prepared: chained Sherpa diagnostics/gate anchors")


if __name__ == "__main__":
    main()
