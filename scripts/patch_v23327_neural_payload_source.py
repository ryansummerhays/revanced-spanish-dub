#!/usr/bin/env python3
"""Restore the installable Sherpa raw-resource patch in source for v2.33.27.

v2.33.25/v2.33.26 installable MPPs contain a hidden raw-resource dependency that copies all four
Sherpa runtime payload files into the patched YouTube APK. The ordinary source replay used for
v2.33.27 did not contain that custom patch, so replacing the top-level compiled patch DEX without
restoring it would make the resulting MPP unable to install the ONNX/native payload resources.

This source-level reconstruction deliberately copies all four files from the already-established
`spanishstudysherpa/raw` bundled resource group. The final installable MPP is assembled on the
proven v2.33.26 package so those exact payload bytes remain unchanged.
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
        raise SystemExit("usage: patch_v23327_neural_payload_source.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.kt"
    payload = pkg / "SpeakerNeuralPayloadPatch.kt"
    if not vot.is_file():
        raise RuntimeError(f"missing VoiceOverTranslationPatch source: {vot}")

    payload.write_text('''package app.morphe.patches.youtube.video.voiceovertranslation

import app.morphe.patcher.patch.rawResourcePatch
import app.morphe.util.ResourceGroup
import app.morphe.util.copyResources

/**
 * Hidden dependency for Spanish Dub Study's local neural speaker backend.
 *
 * All four payloads are copied as ordinary APK raw resources. Runtime code then resolves those
 * resource IDs, extracts the files into app-private storage, and loads Sherpa/ONNX from absolute
 * filesystem paths. No network/model download occurs on the device.
 */
internal val speakerNeuralPayloadPatch = rawResourcePatch {
    execute {
        copyResources(
            "spanishstudysherpa",
            ResourceGroup(
                "raw",
                "spanishstudy_sherpa_segmentation.onnx",
                "spanishstudy_sherpa_embedding.onnx",
                "spanishstudy_sherpa_onnxruntime.so",
                "spanishstudy_sherpa_jni.so",
            )
        )
    }
}
''', encoding="utf-8")
    print("created:", payload)

    dep_anchor = '''        legacyPlayerControlsPatch,
        voiceOverTranslationResourcePatch,
        playerVolumeHookPatch
'''
    dep_insert = '''        legacyPlayerControlsPatch,
        voiceOverTranslationResourcePatch,
        speakerNeuralPayloadPatch,
        playerVolumeHookPatch
'''
    rep(vot, dep_anchor, dep_insert, "wire hidden Sherpa payload resource patch into VOT dependency graph")

    print("v2.33.27 neural payload source reconstruction complete")
    print("PAYLOAD NAMES: segmentation, embedding, onnxruntime, sherpa-jni")
    print("FINAL PACKAGE POLICY: preserve exact v2.33.26 payload bytes; replace only compiled patch/runtime entries")


if __name__ == "__main__":
    main()
