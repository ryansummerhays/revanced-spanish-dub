#!/usr/bin/env python3
"""Audit v2.32.3: English-source repair + counter-only decoded PCM hook."""
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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2323_pcm_counter_english_source.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    # Self-identification and English-source behavior.
    need(controller, "Spanish Dub Study v2.32.3 Stage-A PCM diagnostics", "v2.32.3 header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "caption-source diagnostic")
    need(controller, "pcmProbe=audio-track-write-bytebuffer-counter-only", "PCM probe diagnostic")
    need(controller, "pcmProbeBufferReads=0", "zero buffer reads diagnostic")
    need(controller, "pcmProbeBufferCopies=0", "zero buffer copies diagnostic")
    need(controller, "pcmProbeWorkerThreads=0", "zero worker threads diagnostic")
    need(controller, "PlayerVolumePatch.getPcmHookCallsForStudy()", "PCM hook count publication")

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English caption track precedes Spanish target track only for Spanish target")

    # Stage-A hook must be one-argument and counter-only.
    need(player_volume, "public static void observePcmBufferForStudy(ByteBuffer buffer)", "one-argument PCM callback")
    need(player_volume, "studyPcmHookCalls++;", "counter increment")
    need(player_volume, "public static long getPcmHookCallsForStudy()", "counter getter")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "one-argument bytecode call")
    need(hook, "invoke-static/range { v$bufferRegister .. v$bufferRegister }", "single-register range invoke")

    # Do not accidentally restore the old invasive v2.32 callback path.
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "second size-register injection")
    forbid(player_volume, ".duplicate()", "PCM buffer duplication")
    forbid(player_volume, ".get(", "PCM buffer reads")
    forbid(player_volume, "new Thread", "PCM worker thread")
    forbid(player_volume, "Executor", "PCM executor")
    forbid(player_volume, "PcmSpeakerFeature", "feature extraction")

    # Sacred Morphe packetization / segmentation invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet cardinality contract retained")

    # Stock volume hooks remain in place around the probe.
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack observation retained")

    print("v2.32.3 audit passed")
    print("Stage A intentionally performs no PCM analysis; runtime success criterion is pcmProbeHookCalls > 0 without startup/playback crashes.")


if __name__ == "__main__":
    main()
