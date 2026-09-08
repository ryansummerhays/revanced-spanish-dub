#!/usr/bin/env python3
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
        raise SystemExit("usage: audit_v23319_sherpa_source_parity.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    player = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text()
    controller = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java").read_text()
    shadow_path = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    if not shadow_path.is_file(): raise RuntimeError("SherpaNeuralShadow.java missing")
    shadow = shadow_path.read_text()
    gradle = (root / "extensions/youtube/build.gradle.kts").read_text()

    require(gradle, 'implementation(files("libs/sherpa-onnx-1.13.7-classes.jar"))', "Sherpa compile/runtime Java API")
    require(player, 'SherpaNeuralShadow.observePcmTrigger()', "first-PCM trigger")
    require(player, 'SherpaNeuralShadow.observePcmBuffer(', "direct PCM feed")
    require(player, 'SherpaNeuralShadow.resetCaptureForVideo()', "per-video neural reset")
    require(controller, 'SherpaNeuralShadow.provideContext(activity)', "main-thread context bridge")
    require(controller, 'report.append(SherpaNeuralShadow.diagnostics())', "neural diagnostics")

    require(shadow, 'if (local == null || state != STATE_READY)', "inference READY gate")
    require(shadow, 'if (epoch != captureEpoch) return;', "epoch invalidation")
    require(shadow, 'if ((((int) captureBuffers) & 3) != 0) return;', "temporary stride-4 containment")
    require(shadow, 'CAPTURE_TARGET_SAMPLES = TARGET_SAMPLE_RATE * CAPTURE_SECONDS', "bounded capture")
    require(shadow, 'worker.setPriority(Thread.MIN_PRIORITY)', "low-priority inference")
    require(shadow, 'System.load(onnx.getAbsolutePath())', "absolute ONNX load")
    require(shadow, 'System.load(sherpa.getAbsolutePath())', "absolute Sherpa JNI load")
    require(shadow, 'openRawResource', "res/raw transport")

    # Android AAR constructor is (AssetManager?, Config). The extracted ONNX paths are absolute,
    # so AssetManager MUST be null to select Sherpa JNI newFromFile rather than newFromAsset.
    require(shadow, 'Class<?> assetManagerClass = Class.forName("android.content.res.AssetManager")', "Android AAR nullable AssetManager type")
    require(shadow, 'Constructor<?> diarizerCtor = diarizerCls.getConstructor(assetManagerClass, cfgCls);', "Android AAR JVM constructor")
    require(shadow, 'diarizerCtor.newInstance(null, config)', "null AssetManager file-backed Sherpa model creation")
    require(shadow, 'Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig")', "reflected config API")
    forbid(shadow, 'diarizerCtor.newInstance(assets, config)', "non-null AssetManager with absolute model paths")

    # Public runtime API stays directly typed so R8 cannot prune native process/result methods.
    require(shadow, 'import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization;', "typed diarizer runtime API")
    require(shadow, 'import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationSegment;', "typed segment runtime API")
    require(shadow, 'OfflineSpeakerDiarizationSegment[] result = local.process(input);', "direct native process bridge")
    require(shadow, 'int speaker = s.getSpeaker();', "direct speaker getter")
    require(shadow, 'float start = s.getStart();', "direct start getter")
    require(shadow, 'float end = s.getEnd();', "direct end getter")
    forbid(shadow, 'pyannote.model =', "private config field access")
    forbid(shadow, 'config.segmentation =', "private config field access")

    forbid(shadow, 'VideoInformation.', "player API on neural path")
    forbid(shadow, 'getVideoTime(', "direct video-time read on neural path")
    forbid(shadow, 'interrupt()', "native worker interruption")

    require(player, '// Neural shadow must never escape onto ExoPlayer\'s audio thread.', "audio-thread containment")

    print("PASS v2.33.19 source-parity audit")
    print("READY gate, epoch invalidation, bounded capture, stride-4 containment and Sherpa JNI result surface preserved")
    print("PASS absolute-path model constructor: nullable AssetManager JVM ctor invoked with null => newFromFile")


if __name__ == "__main__":
    main()
