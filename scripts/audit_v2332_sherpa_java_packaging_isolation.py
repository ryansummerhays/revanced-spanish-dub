#!/usr/bin/env python3
"""Audit v2.33.2 Sherpa Java-packaging isolation gate."""
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2332_sherpa_java_packaging_isolation.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    ext = root / "extensions/youtube"
    gradle = ext / "build.gradle.kts"
    controller = ext / "src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    player = ext / "src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    jar = ext / "libs/sherpa-onnx-1.13.7-classes.jar"
    so1 = ext / "src/main/jniLibs/arm64-v8a/libsherpa-onnx-jni.so"
    so2 = ext / "src/main/jniLibs/arm64-v8a/libonnxruntime.so"
    seg = ext / "src/main/assets/spanishstudy/sherpa/segmentation.onnx"
    emb = ext / "src/main/assets/spanishstudy/sherpa/embedding.onnx"
    neural = ext / "src/main/java/app/spanishstudy/vot/SherpaNeuralDiarizer.java"

    for path in (gradle, controller, player, jar, so1, so2, seg, emb):
        if not path.is_file():
            raise RuntimeError(f"missing required v2.33.2 file: {path}")
    if neural.exists():
        raise RuntimeError("SherpaNeuralDiarizer.java must not exist in v2.33.2")

    g = gradle.read_text(encoding="utf-8")
    c = controller.read_text(encoding="utf-8")
    p = player.read_text(encoding="utf-8")

    need(g, 'implementation(files("libs/sherpa-onnx-1.13.7-classes.jar"))', "Sherpa classes.jar dependency")
    need(g, 'implementation("org.jetbrains.kotlin:kotlin-stdlib:1.7.20")', "Kotlin stdlib dependency")
    need(c, "Spanish Dub Study v2.33.2 Sherpa Java-packaging isolation diagnostics", "v2.33.2 header")
    need(c, "speakerNeuralGate=v2.33.2-java-api-packaged-unlinked", "v2.33.2 gate diagnostic")
    need(c, "speakerNeuralJavaApi=official-1.13.7-classes-jar-packaged-unlinked", "Java API diagnostic")
    need(c, "speakerNeuralNativeLoad=disabled", "native-load disabled diagnostic")
    need(c, "speakerNeuralPcmFeed=disabled", "PCM disabled diagnostic")
    need(c, "speakerNeuralInference=disabled-java-packaging-gate", "inference disabled diagnostic")

    # Startup-hot runtime code must contain no static/direct link to the new backend.
    for text, name in ((p, "PlayerVolumePatch"), (c, "SpanishStudyController")):
        forbid(text, "SherpaNeuralDiarizer", f"direct Sherpa bridge reference in {name}")
        forbid(text, "com.k2fsa.sherpa", f"direct official Sherpa reference in {name}")
        forbid(text, "System.loadLibrary", f"JNI load call in {name}")

    # Make sure the proven Stage-J runtime remains present.
    need(p, "resetSpeakerAnalysisForStudy", "Stage-J reset")
    need(p, "getSpeakerClusterCommittedForStudy", "Stage-G/H committed cluster access")

    print("v2.33.2 audit PASS")
    print("PASS: native/model payload present")
    print("PASS: official Sherpa classes.jar + Kotlin stdlib configured")
    print("PASS: no Sherpa bridge source, no direct runtime class reference, no System.loadLibrary")
    print("PASS: Stage-J speaker runtime remains the only live authority")


if __name__ == "__main__":
    main()
