#!/usr/bin/env python3
"""Prepare the v2.33.26 patch driver for generated v19 source shape.

The generated Stage-E/F/G/J body is intentionally left in source for audit/history, but a volatile
runtime gate makes it unreachable in practice without Java's compile-time unreachable-code rules.
The v19 Sherpa diagnostics are one chained StringBuilder expression, so this helper also rewrites
the initial driver diagnostics patch to match that exact source shape.
"""
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

    pt = player.read_text(encoding="utf-8")
    field_anchor = "    private static final AtomicReference<AudioTrack> lastAudioTrackRef = new AtomicReference<>(null);\n"
    if pt.count(field_anchor) != 1:
        raise RuntimeError("could not locate lastAudioTrackRef field")
    pt = pt.replace(field_anchor,
            field_anchor + "    private static volatile boolean studyLegacySpeakerDiarizationEnabled = false;\n", 1)
    player.write_text(pt, encoding="utf-8")
    print("prepared: volatile legacy speaker gate")

    text = driver.read_text(encoding="utf-8")
    old = '''        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        return;
        /* legacy Stage-E/F/G/J retained below for source history but unreachable */
        /*
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    new = '''        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        if (!studyLegacySpeakerDiarizationEnabled) return;
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    if text.count(old) != 1:
        raise RuntimeError("could not locate v2.33.26 retirement injection")
    text = text.replace(old, new, 1)

    pattern = re.compile(
        r'''    # Close the comment just before the method's final catch\..*?'''
        r'''    rep\(player, legacy_end, legacy_end_new, "close retired legacy PCM diarization source block"\)\n''',
        re.S,
    )
    text, n = pattern.subn("", text, count=1)
    if n != 1:
        raise RuntimeError("could not remove obsolete block-comment close patch")

    # The checked-in v19 Sherpa source emits diagnostics as one chained StringBuilder expression,
    # not separate out.append() statements. Replace the driver's original diagnostic patch block
    # with exact chained-expression anchors.
    diag_pattern = re.compile(
        r'''    diag_anchor = '''.*?'''
    rep\(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics"\)\n''',
        re.S,
    )
    diag_replacement = '''    diag_anchor = ''' + "'''" + '''                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)
                .append("\\nspeakerNeuralLiveBadgeAuthority=false-stage-j-remains-control")
'''+ "'''" + '''
    diag_insert = ''' + "'''" + '''                .append("\\nspeakerNeuralInferenceLastError=").append(inferenceError)
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
'''+ "'''" + '''
    rep(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics")
'''
    text, n = diag_pattern.subn(diag_replacement, text, count=1)
    if n != 1:
        raise RuntimeError("could not rewrite chained Sherpa diagnostic patch")

    # The same chained expression starts with a literal gate string, so make the gate replacement
    # accept the actual source rather than a separate out.append() statement.
    old_gate_patch = '''    rep(sherpa,
        '        out.append("speakerNeuralGate=v2.33.19-source-parity+stride4-only\\n");\\n',
        '        out.append("speakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection\\n");\\n',
        "update neural gate diagnostic")
'''
    new_gate_patch = '''    rep(sherpa,
        '.append("\\\\nspeakerNeuralGate=v2.33.19-source-parity+stride4-only")',
        '.append("\\\\nspeakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection")',
        "update neural gate diagnostic")
'''
    if text.count(old_gate_patch) != 1:
        raise RuntimeError("could not locate old neural gate patch")
    text = text.replace(old_gate_patch, new_gate_patch, 1)

    driver.write_text(text, encoding="utf-8")
    print("prepared: compile-safe v2.33.26 patch driver")
    print("prepared: chained Sherpa diagnostics/gate anchors")


if __name__ == "__main__":
    main()
