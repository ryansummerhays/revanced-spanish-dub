#!/usr/bin/env python3
"""v2.33.31: near-live ERes2Net speaker identity over exact accepted PCM/videoMs.

Builds on v2.33.30 without touching the proven target AudioTrack.write hook shape.
The verifier-safe int-only post-write callback and ThreadLocal ByteBuffer handoff remain unchanged.
"""
from pathlib import Path
import shutil
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def require(path: Path, needle: str, label: str) -> None:
    if needle not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"{label}: missing {needle!r} in {path}")


def forbid(path: Path, needle: str, label: str) -> None:
    if needle in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"{label}: forbidden {needle!r} in {path}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v23331_live_speaker.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = base / "SpanishStudyController.java"
    sherpa = base / "SherpaNeuralShadow.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    live_src = repo / "overlay/v23331/app/spanishstudy/vot/LiveSpeakerOnline.java"
    for p in (player, controller, sherpa, hook, live_src):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.31 input: {p}")

    shutil.copy2(live_src, base / "LiveSpeakerOnline.java")
    print("copied: LiveSpeakerOnline.java")

    rep(
        sherpa,
        '''            assetsExtracted = true;\n            extractionStep = "payload-ready";\n\n            OfflineSpeakerSegmentationPyannoteModelConfig pyannote =\n''',
        '''            assetsExtracted = true;\n            extractionStep = "payload-ready";\n            LiveSpeakerOnline.initialize(embedding.getAbsolutePath());\n\n            OfflineSpeakerSegmentationPyannoteModelConfig pyannote =\n''',
        "initialize live ERes2Net extractor from proven embedding payload",
    )

    rep(
        sherpa,
        '''    public static String labelAtVideoMs(long videoMs) {\n        if (!absoluteTimelineValid || videoMs < 0L) return "";\n''',
        '''    public static String labelAtVideoMs(long videoMs) {\n        String live = LiveSpeakerOnline.labelAtVideoMs(videoMs);\n        if (!live.isEmpty()) return live;\n        if (!absoluteTimelineValid || videoMs < 0L) return "";\n''',
        "prefer live speaker label before bounded batch fallback",
    )
    rep(
        sherpa,
        '''    public static String labelDetailsAtVideoMs(long videoMs) {\n        return ''',
        '''    public static String labelDetailsAtVideoMs(long videoMs) {\n        String live = LiveSpeakerOnline.labelAtVideoMs(videoMs);\n        if (!live.isEmpty()) return LiveSpeakerOnline.labelDetailsAtVideoMs(videoMs);\n        return ''',
        "prefer live speaker badge details",
    )

    old_complete = '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {\n                    captureComplete = true;\n                    inferenceStarted = true;\n                    nativeInferenceBusy = true;\n                    inference = Arrays.copyOf(CAPTURE, CAPTURE_TARGET_SAMPLES);\n                    epoch = captureEpoch;\n                }\n'''
    new_complete = '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {\n                    captureComplete = true;\n                    if (LiveSpeakerOnline.isReady()) {\n                        inferenceStarted = false;\n                        inferenceDone = true;\n                        inferenceMs = 0L;\n                        inferenceSegments = 0;\n                        inferenceSpeakers = 0;\n                        inferenceSummary = "skipped-live-embedding-primary";\n                        inferenceError = "none";\n                    } else {\n                        inferenceStarted = true;\n                        nativeInferenceBusy = true;\n                        inference = Arrays.copyOf(CAPTURE, CAPTURE_TARGET_SAMPLES);\n                        epoch = captureEpoch;\n                    }\n                }\n'''
    rep(sherpa, old_complete, new_complete, "make 20-second batch inference fallback-only")

    old_handoff = '''        try {\n            app.spanishstudy.vot.SherpaNeuralShadow.observeAcceptedPcmBuffer(\n                    buffer, sampleRateHz, channels, studyAudioTrackEncoding, acceptedBytes,\n                    trackEndFrame, trackIdentity);\n        } catch (Throwable ignored) {\n            // Neural shadow must never escape onto ExoPlayer's audio thread.\n        }\n'''
    new_handoff = old_handoff + '''        try {\n            app.spanishstudy.vot.LiveSpeakerOnline.observeAcceptedPcmBuffer(\n                    buffer, sampleRateHz, channels, studyAudioTrackEncoding, acceptedBytes,\n                    trackEndFrame, trackIdentity);\n        } catch (Throwable ignored) {\n            // Live speaker identity must never escape onto ExoPlayer's audio thread.\n        }\n'''
    rep(player, old_handoff, new_handoff, "feed live identity from verifier-safe accepted PCM")

    rep(
        player,
        '''        try {\n            app.spanishstudy.vot.SherpaNeuralShadow.resetCaptureForVideo();\n            // Stage E: per-video voice gate and activity statistics.\n''',
        '''        try {\n            app.spanishstudy.vot.SherpaNeuralShadow.resetCaptureForVideo();\n            app.spanishstudy.vot.LiveSpeakerOnline.resetForVideo();\n            // Stage E: per-video voice gate and activity statistics.\n''',
        "reset live identities only on genuinely new video",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.33.30 verifier-safe accepted-PCM video-master diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics\\n");',
        "update v2.33.31 diagnostics header",
    )
    rep(
        controller,
        '        report.append("nativeInferenceLifecycle=retain-model+epoch-discard+single-native-worker-no-interrupt\\n");\n',
        '        report.append("nativeInferenceLifecycle=live-embedding-single-latest-wins-worker;20s-batch-fallback-only\\n");\n'
        '        report.append("speakerLiveGoal=human-identity-not-voice-style;multi-prototype-impression-tolerance\\n");\n',
        "declare live identity architecture",
    )
    rep(
        controller,
        '        report.append("speakerLabelClock=neural-absolute-video-ms-projection\\n");\n',
        '        report.append("speakerLabelClock=live-eres2net-video-ms+bounded-batch-fallback\\n");\n',
        "declare live badge clock",
    )
    rep(
        controller,
        '        report.append("speakerLabelPersistence=per-video-neural-projected-timeline-diagnostic-only\\n");\n',
        '        report.append("speakerLabelPersistence=per-video-online-human-identity+multi-style-prototypes\\n");\n',
        "declare persistent human speaker identity",
    )
    rep(
        controller,
        '''        report.append(SherpaNeuralShadow.diagnostics()).append('\\n');\n''',
        '''        report.append(SherpaNeuralShadow.diagnostics()).append('\\n');\n        report.append(LiveSpeakerOnline.diagnostics()).append('\\n');\n''',
        "publish live speaker diagnostics",
    )

    text = sherpa.read_text(encoding="utf-8")
    old = "speakerNeuralGate=v2.33.30-neural-only+accepted-postwrite+video-master-projection"
    new = "speakerNeuralGate=v2.33.31-live-embedding-primary+20s-diarization-fallback"
    if text.count(old) < 1:
        raise RuntimeError("v2.33.31 neural gate marker: old marker missing")
    sherpa.write_text(text.replace(old, new), encoding="utf-8")
    print("patched: identify v2.33.31 neural gate")

    require(hook, "observeAudioTrackWriteResultForStudy(I)V", "int-only result callback retained")
    require(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "pre-write ByteBuffer callback retained")
    forbid(hook, "observeAcceptedPcmBufferForStudy", "no post-write target ByteBuffer callback")
    require(player, "studyPcmWritePendingBuffer.set(buffer);", "ThreadLocal accepted-buffer bridge retained")
    require(player, "LiveSpeakerOnline.observeAcceptedPcmBuffer", "live accepted PCM feed")
    require(sherpa, "LiveSpeakerOnline.initialize(embedding.getAbsolutePath())", "live embedding init")
    require(sherpa, "skipped-live-embedding-primary", "batch fallback-only gate")
    require(controller, "v2.33.31 near-live ERes2Net", "runtime version identity")

    print("v2.33.31 live speaker patch complete")
    print("PRESERVED: v2.33.30 verifier-safe ThreadLocal accepted PCM + exact track-frame video projection")
    print("ADDED: 2 s / 0.75 s-hop ERes2Net online embeddings, latest-wins worker, persistent multi-style A/B/C identities")
    print("IMPRESSION POLICY: continuous vocal-style changes stay on same human and can add a profile prototype")
    print("NEW PERSON POLICY: unmatched identity requires repeated evidence instead of one altered voice window")
    print("FALLBACK: old 20 s full diarization runs only if live embedding extractor is unavailable")
    print("UNCHANGED: translation, TTS, subtitle packetization, voice routing, video-master clock, target write hook")


if __name__ == "__main__":
    main()
