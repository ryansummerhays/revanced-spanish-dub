#!/usr/bin/env python3
from pathlib import Path
import sys


def must(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"FAIL {label}: missing {needle!r}")
    print("PASS", label)


def must_not(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"FAIL {label}: forbidden {needle!r}")
    print("PASS", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23331_live_speaker.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    live = base / "LiveSpeakerOnline.java"
    sherpa = base / "SherpaNeuralShadow.java"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    controller = base / "SpanishStudyController.java"
    for p in (live, sherpa, player, hook, controller):
        if not p.is_file(): raise RuntimeError(f"missing audit input {p}")

    lt = live.read_text(encoding="utf-8")
    st = sherpa.read_text(encoding="utf-8")
    pt = player.read_text(encoding="utf-8")
    ht = hook.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")

    must(lt, "SpeakerEmbeddingExtractor", "direct ERes2Net extractor API")
    must(lt, "WINDOW_SAMPLES = 32_000", "2 second embedding window")
    must(lt, "HOP_SAMPLES = 12_000", "750 ms hop")
    must(lt, "jobsDroppedLatestWins", "latest-wins backlog containment")
    must(lt, "MAX_PROTOTYPES = 3", "multi-style prototypes")
    must(lt, "continuous-run-identity-hold", "impression/range continuity hold")
    must(lt, "new-speaker-confirmed", "repeated evidence new-person confirmation")
    must(lt, "resetContinuityLocked", "seek continuity reset preserving people")
    must(lt, "resetForVideo", "new-video identity reset")
    must_not(lt, "AudioRecord", "no microphone AudioRecord")

    must(st, "LiveSpeakerOnline.initialize(embedding.getAbsolutePath())", "live model initialized from extracted payload")
    must(st, "String live = LiveSpeakerOnline.labelAtVideoMs(videoMs);", "live badge preferred")
    must(st, "skipped-live-embedding-primary", "20 s batch fallback-only")
    must(st, "speakerNeuralGate=v2.33.31-live-embedding-primary+20s-diarization-fallback", "v31 neural gate marker")

    must(pt, "LiveSpeakerOnline.observeAcceptedPcmBuffer", "live tracker fed exact accepted PCM")
    must(pt, "LiveSpeakerOnline.resetForVideo();", "Stage-J new-video live reset")
    must(pt, "studyPcmWritePendingBuffer.set(buffer);", "v30 ThreadLocal ByteBuffer bridge retained")
    must(pt, "final ByteBuffer acceptedBuffer = studyPcmWritePendingBuffer.get();", "v30 post-write object recovery retained")

    must(ht, "observeAudioTrackWriteResultForStudy(I)V", "int-only post-write result callback retained")
    must(ht, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "pre-write ByteBuffer callback retained")
    must_not(ht, "observeAcceptedPcmBufferForStudy", "no verifier-unsafe target post-write ByteBuffer callback")

    must(ct, "Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics", "v31 runtime identity")
    must(ct, "speakerLiveGoal=human-identity-not-voice-style", "human identity goal explicit")
    must(ct, "LiveSpeakerOnline.diagnostics()", "live diagnostics published")
    must(ct, "speakerLabelClock=live-eres2net-video-ms+bounded-batch-fallback", "live label clock declared")

    print("v2.33.31 source audit PASS")


if __name__ == "__main__":
    main()
