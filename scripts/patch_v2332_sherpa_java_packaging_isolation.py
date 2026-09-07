#!/usr/bin/env python3
"""v2.33.2: package Sherpa Java/Kotlin API without runtime linkage.

This sits on top of v2.33.1, which proved that the ARM64 native runtime and both ONNX models can
be packaged without causing the pre-loading startup crash. v2.33.2 adds only the official
sherpa-onnx classes.jar plus the Kotlin stdlib it expects. No runtime Java source is allowed to
reference Sherpa, no System.loadLibrary call is added, and no PCM/inference path is enabled.

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
        raise SystemExit("usage: patch_v2332_sherpa_java_packaging_isolation.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    gradle = root / "extensions/youtube/build.gradle.kts"
    if not controller.is_file() or not gradle.is_file():
        raise RuntimeError("missing v2.33.1 source tree")

    rep(
        gradle,
        "    implementation(libs.protobuf.javalite)\n",
        "    implementation(libs.protobuf.javalite)\n"
        "    // Spanish Dub Study v2.33.2: package official Sherpa API, but do not link it from runtime code.\n"
        "    implementation(files(\"libs/sherpa-onnx-1.13.7-classes.jar\"))\n"
        "    implementation(\"org.jetbrains.kotlin:kotlin-stdlib:1.7.20\")\n",
        "package official Sherpa Java/Kotlin API",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.33.1 Sherpa startup-isolation diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.2 Sherpa Java-packaging isolation diagnostics\\n");',
        "update v2.33.2 diagnostics header",
    )

    old = (
        '        report.append("speakerNeuralGate=v2.33.1-native-model-payload-only\\n");\n'
        '        report.append("speakerNeuralJavaApi=not-packaged-not-linked\\n");\n'
        '        report.append("speakerNeuralClassReference=none\\n");\n'
        '        report.append("speakerNeuralNativeLoad=disabled\\n");\n'
        '        report.append("speakerNeuralPcmFeed=disabled\\n");\n'
        '        report.append("speakerNeuralInference=disabled-startup-safety-gate\\n");\n'
        '        report.append("speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control\\n");\n'
    )
    new = (
        '        report.append("speakerNeuralGate=v2.33.2-java-api-packaged-unlinked\\n");\n'
        '        report.append("speakerNeuralJavaApi=official-1.13.7-classes-jar-packaged-unlinked\\n");\n'
        '        report.append("speakerNeuralKotlinRuntime=stdlib-1.7.20-packaged-unlinked\\n");\n'
        '        report.append("speakerNeuralClassReference=none-from-runtime-code\\n");\n'
        '        report.append("speakerNeuralNativeLoad=disabled\\n");\n'
        '        report.append("speakerNeuralPcmFeed=disabled\\n");\n'
        '        report.append("speakerNeuralInference=disabled-java-packaging-gate\\n");\n'
        '        report.append("speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control\\n");\n'
    )
    rep(controller, old, new, "publish Java-packaging isolation diagnostics")

    print("v2.33.2 Sherpa Java-packaging isolation patch complete")
    print("ADDED: official Sherpa classes.jar and Kotlin stdlib as packaged dependencies")
    print("NOT ADDED: Sherpa bridge class, direct class reference, JNI load, PCM feed, worker, inference")
    print("UNCHANGED: PlayerVolumePatch and all translation/subtitle/TTS behavior")


if __name__ == "__main__":
    main()
