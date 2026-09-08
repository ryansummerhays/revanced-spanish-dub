#!/usr/bin/env python3
"""Prepare the v2.33.26 driver and patch v19 chained diagnostics directly."""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_v23326_driver.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    sherpa = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    driver = repo / "scripts/patch_v23326_neural_absolute_timeline.py"

    # Runtime-disable the legacy Stage-E/F/G/J body without compile-time unreachable Java.
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

    # Patch the actual v19 chained StringBuilder diagnostics before the main v26 driver adds the
    # referenced fields. This avoids pretending the diagnostics use separate out.append calls.
    nt = sherpa.read_text(encoding="utf-8")
    old_diag = (
        '                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)\n'
        '                .append("\\nspeakerNeuralLiveBadgeAuthority=false-stage-j-remains-control")\n'
    )
    new_diag = (
        '                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)\n'
        '                .append("\\nspeakerNeuralCaptureVideoEpoch=").append(captureVideoEpoch)\n'
        '                .append("\\nspeakerNeuralCaptureContinuityEpoch=").append(captureContinuityEpoch)\n'
        '                .append("\\nspeakerNeuralCaptureStartVideoMs=").append(captureStartVideoMs)\n'
        '                .append("\\nspeakerNeuralCaptureEndVideoMs=").append(captureEndVideoMs)\n'
        '                .append("\\nspeakerNeuralAbsoluteTimelineValid=").append(absoluteTimelineValid)\n'
        '                .append("\\nspeakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse")\n'
        '                .append("\\nspeakerNeuralAbsoluteScalePermille=").append(absoluteTimelineScalePermille)\n'
        '                .append("\\nspeakerNeuralAbsoluteSegments=").append(absoluteSegmentCount)\n'
        '                .append("\\nspeakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary)\n'
        '                .append("\\nspeakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline")\n'
    )
    if nt.count(old_diag) != 1:
        raise RuntimeError(f"could not locate chained Sherpa diagnostics: {nt.count(old_diag)}")
    nt = nt.replace(old_diag, new_diag, 1)

    old_gate = '.append("\\nspeakerNeuralGate=v2.33.19-source-parity+stride4-only")'
    new_gate = '.append("\\nspeakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection")'
    if nt.count(old_gate) != 1:
        raise RuntimeError(f"could not locate chained Sherpa gate: {nt.count(old_gate)}")
    nt = nt.replace(old_gate, new_gate, 1)
    sherpa.write_text(nt, encoding="utf-8")
    print("prepared: v2.33.26 chained Sherpa diagnostics/gate")

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

    # Remove the obsolete block-comment closing patch.
    block_start = text.find("    # Close the comment just before the method's final catch.")
    block_end_marker = '    rep(player, legacy_end, legacy_end_new, "close retired legacy PCM diarization source block")\n'
    if block_start < 0:
        raise RuntimeError("could not locate obsolete block-comment patch start")
    block_end = text.find(block_end_marker, block_start)
    if block_end < 0:
        raise RuntimeError("could not locate obsolete block-comment patch end")
    block_end += len(block_end_marker)
    text = text[:block_start] + text[block_end:]

    # Diagnostics and gate were just patched directly on the exact source. Remove the obsolete
    # generic driver blocks so they cannot fail on source-shape assumptions.
    diag_start = text.find("    diag_anchor = '''")
    diag_end_marker = '    rep(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics")\n'
    if diag_start < 0:
        raise RuntimeError("could not locate obsolete diagnostic patch start")
    diag_end = text.find(diag_end_marker, diag_start)
    if diag_end < 0:
        raise RuntimeError("could not locate obsolete diagnostic patch end")
    diag_end += len(diag_end_marker)
    text = text[:diag_start] + text[diag_end:]

    gate_start = text.find("    # The v19 gate string should no longer imply Stage-J is the intended next authority.")
    gate_end_marker = '        "update neural gate diagnostic")\n'
    if gate_start < 0:
        raise RuntimeError("could not locate obsolete gate patch start")
    gate_end = text.find(gate_end_marker, gate_start)
    if gate_end < 0:
        raise RuntimeError("could not locate obsolete gate patch end")
    gate_end += len(gate_end_marker)
    text = text[:gate_start] + text[gate_end:]

    driver.write_text(text, encoding="utf-8")
    print("prepared: compile-safe v2.33.26 patch driver")


if __name__ == "__main__":
    main()
