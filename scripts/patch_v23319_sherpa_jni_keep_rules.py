#!/usr/bin/env python3
"""Preserve the Android Sherpa JNI ABI through R8.

Sherpa's native code looks up configuration fields by their exact Java names and constructs
OfflineSpeakerDiarizationSegment with the exact (float,float,int) constructor. Those references
are invisible to R8, so a normal minified extension must explicitly keep this small JNI surface.
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
        raise SystemExit("usage: patch_v23319_sherpa_jni_keep_rules.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    gradle = root / "extensions/youtube/build.gradle.kts"
    rules = root / "extensions/youtube/spanishstudy-sherpa-jni.pro"
    if not gradle.is_file():
        raise RuntimeError(f"missing YouTube Gradle file: {gradle}")

    rules.write_text(r'''# Spanish Dub Study: sherpa-onnx 1.13.7 Android JNI ABI.
# Native code uses FindClass/GetFieldID/GetMethodID with these exact names/signatures.
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization { *; }
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization$Companion { *; }
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationSegment { *; }
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig { *; }
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationModelConfig { *; }
-keep class com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationPyannoteModelConfig { *; }
-keep class com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig { *; }
-keep class com.k2fsa.sherpa.onnx.FastClusteringConfig { *; }
''', encoding="utf-8")
    print("created:", rules)

    rep(
        gradle,
        "configure<ApplicationExtension> {\n    defaultConfig {\n        minSdk = 26\n    }\n}\n",
        "configure<ApplicationExtension> {\n"
        "    defaultConfig {\n"
        "        minSdk = 26\n"
        "    }\n"
        "    buildTypes {\n"
        "        getByName(\"release\") {\n"
        "            proguardFiles(\"spanishstudy-sherpa-jni.pro\")\n"
        "        }\n"
        "    }\n"
        "}\n",
        "attach Sherpa JNI keep rules to release R8",
    )

    print("v2.33.19 Sherpa JNI keep rules installed")
    print("KEPT: native class names, config field names, segment (FFI)V ctor/getters, process/sampleRate bridge")


if __name__ == "__main__":
    main()
