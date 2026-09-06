#!/usr/bin/env python3
"""Audit v2.32.5 Stage C: sparse bounded raw-byte reads from decoded PCM ByteBuffer."""
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
        raise SystemExit("usage: audit_v2325_pcm_sample_read_stage_c.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.5 Stage-C PCM sample-read diagnostics", "Stage-C header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmProbe=audio-track-write-bytebuffer-sparse-bounded-read", "Stage-C probe label")
    need(controller, "pcmProbeBufferCopies=0", "zero copies diagnostic")
    need(controller, "pcmProbeWorkerThreads=0", "zero workers diagnostic")
    for getter in (
        "getPcmSampleStrideForStudy()", "getPcmSampleMaxBytesForStudy()",
        "getPcmSampleReadCallsForStudy()", "getPcmSampleBytesReadForStudy()",
        "getPcmSampleZeroBytesForStudy()", "getPcmSampleNonZeroBytesForStudy()",
        "getPcmSampleReadErrorsForStudy()", "getPcmSampleRollingHashForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "Stage-C diagnostic publication " + getter)

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    # The hook itself must remain exactly the proven one-register callback family.
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "same one-argument AudioTrack.write hook")
    need(hook, "invoke-static/range { v$bufferRegister .. v$bufferRegister }", "same single-register range invoke")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    callback = between(
        player_volume,
        "public static void observePcmBufferForStudy(ByteBuffer buffer)",
        "public static long getPcmHookCallsForStudy()",
        "Stage-C callback",
    )
    need(callback, "ByteBuffer view = buffer.duplicate();", "Stage-B duplicate retained")
    need(callback, "STUDY_PCM_SAMPLE_STRIDE", "sparse-read stride gate")
    need(callback, "STUDY_PCM_SAMPLE_MAX_BYTES", "bounded read ceiling")
    need(callback, "view.get(start + i)", "absolute raw-byte read")
    need(callback, "studyPcmSampleReadErrors++;", "fail-soft read error counter")
    need(callback, "Math.min(remaining, STUDY_PCM_SAMPLE_MAX_BYTES)", "bounded byte count")

    # Stage C may read sparse raw bytes only. It must not decode samples or dispatch/copy work.
    forbid(callback, ".getShort(", "PCM16 decoding")
    forbid(callback, ".getFloat(", "float PCM decoding")
    forbid(callback, ".order(", "byte-order assumption")
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

    print("v2.32.5 Stage-C audit passed")
    print("Runtime success: stable playback + sampleReadCalls > 0 + sampleBytesRead > 0 + sampleReadErrors == 0.")


if __name__ == "__main__":
    main()
