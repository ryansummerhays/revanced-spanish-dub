#!/usr/bin/env python3
"""Audit v2.33.27 source reconstruction of the hidden Sherpa payload resource patch."""
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23327_neural_payload_source.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.kt"
    payload = pkg / "SpeakerNeuralPayloadPatch.kt"
    for p in (vot, payload):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.27 neural payload source: {p}")

    vt = vot.read_text(encoding="utf-8")
    pt = payload.read_text(encoding="utf-8")

    require(vt, "speakerNeuralPayloadPatch,", "VOT dependency on hidden neural payload patch")
    require(pt, "rawResourcePatch", "raw resource patch type")
    require(pt, 'copyResources(', "resource copier")
    require(pt, '"spanishstudysherpa"', "bundled raw resource root")
    for name in (
        "spanishstudy_sherpa_segmentation.onnx",
        "spanishstudy_sherpa_embedding.onnx",
        "spanishstudy_sherpa_onnxruntime.so",
        "spanishstudy_sherpa_jni.so",
    ):
        require(pt, f'"{name}"', f"payload {name}")

    print("PASS v2.33.27 neural payload source audit")
    print("VOT depends on hidden raw-resource patch and all four established Sherpa payload names are present")


if __name__ == "__main__":
    main()
