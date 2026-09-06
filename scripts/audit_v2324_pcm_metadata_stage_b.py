#!/usr/bin/env python3
"""Audit v2.32.4 Stage B: decoded PCM ByteBuffer metadata only."""
from pathlib import Path
import sys


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing {label}: {token}")
    print("ok:", label)


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise RuntimeError(f"forbidden {label}: {token}")
    print("ok absent:", label)


def between(text: str, start: str, end: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f"missing {label} start anchor")
    b = text.find(end, a + len(start))
    if b < 0:
        raise RuntimeError(f"missing {label} end anchor")
    return text[a:b]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2324_pcm_metadata_stage_b.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.4 Stage-B PCM metadata diagnostics", "Stage-B header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmProbe=audio-track-write-bytebuffer-metadata-only", "metadata-only probe label")
    need(controller, "pcmProbeSampleReads=0", "zero sample reads diagnostic")
    need(controller, "pcmProbeBufferCopies=0", "zero copies diagnostic")
    need(controller, "pcmProbeWorkerThreads=0", "zero worker threads diagnostic")
    for getter in (
        "getPcmHookCallsForStudy()", "getPcmNonNullBuffersForStudy()", "getPcmNullBuffersForStudy()",
        "getPcmNonEmptyBuffersForStudy()", "getPcmEmptyBuffersForStudy()", "getPcmObservedBytesForStudy()",
        "getPcmBufferDuplicatesForStudy()", "getPcmLastPositionForStudy()", "getPcmLastLimitForStudy()",
        "getPcmLastRemainingForStudy()", "getPcmMaxRemainingForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "diagnostic publication " + getter)

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: v2.32.3 English-source repair retained")

    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "same one-argument AudioTrack.write hook")
    need(hook, "invoke-static/range { v$bufferRegister .. v$bufferRegister }", "same single-register range invoke")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    callback = between(
        player_volume,
        "public static void observePcmBufferForStudy(ByteBuffer buffer)",
        "public static long getPcmHookCallsForStudy()",
        "Stage-B callback",
    )
    need(callback, "studyPcmHookCalls++;", "hook counter retained")
    need(callback, "if (buffer == null)", "null guard")
    need(callback, "ByteBuffer view = buffer.duplicate();", "non-mutating duplicate")
    need(callback, "int position = view.position();", "position metadata read")
    need(callback, "int limit = view.limit();", "limit metadata read")
    need(callback, "int remaining = view.remaining();", "remaining metadata read")
    need(callback, "studyPcmObservedBytes += remaining;", "observed-byte accumulation")
    need(callback, "studyPcmMaxRemaining", "maximum-buffer-size accumulation")

    # Stage B may inspect ByteBuffer metadata only. It must not touch sample bytes or dispatch work.
    forbid(callback, ".get(", "sample-byte read")
    forbid(callback, ".getShort(", "PCM16 sample read")
    forbid(callback, ".getFloat(", "float sample read")
    forbid(callback, ".array(", "backing-array access")
    forbid(callback, "new byte", "byte-array allocation")
    forbid(callback, "System.arraycopy", "buffer copy")
    forbid(callback, "Thread", "worker thread")
    forbid(callback, "Executor", "executor")
    forbid(callback, "submit(", "worker dispatch")
    forbid(callback, "execute(", "worker dispatch")
    forbid(callback, "PcmSpeakerFeature", "feature extraction")
    forbid(callback, "LocalSpeakerDiarizer", "speaker diarizer")
    forbid(callback, "SpanishStudyDiagnostics", "audio-thread logging")

    # Sacred Morphe translation/segmentation invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")

    # Stock Morphe volume hooks remain present.
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack observation retained")

    print("v2.32.4 Stage-B audit passed")
    print("Runtime success: stable playback + pcmProbeNonEmptyBuffers > 0 + pcmProbeObservedBytes > 0.")


if __name__ == "__main__":
    main()
