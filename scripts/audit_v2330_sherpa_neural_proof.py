#!/usr/bin/env python3
"""Static audit for v2.33.0 sherpa-onnx neural diarization proof."""
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2330_sherpa_neural_proof.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    neural = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralDiarizer.java"
    gradle = root / "extensions/youtube/build.gradle.kts"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    for p in (player, controller, neural, gradle, translator, fetcher):
        if not p.is_file():
            raise RuntimeError(f"missing required file: {p}")

    pt = player.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    nt = neural.read_text(encoding="utf-8")
    gt = gradle.read_text(encoding="utf-8")
    tt = translator.read_text(encoding="utf-8")

    need(gt, 'implementation(files("libs/sherpa-onnx-1.13.7-classes.jar"))', "sherpa classes dependency")
    need(gt, 'implementation("org.jetbrains.kotlin:kotlin-stdlib:1.7.20")', "Kotlin runtime dependency")
    need(pt, "SherpaNeuralDiarizer.observePcmBuffer", "neural PCM feed")
    need(pt, "SherpaNeuralDiarizer.resetForNewVideo", "per-video neural reset")
    need(nt, "PROOF_SECONDS = 20", "bounded 20-second proof")
    need(nt, "p += 12", "48k stereo to 16k decimation")
    need(nt, 'System.loadLibrary("onnxruntime")', "onnxruntime load")
    need(nt, 'System.loadLibrary("sherpa-onnx-jni")', "sherpa JNI load")
    need(nt, 'SEGMENTATION_ASSET = "spanishstudy/sherpa/segmentation.onnx"', "segmentation asset")
    need(nt, 'EMBEDDING_ASSET = "spanishstudy/sherpa/embedding.onnx"', "embedding asset")
    need(nt, 'new Thread(() -> runProof', "background inference")
    need(nt, 'FastClusteringConfig', "automatic clustering config reflection")
    need(nt, 'newInstance(-1, 0.5f)', "automatic speaker count")
    need(ct, "speakerNeuralBackend=sherpa-onnx-pyannote3+eres2net-one-shot-proof", "neural diagnostics")
    need(ct, "speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control", "Stage-J control declaration")

    # Sacred translation packetization must remain native.
    need(tt, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "native 1500-char packet cap")
    need(tt, "OPENROUTER_FIRST_BATCH_CHARS = 350", "native 350-char first batch")
    need(fetcher.read_text(encoding="utf-8"), "mergeIntoSentences", "native sentence merge")

    # This proof must not route voices or replace the live subtitle badge authority.
    if "setVoice" in nt or "MediaPlayer" in nt or "SpanishSubtitleOverlay" in nt:
        raise RuntimeError("neural proof unexpectedly touches voice/subtitle routing")

    print("v2.33.0 sherpa neural proof audit PASS")
    print("verified: official JNI/model proof is parallel to Stage-J live badges")
    print("verified: 20 s bounded collection, 48k stereo PCM16 -> 16k mono, background inference")
    print("verified: native Morphe mergeIntoSentences and OpenRouter 1500/350 packetization retained")


if __name__ == "__main__":
    main()
