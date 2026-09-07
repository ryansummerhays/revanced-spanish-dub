#!/usr/bin/env python3
"""v2.33.1: Sherpa startup-isolation gate on top of known Stage J.

This intentionally does NOT link or execute sherpa Java/JNI code. The build may package the
ARM64 sherpa native runtime and two ONNX model assets, but runtime code remains Stage J.
The purpose is to distinguish payload/packaging startup safety from Java class-linkage safety.

UNCHANGED: PlayerVolumePatch, AudioTrack PCM hook, Stage-E/F/G analysis, Stage-H/I/J behavior,
Morphe segmentation, OpenRouter 1500/350 packetization/order, subtitles, and Edge TTS.
"""
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
        raise SystemExit("usage: patch_v2331_sherpa_startup_isolation.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    if not controller.is_file():
        raise RuntimeError(f"missing Stage-J controller: {controller}")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.12 Stage-J per-video-speaker-reset diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.1 Sherpa startup-isolation diagnostics\\n");',
        "update v2.33.1 diagnostics header",
    )

    anchor = '        report.append("speakerAnalysisResetInProgress=").append(PlayerVolumePatch.isSpeakerAnalysisResetInProgressForStudy()).append(\'\\n\');\n'
    insert = anchor + (
        '        report.append("speakerNeuralGate=v2.33.1-native-model-payload-only\\n");\n'
        '        report.append("speakerNeuralJavaApi=not-packaged-not-linked\\n");\n'
        '        report.append("speakerNeuralClassReference=none\\n");\n'
        '        report.append("speakerNeuralNativeLoad=disabled\\n");\n'
        '        report.append("speakerNeuralPcmFeed=disabled\\n");\n'
        '        report.append("speakerNeuralInference=disabled-startup-safety-gate\\n");\n'
        '        report.append("speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control\\n");\n'
    )
    rep(controller, anchor, insert, "publish startup-isolation diagnostics")

    print("v2.33.1 Sherpa startup-isolation patch complete")
    print("ADDED: static diagnostics only")
    print("NOT ADDED: Sherpa Java classes, Kotlin dependency, JNI load calls, PCM feed, worker, inference")
    print("UNCHANGED: PlayerVolumePatch and all translation/subtitle/TTS behavior")


if __name__ == "__main__":
    main()
