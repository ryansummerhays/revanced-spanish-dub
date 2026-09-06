#!/usr/bin/env python3
"""Audit v2.32.6 Stage D: actual AudioTrack receiver format metadata, no PCM decoding yet."""
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
        raise SystemExit("usage: audit_v2326_audiotrack_format_stage_d.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.6 Stage-D AudioTrack format diagnostics", "Stage-D header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmProbe=audio-track-write-bytebuffer-sparse-bounded-read", "Stage-C raw-byte probe retained")
    need(controller, "pcmTrackProbe=actual-audiotrack-write-receiver-format-metadata", "Stage-D track probe label")
    need(controller, "pcmProbeBufferCopies=0", "zero copies diagnostic retained")
    need(controller, "pcmProbeWorkerThreads=0", "zero workers diagnostic retained")

    for getter in (
        "getAudioTrackProbeStrideForStudy()", "getAudioTrackProbeCallsForStudy()",
        "getAudioTrackProbeAttemptsForStudy()", "getAudioTrackProbeSuccessForStudy()",
        "getAudioTrackProbeErrorsForStudy()", "getAudioTrackSessionIdForStudy()",
        "getAudioTrackSampleRateHzForStudy()", "getAudioTrackChannelCountForStudy()",
        "getAudioTrackEncodingForStudy()", "getAudioTrackStateForStudy()",
        "getAudioTrackPlayStateForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "Stage-D diagnostic publication " + getter)

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    # The hook must use the exact AudioTrack receiver and ByteBuffer registers from the same proven write call.
    need(hook, "val trackRegister = when (writeInstruction)", "AudioTrack receiver register extraction")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerC", "FiveRegister receiver register")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister", "range receiver register")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerD", "FiveRegister ByteBuffer register retained")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister + 1", "range ByteBuffer register retained")
    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "Stage-D AudioTrack receiver callback")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "Stage-C ByteBuffer callback retained")
    need(hook, "invoke-static/range { v$trackRegister .. v$trackRegister }", "single-register AudioTrack callback")
    need(hook, "invoke-static/range { v$bufferRegister .. v$bufferRegister }", "single-register ByteBuffer callback")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    track_callback = between(
        player_volume,
        "public static void observeAudioTrackForStudy(AudioTrack track)",
        "/**\n     * Spanish Dub Study Stage-B injection point",
        "Stage-D AudioTrack callback",
    )
    need(track_callback, "track.getAudioSessionId()", "session-id getter")
    need(track_callback, "track.getSampleRate()", "sample-rate getter")
    need(track_callback, "track.getChannelCount()", "channel-count getter")
    need(track_callback, "track.getAudioFormat()", "encoding getter")
    need(track_callback, "track.getState()", "state getter")
    need(track_callback, "track.getPlayState()", "play-state getter")
    need(track_callback, "STUDY_AUDIO_TRACK_PROBE_STRIDE", "sparse refresh gate")
    need(track_callback, "catch (Throwable ignored)", "fail-soft receiver probe")

    # Metadata callback must remain tiny: no sample touching, copying, background work, or speaker logic.
    for token, label in (
        ("ByteBuffer", "ByteBuffer access in track callback"),
        ("getShort(", "PCM16 decode in track callback"),
        ("getFloat(", "float decode in track callback"),
        ("new byte", "byte-array allocation in track callback"),
        ("System.arraycopy", "copy in track callback"),
        ("Thread", "worker thread in track callback"),
        ("Executor", "executor in track callback"),
        ("PcmSpeakerFeature", "feature extraction in track callback"),
        ("LocalSpeakerDiarizer", "speaker diarizer in track callback"),
        ("SpanishStudyDiagnostics", "audio-thread logging in track callback"),
    ):
        forbid(track_callback, token, label)

    # Stage-C sparse raw-byte read must remain intact and must still not decode samples.
    pcm_callback = between(
        player_volume,
        "public static void observePcmBufferForStudy(ByteBuffer buffer)",
        "public static long getPcmHookCallsForStudy()",
        "Stage-C PCM callback",
    )
    need(pcm_callback, "ByteBuffer view = buffer.duplicate();", "Stage-C duplicate retained")
    need(pcm_callback, "STUDY_PCM_SAMPLE_STRIDE", "Stage-C sparse-read gate retained")
    need(pcm_callback, "Math.min(remaining, STUDY_PCM_SAMPLE_MAX_BYTES)", "Stage-C bounded byte count retained")
    need(pcm_callback, "view.get(start + i)", "Stage-C absolute raw-byte read retained")
    need(pcm_callback, "studyPcmSampleReadErrors++;", "Stage-C fail-soft read error retained")
    forbid(pcm_callback, ".getShort(", "PCM16 decoding still absent")
    forbid(pcm_callback, ".getFloat(", "float PCM decoding still absent")
    forbid(pcm_callback, ".order(", "byte-order assumption still absent")
    forbid(pcm_callback, "new byte", "byte-array allocation still absent")
    forbid(pcm_callback, "Thread", "worker thread still absent")
    forbid(pcm_callback, "Executor", "executor still absent")
    forbid(pcm_callback, "PcmSpeakerFeature", "feature extraction still absent")
    forbid(pcm_callback, "LocalSpeakerDiarizer", "speaker diarizer still absent")

    # Sacred Morphe translation/segmentation invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")

    # Stock Morphe volume hooks remain present.
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack wrapper observation retained")

    print("v2.32.6 Stage-D audit passed")
    print("Runtime success: stable playback + Stage-C reads healthy + trackProbeSuccess > 0 + trackProbeErrors == 0 + sampleRate/channelCount/encoding > 0.")


if __name__ == "__main__":
    main()
