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

    require(shadow, 'if (local == null || process == null || state != STATE_READY)', "inference READY gate")
    require(shadow, 'if (epoch != captureEpoch) return;', "epoch invalidation")
    require(shadow, 'if ((((int) captureBuffers) & 3) != 0) return;', "temporary stride-4 containment")
    require(shadow, 'CAPTURE_TARGET_SAMPLES = TARGET_SAMPLE_RATE * CAPTURE_SECONDS', "bounded capture")
    require(shadow, 'worker.setPriority(Thread.MIN_PRIORITY)', "low-priority inference")
    require(shadow, 'System.load(onnx.getAbsolutePath())', "absolute ONNX load")
    require(shadow, 'System.load(sherpa.getAbsolutePath())', "absolute Sherpa JNI load")
    require(shadow, 'openRawResource', "res/raw transport")
    require(shadow, 'getConstructor(assetManagerClass, cfgCls)', "Android AAR AssetManager constructor")
    require(shadow, 'getMethod("process", float[].class)', "reflected process method")
    require(shadow, 'getMethod("getSpeaker")', "reflected segment getter")
    forbid(shadow, 'import com.k2fsa.sherpa.onnx.', "direct Sherpa implementation imports")
    forbid(shadow, 'VideoInformation.', "player API on neural path")
    forbid(shadow, 'getVideoTime(', "direct video-time read on neural path")
    forbid(shadow, 'interrupt()', "native worker interruption")

    # The hot AudioTrack observer must remain fail-soft around the neural handoff.
    require(player, '// Neural shadow must never escape onto ExoPlayer\'s audio thread.', "audio-thread containment")

    print("PASS v2.33.19 source-parity audit")
    print("READY gate, epoch invalidation, bounded capture, stride-4 containment, res/raw loading and Android-AAR reflection preserved")


if __name__ == "__main__":
    main()
