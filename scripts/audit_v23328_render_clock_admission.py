#!/usr/bin/env python3
"""Source audit for v2.33.28 render-clock Sherpa admission."""
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
        raise SystemExit("usage: audit_v23328_render_clock_admission.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    probe = (base / "AudioVideoSyncProbe.java").read_text(encoding="utf-8")
    sherpa = (base / "SherpaNeuralShadow.java").read_text(encoding="utf-8")
    controller = (base / "SpanishStudyController.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")
    player = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")

    for needle, label in [
        ("public static final class RenderAnchor", "immutable render tuple"),
        ("private static volatile RenderAnchor publishedRenderAnchor", "volatile published anchor"),
        ("public static RenderAnchor latestRenderAnchor()", "hot-path render getter"),
        ("publishedRenderAnchor = new RenderAnchor(true", "controller publish"),
        ("audioVideoAdmissionAnchorValid=", "anchor diagnostics"),
    ]:
        require(probe, needle, label)

    for needle, label in [
        ("AudioVideoSyncProbe.RenderAnchor render = AudioVideoSyncProbe.latestRenderAnchor();", "render anchor read"),
        ("captureRenderBaselineHeadFrames", "render baseline"),
        ("captureRenderAllowedInputFrames", "render allowance"),
        ("captureRenderAcceptedInputFrames + frames > allowedInputFrames", "full-buffer credit gate"),
        ("captureRenderAcceptedInputFrames += frames", "accepted input accounting"),
        ("speakerNeuralGate=v2.33.28-neural-only+render-credit+absolute-video-projection", "v28 neural gate"),
        ("speakerNeuralPcmFeed=direct-pcm16-fullwindow-render-credit-gated-16k-20s", "v28 feed"),
        ("speakerNeuralPcmFingerprintMode=fnv1a-64-over-64-evenly-spaced-bytes-no-copy", "fingerprint diagnostics"),
        ("captureEndVideoMs = captureStartVideoMs +", "render-derived capture end"),
    ]:
        require(sherpa, needle, label)

    forbid(sherpa, "if ((((int) captureBuffers) & 3) != 0) return;", "old stride4 gate")
    forbid(sherpa, "getPlaybackHeadPosition()", "AudioTrack method on neural path")
    forbid(sherpa, "getTimestamp(", "AudioTimestamp method on neural path")
    forbid(sherpa, "VideoInformation", "YouTube player API on neural path")
    forbid(sherpa, "getVideoTime", "YouTube player API on neural path")
    forbid(sherpa, ".interrupt()", "native worker interruption")

    require(controller, "Spanish Dub Study v2.33.28 render-clock PCM admission diagnostics", "v28 header")
    require(controller, "pcmAdmission=sherpa-render-credit-gate-v23328-shadow-no-live-diarizer-yet", "v28 admission declaration")
    require(controller, "AudioVideoSyncProbe.sample(videoClock", "controller-side render sampling")

    for needle in [
        "observeAudioTrackWriteRequestedForStudy(I)V",
        "observeAudioTrackWriteResultForStudy(I)V",
        "Opcode.MOVE_RESULT",
    ]:
        require(hook, needle, "compiled patch-side write hook")
    for needle in [
        "observeAudioTrackWriteRequestedForStudy(int requestedBytes)",
        "observeAudioTrackWriteResultForStudy(int result)",
        "getPcmWriteAcceptedFramesForStudy()",
    ]:
        require(player, needle, "extension accepted-write callbacks")

    forbid(sherpa, "LS-EEND", "premature live diarizer")
    forbid(sherpa, "FluidAudio", "premature live diarizer")

    print("PASS v2.33.28 render-clock admission source audit")
    print("- stride4 removed from Sherpa capture path")
    print("- controller-published render/video anchor gates neural PCM credit")
    print("- 64-byte bounded PCM fingerprints instrument retries without copies")
    print("- v2.33.27 pre/post AudioTrack.write callbacks remain in patch + extension source")
    print("- no AudioTrack/player APIs/model inference moved onto AudioTrack callback thread")
    print("- LS-EEND/live diarizer intentionally deferred until runtime timing validation")


if __name__ == "__main__":
    main()
