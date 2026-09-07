#!/usr/bin/env python3
"""Audit v2.33.1 Sherpa startup-isolation gate."""
from pathlib import Path
import sys


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2331_sherpa_startup_isolation.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()

    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    gradle = root / "extensions/youtube/build.gradle.kts"
    neural = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralDiarizer.java"
    seg = root / "extensions/youtube/src/main/assets/spanishstudy/sherpa/segmentation.onnx"
    emb = root / "extensions/youtube/src/main/assets/spanishstudy/sherpa/embedding.onnx"
    jni = root / "extensions/youtube/src/main/jniLibs/arm64-v8a"

    for p in (controller, player, gradle, seg, emb):
        require(p.is_file(), f"missing required file: {p}")
    require((jni / "libsherpa-onnx-jni.so").is_file(), "missing libsherpa-onnx-jni.so")
    require((jni / "libonnxruntime.so").is_file(), "missing libonnxruntime.so")

    c = controller.read_text(encoding="utf-8")
    p = player.read_text(encoding="utf-8")
    g = gradle.read_text(encoding="utf-8")

    require("Spanish Dub Study v2.33.1 Sherpa startup-isolation diagnostics" in c, "missing v2.33.1 header")
    require("speakerNeuralGate=v2.33.1-native-model-payload-only" in c, "missing gate diagnostic")
    require("speakerNeuralJavaApi=not-packaged-not-linked" in c, "missing Java isolation diagnostic")
    require("speakerNeuralNativeLoad=disabled" in c, "missing native-load isolation diagnostic")
    require("speakerNeuralPcmFeed=disabled" in c, "missing PCM isolation diagnostic")

    # This gate must have zero Java linkage to sherpa and zero native load calls.
    require(not neural.exists(), "SherpaNeuralDiarizer must not exist in startup gate")
    require("SherpaNeuralDiarizer" not in c, "controller directly references SherpaNeuralDiarizer")
    require("SherpaNeuralDiarizer" not in p, "PlayerVolumePatch directly references SherpaNeuralDiarizer")
    require("System.loadLibrary" not in c, "controller has native load call")
    require("System.loadLibrary" not in p, "PlayerVolumePatch has native load call")
    require("sherpa-onnx-1.13.7-classes.jar" not in g, "Sherpa Java API jar must not be a dependency")
    require('org.jetbrains.kotlin:kotlin-stdlib:1.7.20' not in g, "extra Kotlin stdlib must not be added")

    # Sacred Morphe batching constants remain stock.
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    t = translator.read_text(encoding="utf-8")
    require("OPENROUTER_MAX_BATCH_CHARS = 1_500" in t, "1500-char batch constant changed")
    require("OPENROUTER_FIRST_BATCH_CHARS = 350" in t, "350-char first-batch constant changed")

    require(seg.stat().st_size > 1_000_000, "segmentation model unexpectedly small")
    require(emb.stat().st_size > 10_000_000, "embedding model unexpectedly small")

    print("v2.33.1 startup-isolation audit passed")
    print("payload: ARM64 sherpa JNI + onnxruntime + segmentation/embedding models")
    print("runtime linkage: NONE; Java API/JNI load/PCM feed/inference disabled")


if __name__ == "__main__":
    main()
