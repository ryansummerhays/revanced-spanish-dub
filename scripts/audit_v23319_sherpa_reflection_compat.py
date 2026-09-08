#!/usr/bin/env python3
"""Audit that the source-parity Sherpa wrapper uses the Android AAR API safely."""
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
        raise SystemExit("usage: audit_v23319_sherpa_reflection_compat.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    path = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    text = path.read_text(encoding="utf-8")

    require(text, 'Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization")', "reflected diarizer")
    require(text, 'getConstructor(assetManagerClass, cfgCls)', "Android AssetManager constructor")
    require(text, 'getMethod("process", float[].class)', "reflected process")
    require(text, 'getMethod("getSpeaker")', "segment speaker getter")
    require(text, 'getMethod("getStart")', "segment start getter")
    require(text, 'getMethod("getEnd")', "segment end getter")
    require(text, 'if (local == null || process == null || state != STATE_READY)', "READY/null inference gate")
    require(text, 'if (epoch != captureEpoch) return;', "epoch invalidation")
    require(text, 'if ((((int) captureBuffers) & 3) != 0) return;', "v19 stride4 containment")
    require(text, 'CAPTURE_TARGET_SAMPLES = TARGET_SAMPLE_RATE * CAPTURE_SECONDS', "bounded capture")
    require(text, 'Thread.MIN_PRIORITY', "low-priority inference worker")

    for field in (
        'pyannote.model =', 'segmentationConfig.pyannote =', 'embeddingConfig.model =',
        'clustering.threshold =', 'config.segmentation =', 's.speaker', 's.start', 's.end'):
        forbid(text, field, "incompatible direct Android-AAR field access")
    forbid(text, 'new OfflineSpeakerDiarization(config)', "wrong one-argument Android constructor")
    forbid(text, 'import com.k2fsa.sherpa.onnx.', "compile-time Sherpa implementation import")

    print("v2.33.19 Sherpa Android-AAR reflection compatibility audit OK")
    print("retained: READY gate, epoch invalidation, 320k bounded capture, stride4, dedicated worker")


if __name__ == "__main__":
    main()
